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
  * documento da ordem sem nenhuma conta nos arquivos (`--documentos`): o Reporter não
    confere o CPF/CNPJ de cada documento, então um documento digitado errado só não
    acha conta, e o caso sai como resposta negativa para ele. O aviso diz a posição do
    documento na lista, nunca o documento;
  * CONTAS sem conta nenhuma: confira os documentos da ordem;
  * último saldo do EXTRATO diferente do saldo final do CONTAS (lançamento
    retroativo, ou outra chave de saldo). Com as linhas dos rascunhos, o último é o
    de maior instante (`horaLancamento`), e o saldo é o do campo 12 (disponível +
    bloqueado − cheque especial usado); sem elas, a última linha do arquivo, que pode
    não ser a mais recente (uma transação pendente confirmada depois);
  * lançamento com o código genérico 125 ou 218 do Anexo II;
  * ORIGEM-DESTINO com a contraparte não identificada pelo trilho, ou com a
    contraparte sem CPF/CNPJ;
  * conta com saldo inicial ou final devedor (cheque especial). O CONTAS escreve o
    saldo sem sinal (o Anexo I não lhe dá sinal), e a conta sem lançamento no período
    não aparece no EXTRATO. Por isso a conferência lê as linhas do rascunho do CONTAS,
    como o Reporter as devolve em `GET /v1/regulatory/reports/{reportId}/rows`, onde o
    saldo tem sinal. Sem elas, o saldo devedor não é conferido, e a conferência diz isso;
  * pelas linhas do rascunho do EXTRATO: a parcela de cheque especial que o Midaz grava
    em operação separada (chave overdraft), que sai como lançamento próprio e, numa
    transferência interna, sem contraparte no ORIGEM-DESTINO; conta que usou cheque especial no período ou
    teve valor bloqueado depois de algum lançamento (o saldo final pode não mostrar
    nenhum dos dois), e lançamento sem o cheque especial usado (operação gravada antes
    de o Midaz guardar o snapshot), cujo saldo sai sem ele. Sem essas linhas, nada
    disso é conferido, e a conferência diz isso;
  * TITULARES sem documento de identificação (campos 10 e 11) ou sem dispositivo
    cadastrado (26 e 27): nenhuma aplicação Lerian registra esses dados, então o aviso
    sai em todo caso, por desenho, para quem aprova saber o que vai em branco.

BLOQUEIO (completude do reenvio): com `--anterior`, as linhas de cada rascunho são
comparadas com as do último envio aprovado (Final) do mesmo caso, conjunto a
conjunto, pela chave do grão que o contrato declara. Uma chave do Final que falta no
rascunho novo é uma linha que o reenvio perdeu (um cadastro apagado, um lançamento
estornado na base, um binding alterado) e BLOQUEIA a aprovação, a menos que o
arquivo de justificativas a libere com o motivo registrado. Um conjunto do envio
anterior que o contrato atual não tem, um documento sem rascunho novo ou um rascunho
sem o envio anterior na pasta também bloqueia. Uma chave nova é só aviso. A pasta de
`--anterior` traz o ÚLTIMO envio aprovado, uma resposta por documento, com status
Final; quem roda a conferência a escolhe, e o script recusa pasta vazia, status que
não seja Final e documento repetido.

Fora do alcance: valor bloqueado em conta sem lançamento no período. As linhas do
rascunho do CONTAS não trazem o bloqueado, e a conta não aparece no EXTRATO.

As mensagens citam agência, conta e número da linha, nunca documento ou nome: a
saída da conferência é lida por quem aprova, e o arquivo é sigiloso.

Uso:
    python3 tools/simba_conferencia.py <pasta> <caso> [--rascunhos <pasta>]
        [--anterior <pasta> [--justificativas <arquivo>]] [--documentos <arquivo>]

A pasta tem os cinco arquivos como o script de lote os nomeia:
<caso>_AGENCIAS.txt, <caso>_CONTAS.txt, <caso>_TITULARES.txt, <caso>_EXTRATO.txt e
<caso>_ORIGEM_DESTINO.txt. `--rascunhos` e `--anterior` são pastas com a resposta de
`/rows` de cada documento (um JSON por documento, o nome do arquivo não importa: o
documento sai do `documentId`). `--justificativas` é um JSON com a lista
`[{"documentId", "dataset", "key": {campo: valor}, "motivo"}]`, e só vale com
`--anterior`. `--documentos` é um arquivo com os documentos da ordem, um por linha, na
ordem em que foram passados à geração.

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
# A chave de saldo em que o Midaz grava a parte de um saque tirada do cheque especial.
OVERDRAFT_KEY = "overdraft"


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
                        "transação confirmada depois de outra: sem as linhas dos rascunhos do EXTRATO e do CONTAS, "
                        "o último é a última linha do arquivo)")


def _check_balances_by_instant(entries: list[dict], accounts: dict, report: Report) -> None:
    last: dict[tuple[str, str], tuple[datetime, Decimal | None]] = {}
    for row in entries:
        key = (str(row.get("numeroAgencia")), str(row.get("numeroConta")))
        instant = _instant(row.get("horaLancamento"))
        if instant is None:
            report.error(f"EXTRATO: um lançamento da conta {key[1]} da agência {key[0]} não tem instante legível")
            continue
        if key not in last or instant >= last[key][0]:
            last[key] = (instant, _account_balance(row))
    final = {(str(r.get("numeroAgencia")), str(r.get("numeroConta"))): r.get("saldoFinal")
             for name in CONTAS_SETS for r in accounts.get(name) or []}
    for key, (_, balance) in sorted(last.items()):
        if key not in final:
            continue
        expected = _decimal(str(final[key])) if final[key] not in (None, "") else None
        if balance is None or expected is None:
            report.warn(f"EXTRATO: o saldo da conta {key[1]} da agência {key[0]} não pôde ser comparado: um dos "
                        "saldos está ausente nas linhas dos rascunhos")
        elif balance != expected:
            report.warn(f"EXTRATO: o saldo após o último lançamento da conta {key[1]} da agência {key[0]} é {balance}, "
                        f"e o saldo final no CONTAS é {expected} (lançamento retroativo ou outra chave de saldo)")


def check_entry_balances(drafts: dict[str, dict] | None, report: Report) -> None:
    """Cheque especial usado, valor bloqueado e operação sem snapshot, pelas linhas do EXTRATO."""
    entries = (drafts or {}).get(EXTRATO_DOCUMENT, {}).get(EXTRATO_ENTRIES)
    if entries is None:
        report.warn("EXTRATO: sem as linhas do rascunho do EXTRATO (--rascunhos), o cheque especial usado, o valor "
                    "bloqueado e os lançamentos sem o cheque especial medido NÃO foram conferidos")
        return
    used: set[tuple[str, str]] = set()
    held: set[tuple[str, str]] = set()
    unmeasured: dict[tuple[str, str], int] = {}
    for row in entries:
        key = (str(row.get("numeroAgencia")), str(row.get("numeroConta")))
        if row.get("chequeEspecialApos") in (None, ""):
            unmeasured[key] = unmeasured.get(key, 0) + 1
        elif (_decimal(str(row.get("chequeEspecialApos"))) or Decimal(0)) > 0:
            used.add(key)
        if (_decimal(str(row.get("bloqueadoApos") or "0")) or Decimal(0)) > 0:
            held.add(key)
    for row in entries:
        if row.get("chaveSaldo") == OVERDRAFT_KEY:
            report.warn(f"EXTRATO: a conta {row.get('numeroConta')} da agência {row.get('numeroAgencia')} tem uma parcela "
                        f"de cheque especial de {row.get('valor')} em lançamento separado; revise a contraparte no "
                        "ORIGEM-DESTINO: numa transferência interna, a parcela sai como não identificada pelo trilho")
    for key in sorted(used):
        report.warn(f"EXTRATO: a conta {key[1]} da agência {key[0]} usou cheque especial no período")
    for key in sorted(held):
        report.warn(f"EXTRATO: a conta {key[1]} da agência {key[0]} teve valor bloqueado no período")
    for key, count in sorted(unmeasured.items()):
        report.warn(f"EXTRATO: {count} lançamento(s) da conta {key[1]} da agência {key[0]} sem o cheque especial "
                    "usado (operação anterior ao snapshot do Midaz); o saldo deles sai sem ele")


def _account_balance(row: dict) -> Decimal | None:
    """O saldo da conta do campo 12: disponível + bloqueado − cheque especial usado (ausente conta 0)."""
    available = _decimal(str(row.get("saldoApos"))) if row.get("saldoApos") not in (None, "") else None
    if available is None:
        return None
    held = _decimal(str(row.get("bloqueadoApos") or "0")) or Decimal(0)
    used = _decimal(str(row.get("chequeEspecialApos") or "0")) or Decimal(0)
    return available + held - used


def check_case_documents(path: Path | None, titulares: list[list[str]], report: Report) -> None:
    """Cada documento da ordem aparece como titular de alguma conta no TITULARES."""
    if path is None:
        report.warn("TITULARES: sem --documentos, o documento da ordem sem nenhuma conta NÃO foi conferido")
        return
    try:
        documents = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError) as problem:
        report.error(f"--documentos: {path.name} não se lê ({problem})")
        return
    if not documents:
        report.error(f"--documentos: {path.name} não traz documento nenhum")
        return
    # O TITULARES já escreve o documento só com dígitos (e letras, no CNPJ alfanumérico).
    holders = {field(r, 8) for r in titulares}
    missing = [str(i) for i, document in enumerate(documents, 1) if _digits(document) not in holders]
    if missing:
        report.warn(f"TITULARES: o(s) documento(s) nº {', '.join(missing)} da ordem (posição em --documentos) não "
                    "titula(m) conta nenhuma nos arquivos; confira se foi digitado certo antes de aprovar uma "
                    "resposta negativa")


def _digits(text: str) -> str:
    return "".join(c for c in text if c.isalnum()).upper()


def check_identity(titulares: list[list[str]], report: Report) -> None:
    """Identificação e dispositivos que o TITULARES deixa em branco, contados por arquivo."""
    without_id = sum(1 for r in titulares if not field(r, 10) and not field(r, 11))
    without_device = sum(1 for r in titulares if not field(r, 26) and not field(r, 27))
    if without_id:
        report.warn(f"TITULARES: {without_id} linha(s) sem documento de identificação (campos 10 e 11; "
                    "nenhuma aplicação Lerian registra esse dado)")
    if without_device:
        report.warn(f"TITULARES: {without_device} linha(s) sem dispositivo cadastrado (campos 26 e 27; "
                    "nenhuma aplicação Lerian registra esse dado)")


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
    for document in sorted(set(drafts) - set(previous)):
        report.block(f"{document}: há rascunho novo e a pasta do envio anterior não traz o Final dele")
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
    """O instante, só com fuso: sem ele não se compara com os outros."""
    try:
        instant = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return instant if instant.tzinfo is not None else None


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
             justifications: Path | None = None, documents: Path | None = None) -> Report:
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
    check_identity(files["TITULARES"], report)
    check_case_documents(documents, files["TITULARES"], report)
    check_entry_balances(drafts, report)
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
    parser.add_argument("--documentos", type=Path, help="os documentos da ordem, um por linha")
    args = parser.parse_args(argv)

    report = conferir(args.pasta, args.caso, args.rascunhos, args.anterior, args.justificativas, args.documentos)
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
