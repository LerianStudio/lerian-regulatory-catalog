#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""Cada situação que a conferência dos cinco arquivos do SIMBA lista, vista disparando.

Os arquivos são montados aqui, com dados que não são de ninguém (documentos de
zeros, nomes de exemplo). Um caso coerente passa sem erro e sem aviso; cada teste
quebra uma coisa e exige a mensagem dela.

    python3 tools/test_simba_conferencia.py
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import simba_conferencia as conf

CASO = "001-XYZ-000001-01"


def line(fields: list[str]) -> str:
    return "\t".join(fields) + "\r\n"


def agencia(numero: str) -> list[str]:
    return ["999", numero, "AGENCIA EXEMPLO", "RUA EXEMPLO", "3550308", "35", "Brasil", "01001000",
            "1100000000", "02012024", "31129999", "00000000000000", "INSTITUICAO EXEMPLO", "1"]


def conta(agencia: str, numero: str, movimento: str, inicial: str, final: str) -> list[str]:
    return ["999", agencia, numero, "6", "02012024", "31129999", movimento, "00000000000000",
            "INSTITUICAO EXEMPLO", inicial, final, ""]


def titular(agencia: str, numero: str) -> list[str]:
    row = [""] * 28
    row[:9] = ["999", agencia, numero, "6", "T", "1", "1", "00000000000", "PESSOA EXEMPLO"]
    row[27] = "0"
    return row


def lancamento(numero: str, agencia: str, conta: str, codigo: str, valor: str, natureza: str,
               saldo: str, natureza_saldo: str) -> list[str]:
    row = [""] * 27
    row[:13] = [numero, "999", agencia, conta, "6", "01122026", numero, "LANCAMENTO EXEMPLO", codigo, valor,
                natureza, saldo, natureza_saldo]
    return row


def od(numero_od: str, numero: str, valor: str, documento: str = "00000000000", observacao: str = "") -> list[str]:
    row = [""] * 28
    row[:11] = [numero_od, numero, valor, numero, "999", "0001", "777777", "6", "1", documento, "PESSOA EXEMPLO"]
    row[16] = "0"
    row[17] = observacao
    return row


def case() -> dict[str, list[list[str]]]:
    """Um caso coerente: duas contas na agência 0001, dois lançamentos numa delas."""
    return {
        "AGENCIAS": [agencia("0001")],
        "CONTAS": [conta("0001", "123456", "1", "10000", "4000"), conta("0001", "654321", "2", "500", "500")],
        "TITULARES": [titular("0001", "123456"), titular("0001", "654321")],
        "EXTRATO": [lancamento("1", "0001", "123456", "134", "5000", "D", "5000", "C"),
                    lancamento("2", "0001", "123456", "135", "1000", "D", "4000", "C")],
        "ORIGEM_DESTINO": [od("1", "1", "5000"), od("2", "2", "1000")],
    }


def rows(saldo_final: str = "5.00") -> dict:
    return {"datasets": {
        "contas_investigadas": [
            {"numeroAgencia": "0001", "numeroConta": "123456", "saldoInicial": "100.00", "saldoFinal": "40.00"},
            {"numeroAgencia": "0001", "numeroConta": "654321", "saldoInicial": "5.00", "saldoFinal": saldo_final}],
        "contas_contraparte": []}}


class Conferencia(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, files: dict[str, list[list[str]]], folder: str = "atual", contas_rows: dict | None = None):
        target = self.root / folder
        target.mkdir(exist_ok=True)
        for name, content in files.items():
            (target / f"{CASO}_{name}.txt").write_bytes("".join(line(r) for r in content).encode("ascii"))
        rows_path = None
        if contas_rows is not None:
            rows_path = target / "contas-rows.json"
            rows_path.write_text(json.dumps(contas_rows), encoding="utf-8")
        return target, rows_path

    def run_case(self, files=None, contas_rows=None, previous=None) -> conf.Report:
        folder, rows_path = self.write(files or case(), contas_rows=rows() if contas_rows is None else contas_rows)
        return conf.conferir(folder, CASO, rows_path, previous)

    def assert_says(self, texts: list[str], fragment: str) -> None:
        self.assertTrue(any(fragment in t for t in texts), f"nenhuma mensagem com {fragment!r}: {texts}")

    # ------------------------------------------------------------ controle positivo
    def test_caso_coerente_passa_sem_erro_nem_aviso(self) -> None:
        report = self.run_case()
        self.assertEqual([], report.errors)
        self.assertEqual([], report.warnings)

    # ------------------------------------------------------------ forma do arquivo
    def test_linha_sem_crlf_e_erro(self) -> None:
        folder, rows_path = self.write(case(), contas_rows=rows())
        path = folder / f"{CASO}_CONTAS.txt"
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
        self.assert_says(conf.conferir(folder, CASO, rows_path).errors, "CONTAS")

    def test_campos_a_menos_e_erro(self) -> None:
        files = case()
        files["TITULARES"][0] = files["TITULARES"][0][:27]
        self.assert_says(self.run_case(files).errors, "TITULARES:1: 27 campos")

    # ------------------------------------------------------------ Epic 4.3, linha a linha
    def test_numeros_de_lancamento_diferentes_e_erro(self) -> None:
        files = case()
        files["ORIGEM_DESTINO"][1] = od("2", "3", "1000")
        errors = self.run_case(files).errors
        self.assert_says(errors, "lançamento 2 não tem linha no ORIGEM-DESTINO")
        self.assert_says(errors, "lançamento 3 não está no EXTRATO")

    def test_lancamento_gravado_entre_as_geracoes_desloca_o_valor(self) -> None:
        files = case()
        files["ORIGEM_DESTINO"] = [od("1", "1", "5000"), od("2", "2", "777")]
        self.assert_says(self.run_case(files).errors, "vale 777 aqui e 1000 no EXTRATO")

    def test_conta_do_extrato_fora_do_contas_e_erro(self) -> None:
        files = case()
        files["EXTRATO"][1] = lancamento("2", "0001", "999999", "135", "1000", "D", "4000", "C")
        self.assert_says(self.run_case(files).errors, "EXTRATO: a conta 999999 da agência 0001 não está no CONTAS")

    def test_conta_do_titulares_fora_do_contas_e_erro(self) -> None:
        files = case()
        files["TITULARES"].append(titular("0001", "888888"))
        self.assert_says(self.run_case(files).errors, "TITULARES: a conta 888888")

    def test_agencia_fora_do_agencias_e_erro(self) -> None:
        files = case()
        files["AGENCIAS"] = [agencia("0002")]
        self.assert_says(self.run_case(files).errors, "CONTAS: a agência 0001 não está no AGENCIAS")

    def test_ultimo_saldo_diferente_do_contas_e_aviso(self) -> None:
        files = case()
        files["CONTAS"][0] = conta("0001", "123456", "1", "10000", "3900")
        report = self.run_case(files)
        self.assertEqual([], report.errors)
        self.assert_says(report.warnings, "o último saldo da conta 123456 da agência 0001 é 4000")

    def test_codigo_generico_e_aviso(self) -> None:
        files = case()
        files["EXTRATO"][0] = lancamento("1", "0001", "123456", "218", "5000", "D", "5000", "C")
        report = self.run_case(files)
        self.assertEqual([], report.errors)
        self.assert_says(report.warnings, "o lançamento 1 tem o código genérico 218")

    def test_contraparte_nao_identificada_e_aviso(self) -> None:
        files = case()
        files["ORIGEM_DESTINO"][0] = od("1", "1", "5000", documento="", observacao=conf.UNIDENTIFIED)
        self.assert_says(self.run_case(files).warnings, "contraparte não identificada pelo trilho")

    def test_contraparte_sem_documento_e_aviso(self) -> None:
        files = case()
        files["ORIGEM_DESTINO"][1] = od("2", "2", "1000", documento="")
        self.assert_says(self.run_case(files).warnings, "lançamento 2 está sem CPF/CNPJ")

    def test_cheque_especial_com_movimento_e_aviso(self) -> None:
        files = case()
        files["EXTRATO"][1] = lancamento("2", "0001", "123456", "135", "1000", "D", "4000", "D")
        self.assert_says(self.run_case(files).warnings, "termina o período devedora")

    def test_saldo_devedor_sem_movimento_e_aviso(self) -> None:
        # A conta 654321 não tem lançamento: só as linhas do rascunho mostram o sinal.
        # No arquivo, -12,50 sai 1250 (o CONTAS escreve o saldo sem sinal).
        files = case()
        files["CONTAS"][1] = conta("0001", "654321", "2", "500", "1250")
        report = self.run_case(files, contas_rows=rows(saldo_final="-12.50"))
        self.assertEqual([], report.errors)
        self.assert_says(report.warnings, "a conta 654321 da agência 0001 tem saldo final devedor (-12.50)")

    def test_sem_as_linhas_do_rascunho_a_conferencia_diz_o_que_nao_viu(self) -> None:
        folder, _ = self.write(case())
        self.assert_says(conf.conferir(folder, CASO, None).warnings, "NÃO foi conferida")

    # ------------------------------------------------------------ completude do reenvio
    def test_reenvio_conta_as_linhas_que_entraram_e_sairam(self) -> None:
        anterior, _ = self.write(case(), folder="anterior")
        files = case()
        files["EXTRATO"].append(lancamento("3", "0001", "123456", "135", "1", "D", "3999", "C"))
        files["ORIGEM_DESTINO"].append(od("3", "3", "1"))
        files["CONTAS"][0] = conta("0001", "123456", "1", "10000", "3999")
        report = self.run_case(files, previous=anterior)
        self.assertEqual([], report.errors)
        self.assert_says(report.warnings, "EXTRATO: em relação ao envio anterior, 1 linha(s) entraram e 0 saíram")
        self.assert_says(report.warnings, "CONTAS: em relação ao envio anterior, 1 linha(s) entraram e 1 saíram")


class Mutations(unittest.TestCase):
    """O aviso de saldo devedor sem movimento, visto sumindo: sem ele, o teste reprova."""

    def test_tirar_o_aviso_de_saldo_devedor_reprova_o_teste(self) -> None:
        with mock.patch.object(conf, "check_overdraft_rows", lambda path, report: None):
            result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
                unittest.defaultTestLoader.loadTestsFromName(
                    "test_saldo_devedor_sem_movimento_e_aviso", Conferencia))
        self.assertEqual(1, len(result.failures), "o teste do saldo devedor passou sem o aviso")


if __name__ == "__main__":
    unittest.main(verbosity=1)
