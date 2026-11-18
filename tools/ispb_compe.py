#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""Gera, da lista de participantes do STR que o BCB publica, o trecho de template que
troca o ISPB de uma instituição pelo seu código COMPE.

O ORIGEM-DESTINO do SIMBA pede o código COMPE da instituição da contraparte (IN BCB
636/2025, Anexo I, ORIGEM-DESTINO campo 5), e os trilhos de pagamento guardam o ISPB.
A tabela é do REGULADOR: o catálogo publica a cópia que baixou, byte a byte, em
br/bcb/simba/tabelas/ParticipantesSTR.csv, e o trecho do template nunca é escrito à mão.

O template marca onde o trecho entra, com a expressão que dá o ISPB:

    {# ISPB_COMPE_BLOCK: ispb #}…{# /ISPB_COMPE_BLOCK #}

Esta ferramenta reescreve o que fica entre as duas marcas; sem a marca de fim, insere o
trecho e a marca logo depois da de início. O validador confere que o que está lá é
exatamente o que ela gera.

O trecho:
  * ISPB vazio ou ausente sai 999, ANTES de completar com zeros: sem essa guarda, o
    texto vazio viraria 00000000, que é o Banco do Brasil;
  * o ISPB é completado a 8 dígitos (`%08v`), porque um valor numérico perde os zeros
    à esquerda;
  * a cadeia de comparações é agrupada pelos dois primeiros dígitos, e fica em linha,
    sem `macro`, para rodar também na pré-visualização do manager;
  * ISPB fora da lista, ou de participante sem código (`n/a`, `0` na coluna
    Número_Código), sai 999. Participante que não está na COMPE mas tem código sai com
    o código.

Uso:
    python3 tools/ispb_compe.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TABLE = ROOT / "br" / "bcb" / "simba" / "tabelas" / "ParticipantesSTR.csv"
# A cópia publicada, como o BCB a serve. Trocar a tabela é decisão: o sha256 muda aqui
# junto, e o trecho é regerado.
TABLE_SHA256 = "1e5c5f84d8cc4389864df50965c4fa00b4e7f954533fe7d7e5e857381c5de6e8"
TEMPLATES = ROOT / "br" / "bcb" / "simba"

UNKNOWN = "999"
# O que a coluna Número_Código traz para o participante sem código.
NO_CODE = {"n/a", "0"}

BEGIN = re.compile(r"\{# ISPB_COMPE_BLOCK: ([A-Za-z_][A-Za-z0-9_.]*) #\}")
END = "{# /ISPB_COMPE_BLOCK #}"
TOKEN = "ISPB_COMPE_BLOCK"


class TableError(Exception):
    """A tabela publicada não é a esperada, ou traz uma linha que não se lê."""


def read_codes(path: Path = TABLE) -> dict[str, str]:
    """ISPB (8 dígitos) → código COMPE (3 dígitos), só dos participantes com código."""
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != TABLE_SHA256:
        raise TableError(f"{path.name} tem sha256 {digest}, e não {TABLE_SHA256}; trocar a tabela é decisão")

    codes: dict[str, str] = {}
    for line, row in enumerate(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))), start=2):
        ispb = (row.get("ISPB") or "").strip()
        code = (row.get("Número_Código") or "").strip()
        if not re.fullmatch(r"[0-9]{8}", ispb):
            raise TableError(f"{path.name}:{line}: ISPB {ispb!r} não tem 8 dígitos")
        if ispb in codes:
            raise TableError(f"{path.name}:{line}: ISPB {ispb} repetido")
        if code in NO_CODE:
            continue
        if not re.fullmatch(r"[0-9]{3}", code):
            raise TableError(f"{path.name}:{line}: código {code!r} do ISPB {ispb} não é n/a, 0 nem 3 dígitos")
        codes[ispb] = code
    if not codes:
        raise TableError(f"{path.name} não traz participante com código")
    return codes


def render_block(expression: str, codes: dict[str, str]) -> str:
    """O trecho que escreve o código COMPE do ISPB em `expression`, numa linha só."""
    groups: dict[str, list[tuple[str, str]]] = {}
    for ispb in sorted(codes):
        groups.setdefault(ispb[:2], []).append((ispb, codes[ispb]))

    branches = []
    for prefix, entries in groups.items():
        inner = "".join(
            ("{% if" if i == 0 else "{% elif") + f' compe_k == "{ispb}" %}}{code}'
            for i, (ispb, code) in enumerate(entries))
        branches.append(f'compe_p == "{prefix}" %}}{inner}{{% else %}}{UNKNOWN}{{% endif %}}')
    chain = "{% if " + "{% elif ".join(branches) + f"{{% else %}}{UNKNOWN}{{% endif %}}"

    return (f'{{% if {expression} == None or {expression} == "" %}}{UNKNOWN}{{% else %}}'
            f'{{% with compe_k={expression}|stringformat:"%08v" %}}'
            f'{{% with compe_p=compe_k|slice:":2" %}}{chain}{{% endwith %}}{{% endwith %}}{{% endif %}}')


def expected_template(text: str, codes: dict[str, str]) -> str:
    """O template com cada trecho marcado regerado da tabela."""
    out, at = [], 0
    for begin in BEGIN.finditer(text):
        if begin.start() < at:
            continue
        out.append(text[at:begin.end()])
        out.append(render_block(begin.group(1), codes) + END)
        end = text.find(END, begin.end())
        next_begin = BEGIN.search(text, begin.end())
        if end != -1 and (next_begin is None or end < next_begin.start()):
            at = end + len(END)
        else:
            at = begin.end()
    out.append(text[at:])
    return "".join(out)


def malformed_markers(text: str) -> int:
    """Quantas menções à marca não são uma marca de início ou de fim bem escrita.

    Uma marca escrita diferente (sem o espaço, com outra expressão) não é achada pelo
    gerador nem conferida pelo validador: o trecho ao lado dela passaria sem conferência.
    """
    wellformed = len(BEGIN.findall(text)) + text.count(END)
    return text.count(TOKEN) - wellformed


def marked_templates() -> list[Path]:
    return sorted(p for p in TEMPLATES.glob("*/template.tpl")
                  if BEGIN.search(p.read_text(encoding="utf-8")))


def main() -> int:
    try:
        codes = read_codes()
    except (OSError, TableError) as problem:
        print(f"erro: {problem}", file=sys.stderr)
        return 1
    for path in marked_templates():
        # newline="" preserva o CRLF das linhas do arquivo gerado.
        with path.open(encoding="utf-8", newline="") as handle:
            text = handle.read()
        regenerated = expected_template(text, codes)
        if regenerated != text:
            with path.open("w", encoding="utf-8", newline="") as handle:
                handle.write(regenerated)
            print(f"{path.relative_to(ROOT)}: trecho ISPB→COMPE regerado ({len(codes)} códigos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
