#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""As guardas de leitura da lista de participantes do Pix, vistas recusando.

Com o sha256 da cópia publicada fixo, uma tabela malformada só chega aqui quando a
tabela é trocada; estes testes leem tabelas montadas na hora, com o sha256 delas.

    python3 tools/test_ispb_cnpj.py
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import ispb_cnpj

TITLE = "Lista de participantes ativos do Pix\n"
HEADER = " ;Nome Reduzido;ISPB;CNPJ;Tipo de Instituição;Autorizada pelo BCB\n"


class LeituraDaTabela(unittest.TestCase):
    def read(self, body: str, title: str = TITLE, header: str = HEADER) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ParticipantesPix.csv"
            path.write_bytes((title + header + body).encode("iso-8859-1"))
            return ispb_cnpj.read_cnpjs(path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_a_copia_publicada_le(self) -> None:
        cnpjs = ispb_cnpj.read_cnpjs()
        self.assertEqual("00000000000191", cnpjs["00000000"])
        self.assertEqual("00360305000104", cnpjs["00360305"])
        self.assertNotIn("00038121", cnpjs)  # Selic: participa do STR, não do Pix

    def test_outra_copia_e_recusada_pelo_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.csv"
            path.write_text(TITLE + HEADER, encoding="iso-8859-1")
            with self.assertRaisesRegex(ispb_cnpj.TableError, "trocar a tabela"):
                ispb_cnpj.read_cnpjs(path)

    def test_lista_sem_a_secao_dos_ativos_e_recusada(self) -> None:
        with self.assertRaisesRegex(ispb_cnpj.TableError, "não começa pela seção"):
            self.read("1;A;00000001;00.000.001/0001-01;Banco;Sim\n", title="Lista de participantes em adesão\n")

    def test_cabecalho_sem_as_colunas_e_recusado(self) -> None:
        with self.assertRaisesRegex(ispb_cnpj.TableError, "cabeçalho"):
            self.read("1;A;00000001;00.000.001/0001-01;Banco;Sim\n", header=" ;Nome;CNPJ;ISPB\n")

    def test_ispb_que_nao_tem_8_digitos_e_recusado(self) -> None:
        with self.assertRaisesRegex(ispb_cnpj.TableError, "não tem 8 dígitos"):
            self.read("1;A;123;00.000.001/0001-01;Banco;Sim\n")

    def test_cnpj_fora_do_formato_e_recusado(self) -> None:
        with self.assertRaisesRegex(ispb_cnpj.TableError, "não tem 14 caracteres"):
            self.read("1;A;00000001;00.000.001/0001;Banco;Sim\n")

    def test_ispb_repetido_e_recusado(self) -> None:
        with self.assertRaisesRegex(ispb_cnpj.TableError, "repetido"):
            self.read("1;A;00000001;00.000.001/0001-01;Banco;Sim\n2;B;00000001;00.000.002/0001-02;Banco;Sim\n")

    def test_tabela_sem_ispb_e_recusada(self) -> None:
        with self.assertRaisesRegex(ispb_cnpj.TableError, "não traz participante ativo com ISPB"):
            self.read("1;A;;00.000.001/0001-01;Banco;Sim\n")

    def test_so_a_secao_dos_ativos_entra_e_ispb_vazio_fica_fora(self) -> None:
        cnpjs = self.read("1;A;00000001;00.000.001/0001-01;Banco;Sim\n2;B;;00.000.002/0001-02;Banco;Sim\n"
                          "\nLista de participantes em adesão\n" + HEADER
                          + "1;C;00000003;00.000.003/0001-03;Banco;Sim\n")
        self.assertEqual({"00000001": "00000001000101"}, cnpjs)


class Trechos(unittest.TestCase):
    CNPJS = {"00000001": "00000001000101", "12345678": "12345678000190"}

    def test_valor_sem_guarda_nao_existe(self) -> None:
        block = ispb_cnpj.render_block("p.ispb", self.CNPJS)
        self.assertTrue(block.startswith('{% if p.ispb == None or p.ispb == "" %}{% else %}'))
        self.assertIn('cnpj_k == "12345678" %}12345678000190', block)

    def test_motivo_so_fora_da_lista_e_com_separador_condicional(self) -> None:
        reason = ispb_cnpj.render_reason("ispb", "observacao", self.CNPJS)
        missing = "{% if observacao %}; {% endif %}" + ispb_cnpj.REASON
        self.assertTrue(reason.startswith('{% if ispb == None or ispb == "" %}' + missing + "{% else %}"))
        self.assertIn('cnpj_k == "00000001" %}{% else %}' + missing, reason)  # na lista: nada
        # ISPB vazio, prefixo fora da lista e ISPB fora da lista em cada um dos 2 prefixos
        self.assertEqual(4, reason.count(missing))

    def test_regera_entre_as_marcas_e_insere_sem_a_de_fim(self) -> None:
        text = "a{# ISPB_CNPJ_BLOCK: ispb #}velho{# /ISPB_CNPJ_BLOCK #}b{# ISPB_CNPJ_REASON: ispb obs #}c"
        out = ispb_cnpj.expected_template(text, self.CNPJS)
        self.assertNotIn("velho", out)
        self.assertEqual(1, out.count(ispb_cnpj.END))
        self.assertEqual(1, out.count(ispb_cnpj.END_REASON))
        self.assertTrue(out.endswith(ispb_cnpj.END_REASON + "c"))
        self.assertEqual(out, ispb_cnpj.expected_template(out, self.CNPJS))

    def test_marca_malformada_e_contada(self) -> None:
        self.assertEqual(1, ispb_cnpj.malformed_markers("{# ISPB_CNPJ_BLOCK:ispb #}"))
        self.assertEqual(1, ispb_cnpj.malformed_markers("{# ISPB_CNPJ_REASON: ispb #}"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
