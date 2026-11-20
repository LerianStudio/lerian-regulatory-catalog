#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""Como tools/tabelas_receita.py lê as tabelas de códigos da Receita, e que o que o
catálogo deriva delas confere com a cópia publicada.

Sobre trechos escritos à mão, com as formas que os arquivos da Receita têm: o
cabeçalho `versão=N`, Latin-1 ou UTF-8, CRLF, linhas repetidas e códigos que saíram
de vigência. E sobre as tabelas publicadas em br/rfb/e-financeira/tabelas/: a
`municipios.yaml` de cada documento é a que a ferramenta gera, e cada domínio que o
contrato do evtCadDeclarante declara é exatamente o conjunto vigente da tabela.

    python3 tools/test_tabelas_receita.py
"""

from __future__ import annotations

import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tabelas_receita as tr  # noqa: E402

TODAY = tr.AS_OF


def table(*rows: str, header: str = "versão=1 COD, NOM, DT_INI, DT_FIM", encoding: str = "latin-1") -> bytes:
    return "\r\n".join((header,) + rows).encode(encoding)


class ReadTable(unittest.TestCase):
    def test_reads_the_valid_codes_with_their_names(self):
        got = tr.read_table(table("SP|São Paulo|01012009|", "RJ|Rio de Janeiro|01012009|"), "uf", TODAY)
        self.assertEqual(got, {"SP": "São Paulo", "RJ": "Rio de Janeiro"})

    def test_reads_utf8_and_latin1_alike(self):
        latin = tr.read_table(table("AF|Afeganistão|01012009|"), "p", TODAY)
        utf8 = tr.read_table(table("AF|Afeganistão|01012009|", encoding="utf-8"), "p", TODAY)
        self.assertEqual(latin, utf8)

    def test_a_row_published_twice_is_one_code(self):
        got = tr.read_table(table("AD|Andorra|01012009|", "AD|Andorra|01012009|"), "p", TODAY)
        self.assertEqual(got, {"AD": "Andorra"})

    def test_a_copy_cut_mid_row_and_glued_to_the_next_header_is_read_from_the_whole_copy(self):
        raw = table("TV|Tuvalu|01012009|", "TW|Taiwan - versão=4 COD_PAIS, NOM_PAIS, DT_INI, DT_FIM",
                    "TV|Tuvalu|01012009|", "TW|Taiwan - Província da China|01012009|", encoding="utf-8")
        got = tr.read_table(raw, "p", TODAY)
        self.assertEqual(got, {"TV": "Tuvalu", "TW": "Taiwan - Província da China"})

    def test_a_cut_row_with_no_whole_copy_is_refused(self):
        with self.assertRaisesRegex(tr.TableError, "não aparece inteira"):
            tr.read_table(table("TV|Tuvalu|01012009|", "TW|Taiwan - versão=4 COD_PAIS", encoding="utf-8"), "p", TODAY)

    def test_a_row_with_extra_fields_is_read_from_its_whole_copy(self):
        got = tr.read_table(table("ZW|Zimbábue|01012009||01012009|", "ZW|Zimbábue|01012009|"), "p", TODAY)
        self.assertEqual(got, {"ZW": "Zimbábue"})

    def test_a_row_with_extra_fields_and_no_whole_copy_is_refused(self):
        with self.assertRaisesRegex(tr.TableError, "não aparece inteira"):
            tr.read_table(table("AD|And|orra|01012009||", "TV|Tuvalu|01012009|"), "p", TODAY)

    def test_a_row_with_too_few_fields_is_refused(self):
        with self.assertRaisesRegex(tr.TableError, "campo"):
            tr.read_table(table("AD|Andorra"), "p", TODAY)

    def test_an_impossible_date_is_refused_not_crashed(self):
        with self.assertRaisesRegex(tr.TableError, "não existe"):
            tr.read_table(table("AD|Andorra|31022009|"), "p", TODAY)

    def test_windows_1252_quotes_are_read_and_do_not_break_rows(self):
        raw = "versão=1 COD, NOM, DT_INI, DT_FIM\r\nX1|“Nome”…|01012009|\r\nX2|Outro|01012009|".encode("cp1252")
        got = tr.read_table(raw, "p", TODAY)
        self.assertEqual(got, {"X1": "“Nome”…", "X2": "Outro"})

    def test_a_code_that_left_validity_is_not_valid(self):
        got = tr.read_table(table("AN|Antilhas Holandesas|01012009|31122017|", "AD|Andorra|01012009|"), "p", TODAY)
        self.assertNotIn("AN", got)

    def test_a_code_not_yet_valid_is_not_valid(self):
        got = tr.read_table(table("ZZ|Futuro|01012099|", "AD|Andorra|01012009|"), "p", TODAY)
        self.assertNotIn("ZZ", got)

    def test_a_code_with_two_names_is_refused(self):
        with self.assertRaisesRegex(tr.TableError, "dois nomes"):
            tr.read_table(table("AD|Andorra|01012009|", "AD|Outro|01012009|"), "p", TODAY)

    def test_a_file_without_the_receita_header_is_refused(self):
        with self.assertRaisesRegex(tr.TableError, "cabeçalho"):
            tr.read_table(table("AD|Andorra|01012009|", header="COD|NOM"), "p", TODAY)

    def test_a_date_that_is_not_ddmmyyyy_is_refused(self):
        with self.assertRaisesRegex(tr.TableError, "DDMMAAAA"):
            tr.read_table(table("AD|Andorra|2009-01-01|"), "p", TODAY)

    def test_a_table_with_nothing_valid_is_refused(self):
        with self.assertRaisesRegex(tr.TableError, "nenhum código vigente"):
            tr.read_table(table("AN|Antilhas Holandesas|01012009|31122017|"), "p", TODAY)


class PublishedTables(unittest.TestCase):
    """As tabelas que o catálogo publica, como a Receita as entregou."""

    def test_every_municipality_belongs_to_a_brazilian_uf(self):
        rows = tr.municipalities(TODAY)
        self.assertGreater(len(rows), 5500)
        self.assertEqual(rows["3550308"][0], "SP")  # São Paulo
        self.assertEqual(rows["5300108"][0], "DF")  # Brasília
        foreign = [code for code, (uf, _) in rows.items() if uf == tr.FOREIGN_UF]
        self.assertEqual(foreign, ["9999999"], "só o código Exterior da Receita é do exterior")

    def test_the_domains_hold_what_the_layout_names(self):
        got = tr.domains(TODAY)
        self.assertIn("BR", got["paises"])
        self.assertNotIn("AN", got["paises"], "Antilhas Holandesas saiu de vigência em 2017")
        self.assertEqual(len(got["uf"]), 27)
        self.assertIn("OECD207", got["tiposNome"])
        self.assertIn("OECD304", got["tiposEndereco"])
        self.assertIn("FATCA602", got["categoriasDeclarante"])

    def test_every_municipality_table_is_the_generated_one(self):
        expected = tr.render_municipalities(TODAY)
        targets = tr.documents_declaring(tr.MUNICIPALITY_TABLE_FILE)
        self.assertTrue(targets, "nenhum contrato declara a tabela de municípios")
        for doc_dir in targets:
            with self.subTest(document=str(doc_dir.relative_to(tr.ROOT))):
                self.assertEqual((doc_dir / tr.MUNICIPALITY_TABLE_FILE).read_text(encoding="utf-8"), expected,
                                 "regere com python3 tools/tabelas_receita.py")


class DocumentsDeclaring(unittest.TestCase):
    """A malformed contract is refused as a TableError, which main reports."""

    def _with_contract(self, text: str):
        import tempfile
        from unittest import mock

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        doc = root / "br" / "rfb" / "doc"
        doc.mkdir(parents=True)
        (doc / "contract.yaml").write_text(text, encoding="utf-8")
        patcher = mock.patch.object(tr, "ROOT", root)
        patcher.start()
        self.addCleanup(patcher.stop)
        return doc

    def test_a_contract_that_is_not_a_mapping_is_refused(self):
        self._with_contract("- tables\n- datasets\n")
        with self.assertRaisesRegex(tr.TableError, "não é um mapeamento"):
            tr.documents_declaring(tr.MUNICIPALITY_TABLE_FILE)

    def test_a_contract_that_is_not_yaml_is_refused(self):
        self._with_contract("tables: [\n")
        with self.assertRaisesRegex(tr.TableError, "não é YAML válido"):
            tr.documents_declaring(tr.MUNICIPALITY_TABLE_FILE)

    def test_a_contract_that_is_not_utf8_is_refused(self):
        doc = self._with_contract("")
        (doc / "contract.yaml").write_bytes(b"tables: [\xff\xfe]\n")
        with self.assertRaisesRegex(tr.TableError, "não pôde ser lido"):
            tr.documents_declaring(tr.MUNICIPALITY_TABLE_FILE)

    def test_main_reports_a_missing_table_file_instead_of_crashing(self):
        import contextlib
        import io
        from unittest import mock

        def missing(_today):
            raise FileNotFoundError("municipios.txt")

        err = io.StringIO()
        with mock.patch.object(tr, "render_municipalities", missing), contextlib.redirect_stderr(err):
            self.assertEqual(tr.main(), 1)
        self.assertIn("tabela recusada", err.getvalue())

    def test_main_reports_a_malformed_contract_instead_of_crashing(self):
        import contextlib
        import io

        self._with_contract("- tables\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(tr.main(), 1)
        self.assertIn("não é um mapeamento", err.getvalue())

    def test_a_contract_declaring_the_table_is_found(self):
        doc = self._with_contract(f"tables:\n  - from: {tr.MUNICIPALITY_TABLE_FILE}\n")
        self.assertEqual(tr.documents_declaring(tr.MUNICIPALITY_TABLE_FILE), [doc])


class ContractDomains(unittest.TestCase):
    """Cada domínio que o contrato do evtCadDeclarante declara a partir de uma tabela
    da Receita é EXATAMENTE o conjunto vigente dela — nem um código a mais, nem a menos."""

    CONTRACT = tr.ROOT / "br" / "rfb" / "efinanceira-cad-declarante" / "contract.yaml"

    # (conjunto, campo) → a tabela de que o domínio vem.
    FROM_TABLE = {
        ("declarante", "pais"): "paises",
        ("declarante", "uf"): "uf",
        ("declarante", "tpNome"): "tiposNome",
        ("declarante", "tpEndereco"): "tiposEndereco",
        ("declarante", "categoriaDeclarante"): "categoriasDeclarante",
        ("nifs", "paisEmissao"): "paises",
        ("residenciasFiscais", "pais"): "paises",
    }

    def test_every_table_domain_is_the_valid_table(self):
        import yaml

        contract = yaml.safe_load(self.CONTRACT.read_text(encoding="utf-8"))
        fields = {(ds["name"], f["name"]): f for ds in contract["datasets"] for f in ds["fields"]}
        tables = tr.domains(tr.AS_OF)
        for (dataset, field), table in self.FROM_TABLE.items():
            with self.subTest(field=f"{dataset}.{field}"):
                self.assertEqual(sorted(fields[(dataset, field)]["domain"]), tables[table],
                                 f"o domínio de {dataset}.{field} não é a tabela {table} vigente")



class AberturaDomains(ContractDomains):
    """O mesmo para o evtAberturaeFinanceira: a UF dos endereços do responsável pela
    RMF e dos responsáveis pela e-Financeira é a tabela de UF vigente."""

    CONTRACT = tr.ROOT / "br" / "rfb" / "efinanceira-abertura" / "contract.yaml"

    FROM_TABLE = {
        ("responsavelRMF", "uf"): "uf",
        ("respeFin", "uf"): "uf",
    }

if __name__ == "__main__":
    unittest.main(verbosity=1)
