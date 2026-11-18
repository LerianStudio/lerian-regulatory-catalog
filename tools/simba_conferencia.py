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
  * linha sem CRLF ou com outro número de campos do que o Anexo I dá ao arquivo;
  * EXTRATO e ORIGEM-DESTINO com números de lançamento diferentes, ou o mesmo número
    com outro valor (um lançamento gravado entre as duas gerações desloca a
    numeração: gere os dois de novo);
  * conta do EXTRATO ou do TITULARES que não está no CONTAS; agência do CONTAS que
    não está no AGENCIAS.

AVISO (listado para o aprovador, não bloqueia):
  * último saldo do EXTRATO diferente do saldo final do CONTAS (lançamento
    retroativo, ou outra chave de saldo);
  * lançamento com o código genérico 125 ou 218 do Anexo II;
  * ORIGEM-DESTINO com a contraparte não identificada pelo trilho, ou com a
    contraparte sem CPF/CNPJ;
  * conta com saldo devedor (cheque especial usado). O CONTAS escreve o saldo sem
    sinal (o Anexo I não lhe dá sinal); o EXTRATO o mostra na natureza do saldo, mas
    a conta sem lançamento no período não aparece lá. Por isso a conferência lê
    também as linhas do rascunho do CONTAS, como o Reporter as devolve em
    `GET /v1/regulatory/reports/{reportId}/rows`, onde o saldo tem sinal. Sem esse
    arquivo, a conta sem movimento não é conferida, e a conferência diz isso.

COMPLETUDE DO REENVIO: com `--anterior`, cada arquivo é comparado linha a linha com
o do último envio aprovado, e as linhas que entraram e saíram são contadas.

Fora do alcance: valor bloqueado na conta. Nenhum dos cinco arquivos nem as linhas
do rascunho trazem esse valor.

As mensagens citam agência, conta e número da linha, nunca documento ou nome: a
saída da conferência é lida por quem aprova, e o arquivo é sigiloso.

Uso:
    python3 tools/simba_conferencia.py <pasta> <caso> [--contas-rows rows.json] [--anterior <pasta>]

A pasta tem os cinco arquivos como o script de lote os nomeia:
<caso>_AGENCIAS.txt, <caso>_CONTAS.txt, <caso>_TITULARES.txt, <caso>_EXTRATO.txt e
<caso>_ORIGEM_DESTINO.txt.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

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


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, text: str) -> None:
        self.errors.append(text)

    def warn(self, text: str) -> None:
        self.warnings.append(text)


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


def check_balances(extrato: list[list[str]], contas: list[list[str]], report: Report) -> None:
    last: dict[tuple[str, str], list[str]] = {}
    for row in extrato:
        last[(field(row, 3), field(row, 4))] = row
    final = {(field(r, 2), field(r, 3)): field(r, 11) for r in contas}
    for key, row in sorted(last.items()):
        if key in final and _cents(field(row, 12)) != _cents(final[key]):
            report.warn(f"EXTRATO: o último saldo da conta {key[1]} da agência {key[0]} é {field(row, 12)}, e o "
                        f"saldo final no CONTAS é {final[key]} (lançamento retroativo ou outra chave de saldo)")
        if field(row, 13) == "D":
            report.warn(f"EXTRATO: a conta {key[1]} da agência {key[0]} termina o período devedora (cheque especial); "
                        "o CONTAS escreve o saldo sem sinal")


def check_generic_entries(extrato: list[list[str]], od: list[list[str]], report: Report) -> None:
    for line, row in enumerate(extrato, 1):
        if field(row, 9) in GENERIC_CODES:
            report.warn(f"EXTRATO:{line}: o lançamento {field(row, 1)} tem o código genérico {field(row, 9)}")
    for line, row in enumerate(od, 1):
        if field(row, 18) == UNIDENTIFIED:
            report.warn(f"ORIGEM_DESTINO:{line}: o lançamento {field(row, 2)} tem a contraparte não identificada pelo trilho")
        elif not field(row, 10):
            report.warn(f"ORIGEM_DESTINO:{line}: a contraparte do lançamento {field(row, 2)} está sem CPF/CNPJ")


def check_overdraft_rows(path: Path | None, report: Report) -> None:
    if path is None:
        report.warn("CONTAS: sem as linhas do rascunho (--contas-rows), a conta com saldo devedor e sem "
                    "lançamento no período NÃO foi conferida")
        return
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        datasets = document["datasets"]
    except (OSError, ValueError, KeyError, TypeError) as problem:
        report.error(f"{path.name}: não é a resposta de /rows do rascunho do CONTAS ({problem})")
        return
    for name in CONTAS_SETS:
        for row in datasets.get(name) or []:
            for balance, label in (("saldoInicial", "inicial"), ("saldoFinal", "final")):
                value = str(row.get(balance) or "")
                if value.startswith("-"):
                    report.warn(f"CONTAS: a conta {row.get('numeroConta')} da agência {row.get('numeroAgencia')} tem "
                                f"saldo {label} devedor ({value}); o arquivo o escreve sem sinal")


def check_resubmission(folder: Path, previous: Path, caso: str, report: Report) -> None:
    for name in FILES:
        now, before = _file(folder, caso, name), _find_previous(previous, name)
        if before is None:
            report.warn(f"{name}: não há arquivo do envio anterior em {previous}")
            continue
        current = Counter(now.read_bytes().split(b"\r\n"))
        old = Counter(before.read_bytes().split(b"\r\n"))
        added, removed = sum((current - old).values()), sum((old - current).values())
        if added or removed:
            report.warn(f"{name}: em relação ao envio anterior, {added} linha(s) entraram e {removed} saíram")


def _file(folder: Path, caso: str, name: str) -> Path:
    return folder / f"{caso}_{name}.txt"


def _find_previous(folder: Path, name: str) -> Path | None:
    found = sorted(folder.glob(f"*_{name}.txt"))
    return found[0] if len(found) == 1 else None


def _cents(text: str) -> int | None:
    return int(text) if text.isdigit() else None


def _as_int(text: str) -> tuple[int, str]:
    return (int(text), text) if text.isdigit() else (sys.maxsize, text)


def conferir(folder: Path, caso: str, contas_rows: Path | None = None, previous: Path | None = None) -> Report:
    report = Report()
    files: dict[str, list[list[str]]] = {}
    for name in FILES:
        path = _file(folder, caso, name)
        if not path.is_file():
            report.error(f"{path.name}: não encontrado em {folder}")
            files[name] = []
            continue
        files[name] = read_lines(path, name, report)

    check_numbering(files["EXTRATO"], files["ORIGEM_DESTINO"], report)
    check_membership(files, report)
    check_balances(files["EXTRATO"], files["CONTAS"], report)
    check_generic_entries(files["EXTRATO"], files["ORIGEM_DESTINO"], report)
    check_overdraft_rows(contas_rows, report)
    if previous is not None:
        check_resubmission(folder, previous, caso, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pasta", type=Path)
    parser.add_argument("caso")
    parser.add_argument("--contas-rows", type=Path, help="resposta de /rows do rascunho do CONTAS (JSON)")
    parser.add_argument("--anterior", type=Path, help="pasta com os arquivos do último envio aprovado")
    args = parser.parse_args(argv)

    report = conferir(args.pasta, args.caso, args.contas_rows, args.anterior)
    for text in report.errors:
        print(f"ERRO: {text}")
    for text in report.warnings:
        print(f"AVISO: {text}")
    print(f"{len(report.errors)} erro(s), {len(report.warnings)} aviso(s).")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
