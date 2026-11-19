#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""Gera, da lista de participantes do Pix que o BCB publica, os trechos de template que
trocam o ISPB de uma instituição pelo CNPJ dela.

O ORIGEM-DESTINO do SIMBA pede o CNPJ da instituição da contraparte (IN BCB 636/2025,
Anexo I, ORIGEM-DESTINO campo 19), e os trilhos de pagamento guardam só o ISPB. A
tabela é do REGULADOR: o catálogo publica a cópia que baixou, byte a byte, em
br/bcb/simba/tabelas/ParticipantesPix.csv, e os trechos do template nunca são escritos
à mão. Vale o CNPJ que a lista dá; nada é derivado do ISPB.

Dois trechos, cada um entre as suas marcas, com a expressão que dá o ISPB:

    {# ISPB_CNPJ_BLOCK: ispb #}…{# /ISPB_CNPJ_BLOCK #}
        o CNPJ (14 caracteres, sem separadores), ou nada;
    {# ISPB_CNPJ_REASON: ispb observacao #}…{# /ISPB_CNPJ_REASON #}
        nada, ou o motivo do CNPJ em branco, depois de "; " quando a expressão
        `observacao` já tem texto.

Esta ferramenta reescreve o que fica entre as marcas; sem a marca de fim, insere o
trecho e a marca logo depois da de início. O validador confere que o que está lá é
exatamente o que ela gera.

Os trechos:
  * ISPB vazio ou ausente fica sem CNPJ, ANTES de completar com zeros (o texto vazio
    viraria 00000000, que é o Banco do Brasil);
  * o ISPB é completado a 8 dígitos (`%08v`), como no trecho do Compe;
  * só a seção dos participantes ativos conta (a lista traz depois as instituições em
    processo de adesão, que ainda não transacionam Pix);
  * ISPB fora da lista fica sem CNPJ, e o motivo diz isso.

Uso:
    python3 tools/ispb_cnpj.py
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TABLE = ROOT / "br" / "bcb" / "simba" / "tabelas" / "ParticipantesPix.csv"
# A cópia publicada, como o BCB a serve. Trocar a tabela é decisão: o sha256 muda aqui
# junto, e os trechos são regerados.
TABLE_SHA256 = "4dd1890d0a49c169ac9ddb77f21b1fe48a580dce6f9083def9e2166da637c5e4"
TEMPLATES = ROOT / "br" / "bcb" / "simba"

# O cabeçalho da seção dos participantes ativos (a primeira da lista).
ACTIVE_TITLE = "Lista de participantes ativos do Pix"
HEADER = ";Nome Reduzido;ISPB;CNPJ;"
REASON = "CNPJ da instituicao da contraparte nao informado: ISPB ausente ou fora da lista de participantes do Pix"

EXPR = r"[A-Za-z_][A-Za-z0-9_.]*"
BEGIN = re.compile(r"\{# ISPB_CNPJ_BLOCK: (" + EXPR + r") #\}")
END = "{# /ISPB_CNPJ_BLOCK #}"
BEGIN_REASON = re.compile(r"\{# ISPB_CNPJ_REASON: (" + EXPR + r") (" + EXPR + r") #\}")
END_REASON = "{# /ISPB_CNPJ_REASON #}"
TOKENS = ("ISPB_CNPJ_BLOCK", "ISPB_CNPJ_REASON")


class TableError(Exception):
    """A tabela publicada não é a esperada, ou traz uma linha que não se lê."""


def read_cnpjs(path: Path = TABLE, sha256: str = TABLE_SHA256) -> dict[str, str]:
    """ISPB (8 dígitos) → CNPJ (14 caracteres, sem separadores), dos participantes ativos."""
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != sha256:
        raise TableError(f"{path.name} tem sha256 {digest}, e não {sha256}; trocar a tabela é decisão")

    lines = raw.decode("iso-8859-1").splitlines()
    if not lines or lines[0].strip() != ACTIVE_TITLE:
        raise TableError(f"{path.name} não começa pela seção {ACTIVE_TITLE!r}")
    if len(lines) < 2 or HEADER not in lines[1]:
        raise TableError(f"{path.name}:2: o cabeçalho não traz as colunas Nome Reduzido, ISPB e CNPJ")

    cnpjs: dict[str, str] = {}
    for number, line in enumerate(lines[2:], start=3):
        if not line.strip():
            break  # fim da seção dos ativos
        fields = line.split(";")
        if len(fields) < 4:
            raise TableError(f"{path.name}:{number}: {len(fields)} colunas")
        ispb, cnpj = fields[2].strip(), re.sub(r"[./-]", "", fields[3].strip())
        if not ispb:
            continue  # participante ativo sem ISPB próprio na lista: nada a traduzir
        if not re.fullmatch(r"[0-9]{8}", ispb):
            raise TableError(f"{path.name}:{number}: ISPB {ispb!r} não tem 8 dígitos")
        if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", cnpj):
            raise TableError(f"{path.name}:{number}: CNPJ {fields[3]!r} do ISPB {ispb} não tem 14 caracteres")
        if ispb in cnpjs:
            raise TableError(f"{path.name}:{number}: ISPB {ispb} repetido")
        cnpjs[ispb] = cnpj
    if not cnpjs:
        raise TableError(f"{path.name} não traz participante ativo com ISPB")
    return cnpjs


def _chain(expression: str, cnpjs: dict[str, str], found, missing: str) -> str:
    groups: dict[str, list[str]] = {}
    for ispb in sorted(cnpjs):
        groups.setdefault(ispb[:2], []).append(ispb)
    branches = []
    for prefix, entries in groups.items():
        inner = "".join(("{% if" if i == 0 else "{% elif") + f' cnpj_k == "{ispb}" %}}{found(cnpjs[ispb])}'
                        for i, ispb in enumerate(entries))
        branches.append(f'cnpj_p == "{prefix}" %}}{inner}{{% else %}}{missing}{{% endif %}}')
    chain = "{% if " + "{% elif ".join(branches) + f"{{% else %}}{missing}{{% endif %}}"
    return (f'{{% if {expression} == None or {expression} == "" %}}{missing}{{% else %}}'
            f'{{% with cnpj_k={expression}|stringformat:"%08v" %}}'
            f'{{% with cnpj_p=cnpj_k|slice:":2" %}}{chain}{{% endwith %}}{{% endwith %}}{{% endif %}}')


def render_block(expression: str, cnpjs: dict[str, str]) -> str:
    """O trecho que escreve o CNPJ do ISPB em `expression`, ou nada."""
    return _chain(expression, cnpjs, lambda cnpj: cnpj, "")


def render_reason(expression: str, previous: str, cnpjs: dict[str, str]) -> str:
    """O trecho que escreve o motivo do CNPJ em branco, depois de "; " se `previous` tem texto."""
    missing = f"{{% if {previous} %}}; {{% endif %}}{REASON}"
    return _chain(expression, cnpjs, lambda cnpj: "", missing)


def _regenerate(text: str, begin: re.Pattern, end: str, render) -> str:
    out, at = [], 0
    for match in begin.finditer(text):
        if match.start() < at:
            continue
        out.append(text[at:match.end()])
        out.append(render(*match.groups()) + end)
        close = text.find(end, match.end())
        following = begin.search(text, match.end())
        at = close + len(end) if close != -1 and (following is None or close < following.start()) else match.end()
    out.append(text[at:])
    return "".join(out)


def expected_template(text: str, cnpjs: dict[str, str]) -> str:
    """O template com cada trecho marcado regerado da tabela."""
    text = _regenerate(text, BEGIN, END, lambda expression: render_block(expression, cnpjs))
    return _regenerate(text, BEGIN_REASON, END_REASON,
                       lambda expression, previous: render_reason(expression, previous, cnpjs))


def malformed_markers(text: str) -> int:
    """Quantas menções às marcas não são uma marca de início ou de fim bem escrita."""
    wellformed = (len(BEGIN.findall(text)) + text.count(END)
                  + len(BEGIN_REASON.findall(text)) + text.count(END_REASON))
    return sum(text.count(token) for token in TOKENS) - wellformed


def marked_templates() -> list[Path]:
    return sorted(p for p in TEMPLATES.glob("*/template.tpl")
                  if any(token in p.read_text(encoding="utf-8") for token in TOKENS))


def main() -> int:
    try:
        cnpjs = read_cnpjs()
    except (OSError, TableError) as problem:
        print(f"erro: {problem}", file=sys.stderr)
        return 1
    for path in marked_templates():
        # newline="" preserva o CRLF das linhas do arquivo gerado.
        with path.open(encoding="utf-8", newline="") as handle:
            text = handle.read()
        regenerated = expected_template(text, cnpjs)
        if regenerated != text:
            with path.open("w", encoding="utf-8", newline="") as handle:
                handle.write(regenerated)
            print(f"{path.relative_to(ROOT)}: trechos ISPB→CNPJ regerados ({len(cnpjs)} participantes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
