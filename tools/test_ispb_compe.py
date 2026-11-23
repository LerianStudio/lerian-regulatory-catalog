#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""As guardas de leitura da lista de participantes do STR, vistas recusando.

Com o sha256 da cópia publicada fixo, uma tabela malformada só chega aqui quando a
tabela é trocada; estes testes leem tabelas montadas na hora, com o sha256 delas.

    python3 tools/test_ispb_compe.py
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import ispb_compe

HEADER = "ISPB,Nome_Reduzido,Número_Código,Participa_da_Compe,Acesso_Principal,Nome_Extenso,Início_da_Operação\n"


class LeituraDaTabela(unittest.TestCase):
    def read(self, body: str) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ParticipantesSTR.csv"
            path.write_bytes(("﻿" + HEADER + body).encode("utf-8"))
            return ispb_compe.read_codes(path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_a_copia_publicada_le(self) -> None:
        codes = ispb_compe.read_codes()
        self.assertEqual("001", codes["00000000"])
        self.assertNotIn("00038121", codes)  # Selic, n/a

    def test_outra_copia_e_recusada_pelo_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.csv"
            path.write_text(HEADER, encoding="utf-8")
            with self.assertRaisesRegex(ispb_compe.TableError, "trocar a tabela"):
                ispb_compe.read_codes(path)

    def test_ispb_que_nao_tem_8_digitos_e_recusado(self) -> None:
        with self.assertRaisesRegex(ispb_compe.TableError, "não tem 8 dígitos"):
            self.read("123,BANCO,001,Sim,RSFN,Banco,01/01/2000\n")

    def test_ispb_repetido_e_recusado(self) -> None:
        with self.assertRaisesRegex(ispb_compe.TableError, "repetido"):
            self.read("00000001,A,001,Sim,RSFN,A,01/01/2000\n00000001,B,002,Sim,RSFN,B,01/01/2000\n")

    def test_codigo_fora_do_formato_e_recusado(self) -> None:
        with self.assertRaisesRegex(ispb_compe.TableError, "não é n/a, 0 nem 3 dígitos"):
            self.read("00000001,A,12,Sim,RSFN,A,01/01/2000\n")

    def test_tabela_sem_codigo_e_recusada(self) -> None:
        with self.assertRaisesRegex(ispb_compe.TableError, "não traz participante com código"):
            self.read("00000001,A,n/a,Não,RSFN,A,01/01/2000\n")

    def test_n_a_e_zero_ficam_fora_e_codigo_sem_compe_entra(self) -> None:
        codes = self.read("00000001,A,n/a,Não,RSFN,A,01/01/2000\n00000002,B,0,Não,RSFN,B,01/01/2000\n"
                          "00000003,C,123,Não,RSFN,C,01/01/2000\n")
        self.assertEqual({"00000003": "123"}, codes)


if __name__ == "__main__":
    unittest.main(verbosity=1)
