#!/usr/bin/env python3
"""Gera a tabela de naturezas do COSIF a partir do elenco de contas do BACEN.

A natureza de uma rubrica — o lado em que o saldo dela normalmente fica — é do
PLANO COSIF, não do cliente: o elenco publicado pelo BACEN diz quais contas são
retificadoras. O cliente que lança na rubrica certa fez tudo o que lhe cabe. Por
isso a tabela é curadoria do catálogo e viaja com o contrato (`nature:`), e o
binding de referência só diz em que coluna está o código.

COMO O ELENCO DIZ A NATUREZA, e a regra que este script aplica:

  * A seção dá o lado normal: I - ATIVO (grupos 1, 2 e 3) é devedor; II - PASSIVO
    (grupos 4, 6, 7 e 9) é credor.
  * "(-)" no título inverte o lado da seção: é a retificadora — provisão, perda
    esperada, depreciação acumulada no ativo; capital a realizar, ações em
    tesouraria no patrimônio líquido.
  * "(+/-)" é bilateral: o saldo pode estar de qualquer lado. Herda o lado da
    conta-mãe, então um saldo do lado contrário sai negativo, que é o que ele é.
  * O GRUPO 8 (Resultado Devedor) é devedor INTEIRO. O elenco escreve "(-)" em
    quase todas as despesas — a marca ali diz "subtrai do resultado", não
    "retificadora" —, e as poucas sem a marca são, na maioria, omissões do próprio
    elenco (uma conta-mãe sem marca com todas as filhas marcadas). Seguir a marca
    no grupo 8 trocaria o sinal dessas linhas. As contas sem marca ficam listadas
    no cabeçalho do arquivo gerado, para revisão.

A TABELA É MÍNIMA: o lado de cada grupo e, abaixo dele, só as rubricas cujo lado
difere do da conta-mãe mais próxima já declarada. O motor decide pelo PREFIXO MAIS
LONGO que casa com o código, então uma retificadora declarada pelo próprio prefixo
vence o grupo em que está, e as filhas dela a herdam.

O prefixo é o código sem pontuação e sem dígito verificador, cortado nos níveis
zerados à direita (1.6.1.20.01.60-9 → 161200160; 1.2.6.99.00.00-? → 12699). Os
níveis do COSIF têm largura fixa (1-1-1-2-2-2), então um prefixo assim é
exatamente a subárvore da rubrica.

Uso:
    pip install pypdf
    python3 tools/natureza.py br/bcb/cosif/elenco-contas.pdf

Escreve `natureza.yaml` em todo documento cujo contrato declara `nature.from:
natureza.yaml`, idêntico em todos. O validador confere que as cópias são iguais e
que o sha256 do cabeçalho é o do PDF publicado no catálogo.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOURCE_URL = "https://www3.bcb.gov.br/aplica/cosif/manual/completo_contas.pdf"
TABLE_FILE = "natureza.yaml"

# O lado normal de cada grupo, pela seção do elenco em que ele está.
GROUP_SIDE = {
    "1": "debit", "2": "debit", "3": "debit",
    "4": "credit", "6": "credit", "7": "credit", "9": "credit",
    # Resultado Devedor: devedor inteiro, ver o cabeçalho deste script.
    "8": "debit",
}
WHOLE_GROUPS = {"8"}

ACCOUNT_LINE = re.compile(r"^(\d\.\d\.\d\.\d\d\.\d\d\.\d\d-\d)\s+(.*)$")
LEVEL_WIDTHS = (1, 1, 1, 2, 2, 2)


def flip(side: str) -> str:
    return "credit" if side == "debit" else "debit"


def prefix_of(code: str) -> str:
    """O código sem pontuação nem dígito verificador, cortado nos níveis zerados."""
    digits = code.split("-")[0].replace(".", "")
    levels, at = [], 0
    for width in LEVEL_WIDTHS:
        levels.append(digits[at:at + width])
        at += width
    while len(levels) > 1 and set(levels[-1]) == {"0"}:
        levels.pop()
    return "".join(levels)


def marker(title: str) -> str:
    """'contra' para "(-)", 'bilateral' para "(+/-)", '' sem marca.

    Os espaços somem antes da comparação: a extração do PDF escreve "(- )" numa
    linha ou outra, e a marca é a mesma.
    """
    compact = re.sub(r"\s", "", title)
    if compact.startswith("(-)"):
        return "contra"
    if compact.startswith("(+/-)") or compact.startswith("(+-)"):
        return "bilateral"
    return ""


def parse_elenco(text: str) -> list[tuple[str, str]]:
    """As rubricas do elenco, como (código, título), na ordem em que aparecem."""
    accounts = []
    for line in text.splitlines():
        match = ACCOUNT_LINE.match(line.strip())
        if match:
            # O elenco imprime, depois do título, a coluna de atributos (um
            # traço ou o código do grupo de balanço, "  411"); não é título.
            title = re.sub(r"\s+(-|\d{3})\s*$", "", match.group(2)).strip()
            accounts.append((match.group(1), title))
    return accounts


def natures_of(accounts: list[tuple[str, str]]) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """O lado de cada rubrica, por prefixo, e as contas do grupo 8 sem marca.

    As rubricas chegam na ordem do elenco, que é a da árvore: toda conta-mãe vem
    antes das filhas. Uma rubrica sem marca, ou bilateral, herda o lado da mãe
    mais próxima; uma retificadora inverte o lado da SEÇÃO.
    """
    sides: dict[str, str] = {}
    unmarked_in_whole: list[tuple[str, str]] = []

    for code, title in accounts:
        group = code[0]
        if group not in GROUP_SIDE:
            raise SystemExit(f"rubrica {code} está num grupo que o elenco não tinha: {group}")

        prefix = prefix_of(code)
        kind = marker(title)

        if group in WHOLE_GROUPS:
            sides[prefix] = GROUP_SIDE[group]
            if kind == "":
                unmarked_in_whole.append((code, title))
            continue

        if kind == "contra":
            sides[prefix] = flip(GROUP_SIDE[group])
            continue

        parent = nearest(sides, prefix)
        sides[prefix] = sides[parent] if parent else GROUP_SIDE[group]

    return sides, unmarked_in_whole


def nearest(table: dict[str, str], prefix: str) -> str | None:
    """O prefixo mais longo da tabela que é prefixo próprio deste."""
    for length in range(len(prefix) - 1, 0, -1):
        if prefix[:length] in table:
            return prefix[:length]
    return None


def minimal_table(sides: dict[str, str]) -> dict[str, str]:
    """O lado de cada grupo e só as rubricas que diferem da mãe já declarada."""
    table = {group: side for group, side in GROUP_SIDE.items()}
    for prefix in sorted(sides, key=lambda p: (len(p), p)):
        if prefix in table:
            continue
        parent = nearest(table, prefix)
        if parent is None or table[parent] != sides[prefix]:
            table[prefix] = sides[prefix]
    return table


def decide(table: dict[str, str], code_prefix: str) -> str:
    """O lado que o MOTOR dá a um código: o prefixo mais longo que casa."""
    best = ""
    for prefix in table:
        if code_prefix.startswith(prefix) and len(prefix) > len(best):
            best = prefix
    return table[best]


def render(table: dict[str, str], titles: dict[str, tuple[str, str]],
           unmarked: list[tuple[str, str]], digest: str) -> str:
    lines = [
        "# Natureza das rubricas do COSIF — o lado em que o saldo de cada uma",
        "# normalmente fica. GERADO por tools/natureza.py a partir do elenco de contas",
        "# publicado pelo BACEN; não edite à mão, regere.",
        "#",
        "# É dado do PLANO COSIF, não do cliente: o elenco diz quais rubricas são",
        "# retificadoras. O motor decide pelo prefixo mais longo que casa com o código,",
        "# então uma retificadora declarada abaixo vence o grupo em que está.",
        "#",
        "# Regra: ativo (1, 2, 3) devedor; passivo, PL, resultado credor e compensação",
        "# (4, 6, 7, 9) credores; \"(-)\" no título inverte; \"(+/-)\" herda a mãe; o grupo 8",
        "# (resultado devedor) é devedor inteiro — ver tools/natureza.py.",
    ]
    if unmarked:
        lines += [
            "#",
            "# Grupo 8 sem a marca \"(-)\" no elenco, tratadas como devedoras (revisar):",
        ]
        lines += [f"#   {code}  {title}" for code, title in unmarked]
    lines += [
        "",
        f"source: {SOURCE_URL}",
        f"sha256: {digest}",
        "",
        "byPrefix:",
    ]
    for prefix in sorted(table):
        side = table[prefix]
        comment = ""
        if prefix in titles:
            code, title = titles[prefix]
            spaced = " ".join(title.split())
            comment = f"  # {code} {spaced}"
        lines.append(f'  "{prefix}": {side}{comment}')
    return "\n".join(lines) + "\n"


def extract_text(pdf: Path) -> str:
    try:
        import pypdf  # noqa: PLC0415 — só a extração precisa, os testes não
    except ImportError:
        raise SystemExit("pip install pypdf: a extração do PDF precisa dele")
    reader = pypdf.PdfReader(str(pdf))
    return "\n".join(page.extract_text() for page in reader.pages)


def documents_declaring_natures() -> list[Path]:
    import yaml  # noqa: PLC0415

    found = []
    for path in sorted(ROOT.glob("*/*/*/contract.yaml")):
        contract = yaml.safe_load(path.read_text()) or {}
        # A tabela é publicada pelo contrato em `tables`; quem a declara recebe a cópia.
        for table in contract.get("tables") or []:
            if isinstance(table, dict) and table.get("from") == TABLE_FILE:
                found.append(path.parent)
                break
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2

    pdf = Path(argv[1])
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    accounts = parse_elenco(extract_text(pdf))
    if len(accounts) < 1000:
        raise SystemExit(f"o elenco extraído tem {len(accounts)} rubricas; o PDF não foi lido direito")

    sides, unmarked = natures_of(accounts)
    table = minimal_table(sides)

    # A tabela mínima tem de dar a TODA rubrica do elenco o lado que a regra deu.
    for prefix, side in sides.items():
        if decide(table, prefix) != side:
            raise SystemExit(f"a tabela mínima erra a rubrica {prefix}: {decide(table, prefix)} ≠ {side}")

    titles = {prefix_of(code): (code, title) for code, title in accounts}
    content = render(table, titles, unmarked, digest)

    targets = documents_declaring_natures()
    for doc_dir in targets:
        (doc_dir / TABLE_FILE).write_text(content)
        print(f"{(doc_dir / TABLE_FILE).relative_to(ROOT)}: {len(table)} prefixos")
    if not targets:
        print("nenhum contrato declara nature.from: natureza.yaml; nada escrito")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
