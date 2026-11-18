#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""Confere os cinco rascunhos de um caso do SIMBA ANTES da aprovação.

Cada arquivo é gerado sozinho, e o órgão os cruza: as contas do EXTRATO e do
TITULARES são as do CONTAS, o ORIGEM-DESTINO aponta para os lançamentos do EXTRATO
pelo número. O Reporter recusa o que um documento sozinho prova errado; o que só
aparece cruzando os cinco sai daqui, para quem aprova.

ERRO (corrigir ou gerar de novo antes de aprovar):
  * linha sem CRLF, com caractere fora do ASCII (IN art. 3º, caput) ou com outro
    número de campos do que o Anexo I dá ao arquivo;
  * EXTRATO e ORIGEM-DESTINO com números de lançamento diferentes, ou o mesmo número
    com outro valor (um lançamento gravado entre as duas gerações desloca a
    numeração: gere os dois de novo);
  * conta do EXTRATO ou do TITULARES que não está no CONTAS; agência do CONTAS que
    não está no AGENCIAS.

AVISO (listado para o aprovador, não bloqueia):
  * CONTAS sem conta nenhuma: confira os documentos da ordem;
  * último saldo do EXTRATO diferente do saldo final do CONTAS (lançamento
    retroativo, ou outra chave de saldo). Com as linhas dos rascunhos, o último é o
    de maior instante (`horaLancamento`); sem elas, a última linha do arquivo, que
    pode não ser a mais recente (uma transação pendente confirmada depois);
  * lançamento com o código genérico 125 ou 218 do Anexo II;
  * ORIGEM-DESTINO com a contraparte não identificada pelo trilho, ou com a
    contraparte sem CPF/CNPJ;
  * conta com saldo inicial ou final devedor (cheque especial). O CONTAS escreve o
    saldo sem sinal (o Anexo I não lhe dá sinal), e o EXTRATO nunca o mostra devedor
    (o saldo disponível do Midaz não fica abaixo de zero). Por isso a conferência lê
    as linhas do rascunho do CONTAS, como o Reporter as devolve em
    `GET /v1/regulatory/reports/{reportId}/rows`, onde o saldo tem sinal. Sem elas, o
    saldo devedor não é conferido, e a conferência diz isso.

BLOQUEIO (completude do reenvio): com `--anterior`, as linhas de cada rascunho são
comparadas com as do último envio aprovado (Final) do mesmo caso, conjunto a
conjunto, pela chave do grão que o contrato declara. Uma chave do Final que falta no
rascunho novo é uma linha que o reenvio perdeu (um cadastro apagado, um lançamento
estornado na base, um binding alterado) e BLOQUEIA a aprovação, a menos que o
arquivo de justificativas a libere com o motivo registrado. Um conjunto do envio
anterior que o contrato atual não tem, ou um documento sem rascunho novo, também
bloqueia. Uma chave nova é só aviso. A pasta de `--anterior` traz o ÚLTIMO envio
aprovado, uma resposta por documento, com status Final; quem roda a conferência a
escolhe, e o script recusa pasta vazia, status que não seja Final e documento repetido.

Fora do alcance: valor bloqueado na conta, e o cheque especial usado e coberto dentro
do período (saldos inicial e final credores). Nenhum dos cinco arquivos nem as linhas
do rascunho trazem esses valores.

As mensagens citam agência, conta e número da linha, nunca documento ou nome: a
saída da conferência é lida por quem aprova, e o arquivo é sigiloso.

Uso:
    python3 tools/simba_conferencia.py <pasta> <caso> [--rascunhos <pasta>]
        [--anterior <pasta> [--justificativas <arquivo>]]

A pasta tem os cinco arquivos como o script de lote os nomeia:
<caso>_AGENCIAS.txt, <caso>_CONTAS.txt, <caso>_TITULARES.txt, <caso>_EXTRATO.txt e
<caso>_ORIGEM_DESTINO.txt. `--rascunhos` e `--anterior` são pastas com a resposta de
`/rows` de cada documento (um JSON por documento, o nome do arquivo não importa: o
documento sai do `documentId`). `--justificativas` é um JSON com a lista
`[{"documentId", "dataset", "key": {campo: valor}, "motivo"}]`, e só vale com
`--anterior`.

Saída: 0 sem erro e sem bloqueio; 1 com erro ou com bloqueio não justificado.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Os arquivos e o número de campos de cada um (IN BCB 636/2025, Anexo I).
FILES = {
    "AGENCIAS": 14,
    "CONTAS": 12,
    "TITULARES": 28,
    "EXTRATO": 27,
    "ORIGEM_DESTINO": 28,
}
GENERIC_CODES = {"125", "218"}
UNIDENTIFIED = "contraparte nao identificada pelo trilho"
CONTAS_SETS = ("contas_investigadas", "contas_contraparte")
CONTAS_DOCUMENT = "br.bcb.simba.contas"
EXTRATO_DOCUMENT = "br.bcb.simba.extrato"
EXTRATO_ENTRIES = "lancamentos"


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.blocks: list[str] = []
        self.released: list[str] = []

    def error(self, text: str) -> None:
        self.errors.append(text)

    def warn(self, text: str) -> None:
        self.warnings.append(text)

    def block(self, text: str) -> None:
        self.blocks.append(text)


def read_lines(path: Path, name: str, report: Report) -> list[list[str]]:
    """As linhas do arquivo, cada uma como a lista dos seus campos (campo 1 é o índice 0)."""
    raw = path.read_bytes()
    lines = raw.split(b"\r\n")
    if lines[-1]:
        report.error(f"{name}: a última linha não termina em CRLF")
    else:
        lines.pop()
    rows = []
    for number, line in enumerate(lines, 1):
        try:
            text = line.decode("ascii")
        except UnicodeDecodeError:
            report.error(f"{name}:{number}: caractere fora do ASCII")
            text = line.decode("ascii", errors="replace")
        if "\n" in text or "\r" in text:
            report.error(f"{name}:{number}: quebra de linha que não é CRLF")
        fields = text.split("\t")
        if len(fields) != FILES[name]:
            report.error(f"{name}:{number}: {len(fields)} campos; o Anexo I dá {FILES[name]}")
        rows.append(fields)
    return rows


def field(row: list[str], number: int) -> str:
    return row[number - 1] if len(row) >= number else ""


def check_numbering(extrato: list[list[str]], od: list[list[str]], report: Report) -> None:
    values = {field(r, 1): field(r, 10) for r in extrato}
    od_numbers = {field(r, 2) for r in od}
    for number in sorted(set(values) - od_numbers, key=_as_int):
        report.error(f"EXTRATO: o lançamento {number} não tem linha no ORIGEM-DESTINO; gere os dois de novo")
    for number in sorted(od_numbers - set(values), key=_as_int):
        report.error(f"ORIGEM_DESTINO: o lançamento {number} não está no EXTRATO; gere os dois de novo")
    for line, row in enumerate(od, 1):
        number = field(row, 2)
        if number in values and field(row, 3) != values[number]:
            report.error(f"ORIGEM_DESTINO:{line}: o lançamento {number} vale {field(row, 3)} aqui e "
                         f"{values[number]} no EXTRATO; gere os dois de novo")


def check_membership(files: dict[str, list[list[str]]], report: Report) -> None:
    accounts = {(field(r, 2), field(r, 3)) for r in files["CONTAS"]}
    branches = {field(r, 2) for r in files["AGENCIAS"]}
    for name, agency, account in (("EXTRATO", 3, 4), ("TITULARES", 2, 3)):
        for key in sorted({(field(r, agency), field(r, account)) for r in files[name]} - accounts):
            report.error(f"{name}: a conta {key[1]} da agência {key[0]} não está no CONTAS")
    for branch in sorted({field(r, 2) for r in files["CONTAS"]} - branches):
        report.error(f"CONTAS: a agência {branch} não está no AGENCIAS")


def check_balances(extrato: list[list[str]], contas: list[list[str]], drafts: dict[str, dict] | None,
                   report: Report) -> None:
    """O último saldo de cada conta no EXTRATO contra o saldo final do CONTAS."""
    entries = (drafts or {}).get(EXTRATO_DOCUMENT, {}).get(EXTRATO_ENTRIES)
    accounts = (drafts or {}).get(CONTAS_DOCUMENT)
    if entries is not None and accounts is not None:
        _check_balances_by_instant(entries, accounts, report)
        return
    last: dict[tuple[str, str], list[str]] = {}
    for row in extrato:
        last[(field(row, 3), field(row, 4))] = row
    final = {(field(r, 2), field(r, 3)): field(r, 11) for r in contas}
    for key, row in sorted(last.items()):
        if key in final and _cents(field(row, 12)) != _cents(final[key]):
            report.warn(f"EXTRATO: o saldo da última linha da conta {key[1]} da agência {key[0]} é {field(row, 12)}, e o "
                        f"saldo final no CONTAS é {final[key]} (lançamento retroativo, outra chave de saldo, ou uma "
                        "transação confirmada depois de outra: sem --rascunhos, o último é a última linha do arquivo)")


def _check_balances_by_instant(entries: list[dict], accounts: dict, report: Report) -> None:
    last: dict[tuple[str, str], tuple[datetime, str]] = {}
    for row in entries:
        key = (str(row.get("numeroAgencia")), str(row.get("numeroConta")))
        instant = _instant(row.get("horaLancamento"))
        if instant is None:
            report.error(f"EXTRATO: um lançamento da conta {key[1]} da agência {key[0]} não tem instante legível")
            continue
        if key not in last or instant >= last[key][0]:
            last[key] = (instant, str(row.get("saldoApos")))
    final = {(str(r.get("numeroAgencia")), str(r.get("numeroConta"))): str(r.get("saldoFinal"))
             for name in CONTAS_SETS for r in accounts.get(name) or []}
    for key, (_, balance) in sorted(last.items()):
        if key in final and _decimal(balance) != _decimal(final[key]):
            report.warn(f"EXTRATO: o saldo após o último lançamento da conta {key[1]} da agência {key[0]} é {balance}, "
                        f"e o saldo final no CONTAS é {final[key]} (lançamento retroativo ou outra chave de saldo)")


def check_generic_entries(extrato: list[list[str]], od: list[list[str]], report: Report) -> None:
    for line, row in enumerate(extrato, 1):
        if field(row, 9) in GENERIC_CODES:
            report.warn(f"EXTRATO:{line}: o lançamento {field(row, 1)} tem o código genérico {field(row, 9)}")
    for line, row in enumerate(od, 1):
        if field(row, 18) == UNIDENTIFIED:
            report.warn(f"ORIGEM_DESTINO:{line}: o lançamento {field(row, 2)} tem a contraparte não identificada pelo trilho")
        elif not field(row, 10):
            report.warn(f"ORIGEM_DESTINO:{line}: a contraparte do lançamento {field(row, 2)} está sem CPF/CNPJ")


def check_overdraft_rows(drafts: dict[str, dict] | None, report: Report) -> None:
    contas = (drafts or {}).get(CONTAS_DOCUMENT)
    if contas is None:
        report.warn("CONTAS: sem as linhas do rascunho do CONTAS (--rascunhos), o saldo devedor NÃO foi conferido")
        return
    for name in CONTAS_SETS:
        for row in contas.get(name) or []:
            for balance, label in (("saldoInicial", "inicial"), ("saldoFinal", "final")):
                value = str(row.get(balance) or "")
                if value.startswith("-"):
                    report.warn(f"CONTAS: a conta {row.get('numeroConta')} da agência {row.get('numeroAgencia')} tem "
                                f"saldo {label} devedor ({value}); o arquivo o escreve sem sinal")


def check_resubmission(drafts: dict[str, dict], previous: dict[str, dict], justified: set[tuple],
                       report: Report) -> None:
    """Diff por linha, pela chave do grão, entre o último Final e o rascunho novo."""
    for document, final_sets in sorted(previous.items()):
        try:
            grains = grains_of(document)
        except ValueError as problem:
            report.error(f"--anterior: {problem}")
            continue
        if document not in drafts:
            report.block(f"{document}: há envio aprovado anterior e não há rascunho novo")
            continue
        for dataset, final_rows in sorted(final_sets.items()):
            if dataset not in grains:
                report.block(f"{document} {dataset}: o conjunto do envio anterior não existe no contrato atual; "
                             "compare as linhas à mão")
                continue
            grain = grains[dataset]
            if not isinstance(grain, list):
                continue
            before = {_key(row, grain) for row in final_rows or []}
            after = {_key(row, grain) for row in drafts[document].get(dataset) or []}
            for key in sorted(before - after):
                text = f"{document} {dataset}: a linha {_describe(grain, key)} do envio anterior falta no rascunho"
                if (document, dataset, key) in justified:
                    report.released.append(text)
                else:
                    report.block(text + "; libere só com o motivo registrado em --justificativas")
            if after - before:
                report.warn(f"{document} {dataset}: {len(after - before)} linha(s) novas em relação ao envio anterior")


def grains_of(document: str) -> dict[str, list[str] | str]:
    """Conjunto → grão (campos da chave, ou singleton), como o contrato do documento declara."""
    for path in sorted((ROOT / "br" / "bcb" / "simba").glob("*/contract.yaml")):
        contract = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if (contract.get("metadata") or {}).get("id") == document:
            return {d["name"]: d.get("grain") for d in contract.get("datasets") or []
                    if isinstance(d, dict) and isinstance(d.get("name"), str)}
    raise ValueError(f"{document}: não é documento do SIMBA neste catálogo")


def read_rows(folder: Path | None, status: str, option: str, report: Report) -> dict[str, dict] | None:
    """documentId → conjuntos de linhas, das respostas de /rows guardadas na pasta.

    Uma resposta por documento, todas com o status esperado: uma pasta vazia, um
    rascunho onde se espera o Final, ou dois arquivos do mesmo documento fariam a
    conferência comparar contra a base errada sem dizer.
    """
    if folder is None:
        return None
    paths = sorted(folder.glob("*.json")) if folder.is_dir() else []
    if not paths:
        report.error(f"{option}: {folder} não existe ou não tem resposta de /rows (*.json)")
        return {}
    found: dict[str, dict] = {}
    for path in paths:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            identifier, datasets = document["documentId"], document["datasets"]
        except (OSError, ValueError, KeyError, TypeError) as problem:
            report.error(f"{option}: {path.name} não é uma resposta de /rows ({problem})")
            continue
        if document.get("status") != status:
            report.error(f"{option}: {path.name} tem status {document.get('status')!r}; aqui vai {status}")
            continue
        if identifier in found:
            report.error(f"{option}: há mais de uma resposta de {identifier}; deixe só uma")
            continue
        found[identifier] = datasets
    return found


def read_justifications(path: Path | None, report: Report) -> set[tuple]:
    if path is None:
        return set()
    justified = set()
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as problem:
        report.error(f"{path.name}: não se lê ({problem})")
        return justified
    if not isinstance(entries, list):
        report.error(f"{path.name}: as justificativas são uma lista")
        return justified
    for entry in entries:
        if not isinstance(entry, dict) or not str(entry.get("motivo") or "").strip():
            report.error(f"{path.name}: há justificativa sem motivo, que não libera nada")
            continue
        key = entry.get("key") or {}
        grain = sorted(key)
        try:
            grain = grains_of(entry["documentId"]).get(entry["dataset"]) or grain
        except (KeyError, ValueError) as problem:
            report.error(f"{path.name}: justificativa para {problem}")
            continue
        justified.add((entry["documentId"], entry["dataset"], _key(key, grain)))
    return justified


def _key(row: dict, grain: list[str]) -> tuple:
    return tuple(str(row.get(name, "")) for name in grain)


def _describe(grain: list[str], key: tuple) -> str:
    return ", ".join(f"{name}={value}" for name, value in zip(grain, key))


def _file(folder: Path, caso: str, name: str) -> Path:
    return folder / f"{caso}_{name}.txt"


def _instant(text: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _cents(text: str) -> int | None:
    return int(text) if text.isdigit() else None


def _as_int(text: str) -> tuple[int, str]:
    return (int(text), text) if text.isdigit() else (sys.maxsize, text)


def conferir(folder: Path, caso: str, drafts_folder: Path | None = None, previous_folder: Path | None = None,
             justifications: Path | None = None) -> Report:
    report = Report()
    files: dict[str, list[list[str]]] = {}
    for name in FILES:
        path = _file(folder, caso, name)
        if not path.is_file():
            report.error(f"{path.name}: não encontrado em {folder}")
            files[name] = []
            continue
        files[name] = read_lines(path, name, report)

    drafts = read_rows(drafts_folder, "Draft", "--rascunhos", report)
    if not files["CONTAS"]:
        report.warn("CONTAS: nenhuma conta; confira os documentos e o período da ordem")
    check_numbering(files["EXTRATO"], files["ORIGEM_DESTINO"], report)
    check_membership(files, report)
    check_balances(files["EXTRATO"], files["CONTAS"], drafts, report)
    check_generic_entries(files["EXTRATO"], files["ORIGEM_DESTINO"], report)
    check_overdraft_rows(drafts, report)
    if previous_folder is None:
        if justifications is not None:
            report.error("--justificativas só vale com --anterior")
    elif drafts is None:
        report.error("--anterior compara as linhas dos rascunhos: passe também --rascunhos")
    else:
        check_resubmission(drafts, read_rows(previous_folder, "Final", "--anterior", report) or {},
                           read_justifications(justifications, report), report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pasta", type=Path)
    parser.add_argument("caso")
    parser.add_argument("--rascunhos", type=Path, help="pasta com a resposta de /rows de cada rascunho (JSON)")
    parser.add_argument("--anterior", type=Path, help="pasta com a resposta de /rows do último envio aprovado")
    parser.add_argument("--justificativas", type=Path, help="JSON com as linhas perdidas liberadas e o motivo")
    args = parser.parse_args(argv)

    report = conferir(args.pasta, args.caso, args.rascunhos, args.anterior, args.justificativas)
    for text in report.errors:
        print(f"ERRO: {text}")
    for text in report.blocks:
        print(f"BLOQUEIO: {text}")
    for text in report.released:
        print(f"LIBERADO COM JUSTIFICATIVA: {text}")
    for text in report.warnings:
        print(f"AVISO: {text}")
    print(f"{len(report.errors)} erro(s), {len(report.blocks)} bloqueio(s), {len(report.warnings)} aviso(s).")
    return 1 if report.errors or report.blocks else 0


if __name__ == "__main__":
    sys.exit(main())
