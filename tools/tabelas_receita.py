#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""Lê as tabelas de códigos da e-Financeira publicadas pela Receita e gera o que o
catálogo deriva delas.

As tabelas são do REGULADOR, não do cliente: a Receita valida cada evento contra
a tabela "vigente na data de recepção" (Anexo II, leiaute v1.5.0). Por isso o
catálogo publica a cópia que baixou, byte a byte, em br/rfb/e-financeira/tabelas/,
e nada aqui é escrito à mão:

  * `municipios.yaml` — código do município (7 dígitos, IBGE) → sigla da UF, para a
    regra que confere que o município é da UF informada (REGRA_VALIDA_MUNICIPIO_UF)
    e que o código existe (REGRA_EXISTE_COD_MUNICIPIO). A UF sai dos dois primeiros
    dígitos do código, pela tabela de UF da própria Receita.
  * os domínios que o contrato declara (países, UF, tipos de nome e de endereço,
    categorias de declarante) — o contrato os escreve, e `test_tabelas_receita.py`
    confere que são exatamente os vigentes destas tabelas.

FORMATO DAS TABELAS, como a Receita publica (http://sped.rfb.gov.br/pasta/show/1932):
a primeira linha é `versão=N COLUNAS`; cada linha seguinte é `código|nome|DT_INI|DT_FIM`,
datas em DDMMAAAA, DT_FIM vazio enquanto vigente. A codificação varia de arquivo
para arquivo (UTF-8 ou Latin-1) e há linhas repetidas (a de países traz o arquivo
duas vezes, a primeira cópia cortada no meio de uma linha): o que vale é o conjunto
de códigos vigentes.

Uso:
    python3 tools/tabelas_receita.py

Escreve `municipios.yaml` em todo documento cujo contrato declara uma tabela com
`from: municipios.yaml`, idêntico em todos. O validador confere que cada cópia é
exatamente a que esta ferramenta gera da tabela publicada (e o sha256 do cabeçalho é o
dela).
"""

from __future__ import annotations

import datetime
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TABLES_DIR = ROOT / "br" / "rfb" / "e-financeira" / "tabelas"
MUNICIPALITY_TABLE_FILE = "municipios.yaml"

# Onde a Receita publica cada tabela (o portal serve o arquivo em /arquivo/download/<item>).
SOURCES = {
    "municipios.txt": "http://sped.rfb.gov.br/arquivo/download/1934",
    "paises.txt": "http://sped.rfb.gov.br/arquivo/download/1937",
    "uf.txt": "http://sped.rfb.gov.br/arquivo/download/1949",
    "categorias-declarante.txt": "http://sped.rfb.gov.br/arquivo/download/2455",
    "tipos-nome.txt": "http://sped.rfb.gov.br/arquivo/download/2457",
    "tipos-endereco.txt": "http://sped.rfb.gov.br/arquivo/download/2458",
}

# A data em que as tabelas de br/rfb/e-financeira/tabelas/ foram baixadas: a
# vigência é lida nela, não no dia em que a ferramenta roda, para que gerar e
# conferir deem o mesmo resultado em qualquer dia. Baixou de novo, mude aqui.
AS_OF = datetime.date(2026, 11, 6)

# A sigla que a tabela de UF da Receita usa para o exterior: não é UF de endereço no
# Brasil, e nenhum município a tem.
FOREIGN_UF = "EX"


class TableError(Exception):
    """A tabela publicada não tem a forma que a Receita declara."""


def decode(raw: bytes) -> str:
    """O texto da tabela: UTF-8 quando o arquivo o é; senão Windows-1252, que é o que
    as tabelas em "Latin-1" da Receita de fato usam (aspas curvas 0x93/0x94); Latin-1
    só para o que nem isso lê."""
    for encoding in ("utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _date(text: str, where: str) -> datetime.date | None:
    text = text.strip()
    if not text:
        return None
    if len(text) != 8 or not text.isdigit():
        raise TableError(f"{where}: a data {text!r} não é DDMMAAAA")
    try:
        return datetime.date(int(text[4:]), int(text[2:4]), int(text[:2]))
    except ValueError:
        raise TableError(f"{where}: a data {text!r} não existe") from None


def read_table(raw: bytes, name: str, today: datetime.date) -> dict[str, str]:
    """Os códigos vigentes em `today`, com o nome de cada um.

    Uma linha cujo início é depois de hoje, ou cujo fim é antes, não vale. Um código
    repetido com o MESMO nome é a mesma linha publicada duas vezes; com nomes
    diferentes, a tabela se contradiz e é recusada.
    """
    # Quebra só em "\n": splitlines() quebraria também em U+0085, que é o "…" do
    # Windows-1252 lido como Latin-1.
    lines = [line.rstrip("\r") for line in decode(raw).split("\n")]
    if not lines or not lines[0].lower().startswith(("versão=", "versao=")):
        raise TableError(f"{name}: a primeira linha não é o cabeçalho 'versão=N ...' da Receita")

    valid: dict[str, str] = {}
    cut: list[tuple[int, str]] = []
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        # A tabela de países vem com o arquivo publicado duas vezes, a primeira cópia
        # cortada no meio de uma linha e grudada ao cabeçalho da segunda
        # ("TW|Taiwan - versão=4 ..."). A linha cortada não é um código: a segunda
        # cópia tem de trazê-la inteira, e isso é conferido no fim.
        lowered = line.lower()
        if "versão=" in lowered or "versao=" in lowered:
            cut.append((number, line.split("|", 1)[0].strip()))
            continue
        parts = line.split("|")
        # código|nome|DT_INI|DT_FIM, e a Receita às vezes fecha a linha com mais um "|".
        if len(parts) == 5 and parts[-1].strip() == "":
            parts = parts[:4]
        # Uma linha com campos a mais é tratada como a cortada: a de países traz
        # "ZW|Zimbábue|01012009||01012009|" e, noutra cópia, o Zimbábue inteiro. Só
        # passa se o código aparecer inteiro em outra linha.
        if len(parts) > 4:
            cut.append((number, parts[0].strip()))
            continue
        if len(parts) != 4:
            raise TableError(f"{name}, linha {number}: esperava código|nome|DT_INI|DT_FIM, veio {len(parts)} campo(s)")
        code, label = parts[0].strip(), parts[1].strip()
        if not code:
            raise TableError(f"{name}, linha {number}: código vazio")
        start = _date(parts[2], f"{name}, linha {number}")
        end = _date(parts[3], f"{name}, linha {number}")
        if (start and start > today) or (end and end < today):
            continue
        if code in valid and valid[code] != label:
            raise TableError(f"{name}: o código {code} aparece com dois nomes ({valid[code]!r} e {label!r})")
        valid[code] = label

    for number, code in cut:
        if code and code not in valid:
            raise TableError(f"{name}, linha {number}: a linha malformada de {code} não aparece inteira em outra linha")
    if not valid:
        raise TableError(f"{name}: nenhum código vigente")
    return valid


def load(name: str, today: datetime.date) -> dict[str, str]:
    return read_table((TABLES_DIR / name).read_bytes(), name, today)


def municipalities(today: datetime.date) -> dict[str, tuple[str, str]]:
    """Código do município → (sigla da UF, nome), pela UF dos dois primeiros dígitos."""
    ufs = load("uf.txt", today)
    result: dict[str, tuple[str, str]] = {}
    for code, name in load("municipios.txt", today).items():
        if len(code) != 7 or not code.isdigit():
            raise TableError(f"municipios.txt: o código {code!r} não tem 7 dígitos")
        # O código 9999999 ("Exterior") é da UF EX: fica, como a Receita o publica.
        # O endereço do declarante não o aceita — a UF do endereço é uma das 27, e a
        # regra município × UF recusa a combinação.
        uf = ufs.get(code[:2])
        if uf is None:
            raise TableError(f"municipios.txt: {code} ({name}) começa por {code[:2]}, que não é UF na tabela de UF")
        result[code] = (uf, name)
    return result


def domains(today: datetime.date) -> dict[str, list[str]]:
    """Os domínios que o contrato declara, em ordem: os códigos vigentes de cada tabela."""
    return {
        "paises": sorted(load("paises.txt", today)),
        "uf": sorted(uf for uf in load("uf.txt", today).values() if uf != FOREIGN_UF),
        "tiposNome": sorted(load("tipos-nome.txt", today)),
        "tiposEndereco": sorted(load("tipos-endereco.txt", today)),
        "categoriasDeclarante": sorted(load("categorias-declarante.txt", today)),
    }


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_municipalities(today: datetime.date) -> str:
    raw = (TABLES_DIR / "municipios.txt").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rows = municipalities(today)

    out = [
        "# Municípios da e-Financeira — código (7 dígitos, IBGE) → sigla da UF.",
        "# GERADO por tools/tabelas_receita.py a partir da tabela de municípios que a",
        "# Receita publica (br/rfb/e-financeira/tabelas/municipios.txt); não edite à mão,",
        "# regere. A UF é a dos dois primeiros dígitos, pela tabela de UF da Receita.",
        "#",
        "# É dado do REGULADOR: a Receita confere que o município existe e é da UF do",
        "# endereço (REGRA_EXISTE_COD_MUNICIPIO, REGRA_VALIDA_MUNICIPIO_UF). O motor procura",
        "# o código pelo prefixo mais longo; com o campo de 7 dígitos, é o código exato.",
        f"# Vigência lida em {today.isoformat()}, a data em que as tabelas foram baixadas.",
        "",
        f"source: {SOURCES['municipios.txt']}",
        f"sha256: {digest}",
        "",
        "byPrefix:",
    ]
    for code in sorted(rows):
        uf, name = rows[code]
        out.append(f"  {_quote(code)}: {uf}  # {name}")
    return "\n".join(out) + "\n"


def documents_declaring(file_name: str) -> list[Path]:
    """Os diretórios de documento cujo contrato declara uma tabela `from: file_name`."""
    import yaml  # pyyaml, já usado pelo validador

    found = []
    for contract_path in sorted(ROOT.glob("*/*/*/contract.yaml")):
        try:
            contract = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeDecodeError) as err:
            raise TableError(f"{contract_path.relative_to(ROOT)} não pôde ser lido: {err}") from err
        except yaml.YAMLError as err:
            raise TableError(f"{contract_path.relative_to(ROOT)} não é YAML válido: {err}") from err
        # A contract that is not a mapping is refused here, not with a traceback.
        if not isinstance(contract, dict):
            raise TableError(f"{contract_path.relative_to(ROOT)} não é um mapeamento")
        for table in contract.get("tables") or []:
            if isinstance(table, dict) and table.get("from") == file_name:
                found.append(contract_path.parent)
                break
    return found


def main() -> int:
    today = AS_OF
    try:
        body = render_municipalities(today)
        targets = documents_declaring(MUNICIPALITY_TABLE_FILE)
    except (OSError, TableError) as refusal:
        print(f"tabela recusada: {refusal}", file=sys.stderr)
        return 1

    if not targets:
        print(f"nenhum contrato declara uma tabela from: {MUNICIPALITY_TABLE_FILE}; nada a escrever", file=sys.stderr)
        return 1

    for doc_dir in targets:
        (doc_dir / MUNICIPALITY_TABLE_FILE).write_text(body, encoding="utf-8")
        print(f"escrito {(doc_dir / MUNICIPALITY_TABLE_FILE).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
