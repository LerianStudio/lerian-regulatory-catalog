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

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

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
    row[:11] = ["999", agencia, numero, "6", "T", "1", "1", "00000000000", "PESSOA EXEMPLO", "RG", "000000"]
    row[25:27] = ["DISPOSITIVO EXEMPLO", "COMPUTADOR EXEMPLO"]
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
    """A resposta de /rows do rascunho do CONTAS (o saldo tem sinal aqui)."""
    return {"documentId": "br.bcb.simba.contas", "status": "Draft", "datasets": {
        "instituicao": [{"compe": "999"}],
        "contas_investigadas": [
            {"contaId": "c1", "numeroAgencia": "0001", "numeroConta": "123456", "saldoInicial": "100.00",
             "saldoFinal": "40.00"},
            {"contaId": "c2", "numeroAgencia": "0001", "numeroConta": "654321", "saldoInicial": "5.00",
             "saldoFinal": saldo_final}],
        "contas_contraparte": []}}


def titulares_rows(*partes: tuple[str, str]) -> dict:
    """A resposta de /rows do rascunho do TITULARES, com as partes (contaId, parteId) dadas."""
    return {"documentId": "br.bcb.simba.titulares", "status": "Draft", "datasets": {
        "instituicao": [{"compe": "999"}],
        "titulares": [{"contaId": "c1"}, {"contaId": "c2"}],
        "partes": [{"contaId": conta, "parteId": parte} for conta, parte in partes]}}


def extrato_rows(*lancamentos: tuple) -> dict:
    """A resposta de /rows do rascunho do EXTRATO: (conta, instante, disponível[, bloqueado, cheque especial])."""
    linhas = []
    for i, (conta, instante, disponivel, *resto) in enumerate(lancamentos):
        bloqueado, cheque = (resto + ["0", "0"])[:2]
        linhas.append({"operacaoId": f"o{i}", "numeroAgencia": "0001", "numeroConta": conta,
                       "horaLancamento": instante, "saldoApos": disponivel, "bloqueadoApos": bloqueado,
                       "chequeEspecialApos": cheque})
    return {"documentId": "br.bcb.simba.extrato", "status": "Draft", "datasets": {"lancamentos": linhas}}


def coherent_drafts() -> list[dict]:
    """As linhas dos rascunhos do CONTAS e do EXTRATO que casam com case()."""
    return [rows(), extrato_rows(("123456", "2026-12-01T10:00:01Z", "50.00"),
                                 ("123456", "2026-12-01T10:00:02Z", "40.00"))]


def final(*drafts: dict) -> list[dict]:
    """As mesmas respostas, como as de um envio aprovado."""
    return [dict(d, status="Final") for d in drafts]


class Conferencia(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, files: dict[str, list[list[str]]], folder: str = "atual", drafts: list[dict] | None = None):
        target = self.root / folder
        target.mkdir(exist_ok=True)
        for name, content in files.items():
            (target / f"{CASO}_{name}.txt").write_bytes("".join(line(r) for r in content).encode("ascii"))
        return target, self.rows_folder(f"{folder}-rows", drafts)

    def rows_folder(self, folder: str, drafts: list[dict] | None) -> Path | None:
        if drafts is None:
            return None
        target = self.root / folder
        target.mkdir(exist_ok=True)
        for i, draft in enumerate(drafts):
            (target / f"{i}.json").write_text(json.dumps(draft), encoding="utf-8")
        return target

    def run_case(self, files=None, drafts=None, previous=None, justifications=None, documents=None) -> conf.Report:
        folder, drafts_folder = self.write(files or case(), drafts=coherent_drafts() if drafts is None else drafts)
        path = self.root / "documentos.txt"
        path.write_text("\n".join(["00000000000"] if documents is None else documents) + "\n", encoding="utf-8")
        return conf.conferir(folder, CASO, drafts_folder, previous, justifications, path)

    def assert_says(self, texts: list[str], fragment: str) -> None:
        self.assertTrue(any(fragment in t for t in texts), f"nenhuma mensagem com {fragment!r}: {texts}")

    # ------------------------------------------------------------ controle positivo
    def test_caso_coerente_passa_sem_erro_nem_aviso(self) -> None:
        report = self.run_case()
        self.assertEqual([], report.errors)
        self.assertEqual([], report.warnings)

    # ------------------------------------------------------------ caso sem movimento
    def idle_case(self) -> dict[str, list[list[str]]]:
        files = case()
        files["CONTAS"] = [conta("0001", "123456", "2", "4000", "4000"), conta("0001", "654321", "2", "500", "500")]
        files["EXTRATO"], files["ORIGEM_DESTINO"] = [], []
        return files

    def test_sem_movimento_extrato_e_od_vazios_passam(self) -> None:
        report = self.run_case(files=self.idle_case(), drafts=[rows(), extrato_rows()])
        self.assertEqual([], report.errors)
        self.assertEqual([], report.warnings)

    def test_sem_movimento_extrato_e_od_ausentes_e_aviso_para_entregar_o_vazio(self) -> None:
        files = self.idle_case()
        del files["EXTRATO"], files["ORIGEM_DESTINO"]
        report = self.run_case(files=files, drafts=[rows()])
        self.assertEqual([], report.errors)
        self.assert_says(report.warnings, f"{CASO}_EXTRATO.txt: não encontrado; nenhuma conta do CONTAS teve lançamento")
        self.assert_says(report.warnings, f"{CASO}_ORIGEM_DESTINO.txt: não encontrado; nenhuma conta do CONTAS")

    def test_conta_movimentada_com_extrato_vazio_e_erro(self) -> None:
        files = case()
        files["EXTRATO"], files["ORIGEM_DESTINO"] = [], []
        report = self.run_case(files=files, drafts=[rows()])
        self.assert_says(report.errors, "EXTRATO: sem linha nenhuma, e o CONTAS diz que a conta 123456 da agência 0001")
        self.assert_says(report.errors, "ORIGEM_DESTINO: sem linha nenhuma")

    def test_conta_movimentada_com_extrato_ausente_e_erro(self) -> None:
        files = case()
        del files["EXTRATO"]
        self.assert_says(self.run_case(files=files, drafts=[rows()]).errors, f"{CASO}_EXTRATO.txt: não encontrado em")

    # ------------------------------------------------------------ forma do arquivo
    def test_linha_sem_crlf_e_erro(self) -> None:
        folder, drafts_folder = self.write(case(), drafts=[rows()])
        path = folder / f"{CASO}_CONTAS.txt"
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
        self.assert_says(conf.conferir(folder, CASO, drafts_folder).errors, "CONTAS: a última linha não termina em CRLF")

    def test_campos_a_menos_e_erro(self) -> None:
        files = case()
        files["TITULARES"][0] = files["TITULARES"][0][:27]
        self.assert_says(self.run_case(files).errors, "TITULARES:1: 27 campos")

    def test_caractere_fora_do_ascii_e_erro(self) -> None:
        files = case()
        files["TITULARES"][0][8] = "PESSOA EXEMPLO"
        folder, drafts_folder = self.write(files, drafts=[rows()])
        path = folder / f"{CASO}_TITULARES.txt"
        path.write_bytes(path.read_bytes().replace(b"PESSOA EXEMPLO", "PESSOA EXEMPLÃ".encode("utf-8"), 1))
        self.assert_says(conf.conferir(folder, CASO, drafts_folder).errors, "TITULARES:1: caractere fora do ASCII")

    def test_contas_sem_conta_e_aviso(self) -> None:
        files = {name: [] for name in conf.FILES}
        self.assert_says(self.run_case(files).warnings, "CONTAS: nenhuma conta")

    # ------------------------------------------------------------ a tabela de conferência, linha a linha
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

    def test_conta_do_extrato_sem_movimento_no_contas_e_erro(self) -> None:
        files = case()
        files["EXTRATO"].append(lancamento("3", "0001", "654321", "135", "100", "D", "400", "C"))
        files["ORIGEM_DESTINO"].append(od("3", "3", "100"))
        self.assert_says(self.run_case(files).errors, "EXTRATO: a conta 654321 da agência 0001 tem lançamento, e o "
                                                      "CONTAS não a dá como investigada com movimento")

    def test_conta_movimentada_sem_linha_no_extrato_e_erro(self) -> None:
        files = case()
        files["CONTAS"][1] = conta("0001", "654321", "1", "500", "500")
        self.assert_says(self.run_case(files).errors, "CONTAS: a conta 654321 da agência 0001 teve lançamento no "
                                                      "período (campo 7 = 1) e não tem linha no EXTRATO")

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
        report = self.run_case(files, drafts=[rows()])
        self.assertEqual([], report.errors)
        self.assert_says(report.warnings, "o saldo da última linha da conta 123456 da agência 0001 é 4000")

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

    def test_ultimo_saldo_e_o_do_maior_instante_nas_linhas_do_rascunho(self) -> None:
        # A transação pendente da linha 2 do arquivo foi confirmada antes da linha 1:
        # o último saldo é o da linha 1 (4000 = 40.00), que bate com o CONTAS.
        files = case()
        drafts = [rows(), extrato_rows(("123456", "2026-12-01T10:00:03Z", "40.00"),
                                       ("123456", "2026-12-01T10:00:01Z", "50.00"))]
        report = self.run_case(files, drafts=drafts)
        self.assertEqual([], report.warnings)
        drafts = [rows(), extrato_rows(("123456", "2026-12-01T10:00:01Z", "40.00"),
                                       ("123456", "2026-12-01T10:00:03Z", "50.00"))]
        self.assert_says(self.run_case(files, drafts=drafts).warnings, "o saldo após o último lançamento da conta 123456")

    def test_saldo_pela_formula_do_campo_12_nao_avisa_conta_devedora(self) -> None:
        # Disponível 0, cheque especial 12,50: o EXTRATO diz -12,50, como o CONTAS.
        files = case()
        drafts = [rows(saldo_final="5.00"), extrato_rows(("123456", "2026-12-01T10:00:01Z", "0", "0", "12.50"))]
        drafts[0]["datasets"]["contas_investigadas"][0]["saldoFinal"] = "-12.50"
        report = self.run_case(files, drafts=drafts)
        self.assertFalse(any("o saldo após o último lançamento" in w for w in report.warnings), report.warnings)

    def test_saldo_pela_formula_soma_o_bloqueado(self) -> None:
        # Disponível 36,50 e bloqueado 20,05: o EXTRATO diz 56,55, como o CONTAS.
        drafts = [rows(), extrato_rows(("123456", "2026-12-01T10:00:01Z", "36.50", "20.05", "0"))]
        drafts[0]["datasets"]["contas_investigadas"][0]["saldoFinal"] = "56.55"
        report = self.run_case(drafts=drafts)
        self.assertFalse(any("o saldo após o último lançamento" in w for w in report.warnings), report.warnings)

    def test_lancamento_sem_cheque_especial_medido_e_aviso(self) -> None:
        drafts = [rows(), extrato_rows(("123456", "2026-12-01T10:00:01Z", "40.00", "0", None))]
        self.assert_says(self.run_case(drafts=drafts).warnings,
                         "1 lançamento(s) da conta 123456 da agência 0001 sem o cheque especial usado")

    def test_lancamento_sem_cheque_especial_medido_sem_o_contas_ainda_e_aviso(self) -> None:
        drafts = [extrato_rows(("123456", "2026-12-01T10:00:01Z", "40.00", "0", None))]
        self.assert_says(self.run_case(drafts=drafts).warnings, "sem o cheque especial usado")

    def test_sem_as_linhas_do_extrato_a_conferencia_diz_o_que_nao_viu(self) -> None:
        self.assert_says(self.run_case(drafts=[rows()]).warnings,
                         "sem as linhas do rascunho do EXTRATO (--rascunhos), o cheque especial usado")

    def test_cheque_especial_usado_e_coberto_no_periodo_e_aviso(self) -> None:
        drafts = [rows(), extrato_rows(("123456", "2026-12-01T10:00:01Z", "0", "0", "12.50"),
                                       ("123456", "2026-12-01T10:00:02Z", "40.00", "0", "0"))]
        self.assert_says(self.run_case(drafts=drafts).warnings, "a conta 123456 da agência 0001 usou cheque especial")

    def test_parcela_de_cheque_especial_e_aviso_com_o_valor(self) -> None:
        drafts = [rows(), extrato_rows(("123456", "2026-12-01T10:00:01Z", "0", "0", "70.00"),
                                       ("123456", "2026-12-01T10:00:01Z", "70.00", "0", "70.00"))]
        drafts[1]["datasets"]["lancamentos"][1].update({"chaveSaldo": "overdraft", "valor": "70.00"})
        self.assert_says(self.run_case(drafts=drafts).warnings,
                         "a conta 123456 da agência 0001 tem uma parcela de cheque especial de 70.00")
        self.assert_says(self.run_case(drafts=drafts).warnings,
                         "ela traz o saldo da chave de cheque especial, e a linha principal, o saldo real")

    def test_parcela_de_cheque_especial_por_ultimo_nao_e_o_saldo_da_conta(self) -> None:
        # A principal deixa a conta em 40,00 (o CONTAS); a parcela, no mesmo instante e depois
        # dela, traz o saldo da chave de cheque especial e não entra na comparação.
        drafts = [rows(), extrato_rows(("123456", "2026-12-01T10:00:01Z", "40.00", "0", "0"),
                                       ("123456", "2026-12-01T10:00:01Z", "0", "0", "20.00"))]
        drafts[1]["datasets"]["lancamentos"][1].update({"chaveSaldo": "overdraft", "valor": "20.00"})
        report = self.run_case(drafts=drafts)
        self.assertFalse(any("o saldo após o último lançamento" in w for w in report.warnings), report.warnings)

    def test_valor_bloqueado_no_periodo_e_aviso(self) -> None:
        drafts = [rows(), extrato_rows(("123456", "2026-12-01T10:00:01Z", "20.00", "20.00", "0"))]
        self.assert_says(self.run_case(drafts=drafts).warnings, "a conta 123456 da agência 0001 teve valor bloqueado")

    def test_cheque_especial_ausente_conta_zero_no_saldo(self) -> None:
        # Sem o cheque especial medido, o saldo é disponível + bloqueado: 40,00 bate com o CONTAS.
        drafts = [rows(), extrato_rows(("123456", "2026-12-01T10:00:01Z", "40.00", "0", None))]
        report = self.run_case(drafts=drafts)
        self.assertFalse(any("o saldo após o último lançamento" in w or "não pôde ser comparado" in w
                             for w in report.warnings), report.warnings)

    def test_saldo_ausente_nas_linhas_e_aviso(self) -> None:
        drafts = [rows(), extrato_rows(("123456", "2026-12-01T10:00:01Z", "40.00"))]
        drafts[0]["datasets"]["contas_investigadas"][0]["saldoFinal"] = None
        self.assert_says(self.run_case(drafts=drafts).warnings, "não pôde ser comparado")

    def test_instante_ilegivel_ou_sem_fuso_e_erro(self) -> None:
        for instante in ("ontem", "2026-12-01T10:00:01"):
            with self.subTest(instante=instante):
                drafts = [rows(), extrato_rows(("123456", instante, "40.00"))]
                self.assert_says(self.run_case(drafts=drafts).errors, "não tem instante legível")

    def test_titulares_sem_identificacao_nem_dispositivo_e_aviso(self) -> None:
        files = case()
        files["TITULARES"][0][9:11] = ["", ""]
        files["TITULARES"][1][25:27] = ["", ""]
        warnings = self.run_case(files).warnings
        self.assert_says(warnings, "TITULARES: 1 linha(s) sem documento de identificação (campos 10 e 11;")
        self.assert_says(warnings, "TITULARES: 1 linha(s) sem dispositivo cadastrado (campos 26 e 27;")

    def test_documento_da_ordem_sem_conta_e_aviso_pela_posicao(self) -> None:
        documento_errado = "00000000001"
        warnings = self.run_case(documents=["000.000.000-00", documento_errado]).warnings
        self.assert_says(warnings, "o(s) documento(s) nº 2 da ordem")
        self.assertFalse(any(documento_errado in w for w in warnings), "o aviso ecoou o documento")

    def test_sem_a_lista_da_ordem_a_conferencia_diz_o_que_nao_viu(self) -> None:
        folder, drafts_folder = self.write(case(), drafts=coherent_drafts())
        self.assert_says(conf.conferir(folder, CASO, drafts_folder).warnings,
                         "sem --documentos, o documento da ordem sem nenhuma conta NÃO foi conferido")

    def test_lista_da_ordem_vazia_e_erro(self) -> None:
        self.assert_says(self.run_case(documents=[""]).errors, "não traz documento nenhum")

    def test_saldo_devedor_sem_movimento_e_aviso(self) -> None:
        # A conta 654321 não tem lançamento: só as linhas do rascunho mostram o sinal.
        # No arquivo, -12,50 sai 1250 (o CONTAS escreve o saldo sem sinal).
        files = case()
        files["CONTAS"][1] = conta("0001", "654321", "2", "500", "1250")
        report = self.run_case(files, drafts=[rows(saldo_final="-12.50")])
        self.assertEqual([], report.errors)
        self.assert_says(report.warnings, "a conta 654321 da agência 0001 tem saldo final devedor (-12.50)")

    def test_sem_as_linhas_do_rascunho_a_conferencia_diz_o_que_nao_viu(self) -> None:
        folder, _ = self.write(case())
        self.assert_says(conf.conferir(folder, CASO, None).warnings, "o saldo devedor NÃO foi conferido")

    # ------------------------------------------------------------ completude do reenvio
    def test_linha_do_final_que_falta_no_rascunho_bloqueia(self) -> None:
        anterior = self.rows_folder("final", final(rows(), titulares_rows(("c1", "p1"), ("c1", "p2"))))
        report = self.run_case(drafts=[rows(), titulares_rows(("c1", "p1"))], previous=anterior)
        self.assertEqual([], report.errors)
        self.assert_says(report.blocks, "br.bcb.simba.titulares partes: a linha contaId=c1, parteId=p2")

    def test_bloqueio_sai_com_codigo_de_erro(self) -> None:
        folder, drafts_folder = self.write(case(), drafts=[rows(), titulares_rows(("c1", "p1"))])
        anterior = self.rows_folder("final", final(rows(), titulares_rows(("c1", "p1"), ("c1", "p2"))))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = conf.main([str(folder), CASO, "--rascunhos", str(drafts_folder), "--anterior", str(anterior)])
        self.assertEqual(1, code)
        self.assertIn("BLOQUEIO:", out.getvalue())

    def test_justificativa_registrada_libera_a_linha(self) -> None:
        anterior = self.rows_folder("final", final(rows(), titulares_rows(("c1", "p1"), ("c1", "p2"))))
        justificativas = self.root / "justificativas.json"
        justificativas.write_text(json.dumps([{
            "documentId": "br.bcb.simba.titulares", "dataset": "partes",
            "key": {"contaId": "c1", "parteId": "p2"}, "motivo": "CPF corrigido no cadastro"}]), encoding="utf-8")
        report = self.run_case(drafts=[rows(), titulares_rows(("c1", "p1"))], previous=anterior,
                               justifications=justificativas)
        self.assertEqual([], report.blocks)
        self.assert_says(report.released, "contaId=c1, parteId=p2")

    def test_justificativa_sem_motivo_nao_libera(self) -> None:
        anterior = self.rows_folder("final", final(rows(), titulares_rows(("c1", "p1"), ("c1", "p2"))))
        justificativas = self.root / "justificativas.json"
        justificativas.write_text(json.dumps([{
            "documentId": "br.bcb.simba.titulares", "dataset": "partes",
            "key": {"contaId": "c1", "parteId": "p2"}, "motivo": " "}]), encoding="utf-8")
        report = self.run_case(drafts=[rows(), titulares_rows(("c1", "p1"))], previous=anterior,
                               justifications=justificativas)
        self.assert_says(report.blocks, "parteId=p2")
        self.assert_says(report.errors, "justificativa sem motivo")

    def test_linha_nova_e_so_aviso(self) -> None:
        anterior = self.rows_folder("final", final(rows(), titulares_rows(("c1", "p1"))))
        report = self.run_case(drafts=[rows(), titulares_rows(("c1", "p1"), ("c2", "p3"))], previous=anterior)
        self.assertEqual([], report.blocks)
        self.assert_says(report.warnings, "br.bcb.simba.titulares partes: 1 linha(s) novas")

    def test_documento_do_final_sem_rascunho_bloqueia(self) -> None:
        anterior = self.rows_folder("final", final(rows(), titulares_rows(("c1", "p1"))))
        report = self.run_case(drafts=[rows()], previous=anterior)
        self.assert_says(report.blocks, "br.bcb.simba.titulares: há envio aprovado anterior e não há rascunho novo")

    def test_anterior_inexistente_e_erro_e_sai_com_1(self) -> None:
        folder, drafts_folder = self.write(case(), drafts=[rows()])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = conf.main([str(folder), CASO, "--rascunhos", str(drafts_folder),
                              "--anterior", str(self.root / "nao-existe")])
        self.assertEqual(1, code)
        self.assertIn("--anterior:", out.getvalue())

    def test_anterior_sem_o_final_de_um_rascunho_bloqueia(self) -> None:
        anterior = self.rows_folder("final", final(rows()))
        report = self.run_case(drafts=[rows(), titulares_rows(("c1", "p1"))], previous=anterior)
        self.assert_says(report.blocks, "br.bcb.simba.titulares: há rascunho novo e a pasta do envio anterior não traz")

    def test_anterior_vazia_e_erro(self) -> None:
        (self.root / "vazia").mkdir()
        self.assert_says(self.run_case(previous=self.root / "vazia").errors, "não tem resposta de /rows")

    def test_rascunho_como_base_e_erro(self) -> None:
        anterior = self.rows_folder("final", [rows(), titulares_rows(("c1", "p1"))])
        self.assert_says(self.run_case(previous=anterior).errors, "tem status 'Draft'; aqui vai Final")

    def test_dois_finais_do_mesmo_documento_e_erro(self) -> None:
        anterior = self.rows_folder("final", final(rows(), rows()))
        self.assert_says(self.run_case(previous=anterior).errors, "há mais de uma resposta de br.bcb.simba.contas")

    def test_conjunto_do_final_fora_do_contrato_bloqueia(self) -> None:
        antigo = rows()
        antigo["datasets"]["contas_renomeadas"] = [{"contaId": "c1"}]
        anterior = self.rows_folder("final", final(antigo))
        self.assert_says(self.run_case(previous=anterior).blocks,
                         "contas_renomeadas: o conjunto do envio anterior não existe no contrato atual")

    def test_documento_de_fora_do_simba_na_base_e_erro(self) -> None:
        anterior = self.rows_folder("final", final(rows(), {"documentId": "br.bcb.cadoc-4010", "datasets": {}}))
        self.assert_says(self.run_case(previous=anterior).errors, "br.bcb.cadoc-4010: não é documento do SIMBA")

    def test_justificativas_sem_anterior_e_erro(self) -> None:
        justificativas = self.root / "justificativas.json"
        justificativas.write_text("[]", encoding="utf-8")
        folder, drafts_folder = self.write(case(), drafts=[rows()])
        report = conf.conferir(folder, CASO, drafts_folder, None, justificativas)
        self.assert_says(report.errors, "--justificativas só vale com --anterior")

    def test_justificativas_que_nao_sao_lista_e_erro(self) -> None:
        anterior = self.rows_folder("final", final(rows()))
        justificativas = self.root / "justificativas.json"
        justificativas.write_text("{}", encoding="utf-8")
        self.assert_says(self.run_case(previous=anterior, justifications=justificativas).errors,
                         "as justificativas são uma lista")


class GabaritoChequeEspecial(unittest.TestCase):
    """O aviso que acompanha a limitação fixada no gabarito de cheque especial.

    No cenário b-cheque-especial, as linhas das parcelas de cheque especial trazem o saldo da
    chave de cheque especial, e a parcela da tarifa sai com o código e a contraparte do Pix da
    mesma transação: são limitações declaradas, não a resposta certa. Elas só valem com o aviso
    de cada parcela e da transação, lido aqui das próprias linhas do cenário.
    """

    SCENARIO = conf.ROOT / "tools" / "homologation" / "simba" / "b-cheque-especial"

    def drafts(self) -> dict[str, dict]:
        rows = self.SCENARIO / "rows" / "extrato"
        datasets = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in rows.glob("*.json")}
        return {conf.EXTRATO_DOCUMENT: datasets}

    def test_cada_parcela_de_cheque_especial_tem_o_aviso(self) -> None:
        report = conf.Report()
        conf.check_entry_balances(self.drafts(), report)
        parcelas = sorted(w.split(" tem uma parcela de cheque especial de ")[0].split("a conta ")[1].split(" ")[0]
                          + " " + w.split(" tem uma parcela de cheque especial de ")[1].split(" ")[0]
                          for w in report.warnings if " tem uma parcela de cheque especial de " in w)
        # As linhas 1, 4, 6 e 8 do esperado: 70,00 (crédito que quita a dívida), 70,00 (Pix),
        # 1,00 (tarifa) e 20,00 (Pix com bloqueio).
        self.assertEqual(["2222222 1.00", "2222222 70.00", "2222222 70.00", "2222223 20.00"], parcelas)

    def test_a_transacao_com_tarifa_e_cheque_especial_tem_o_aviso(self) -> None:
        report = conf.Report()
        conf.check_entry_balances(self.drafts(), report)
        avisos = [w for w in report.warnings if "transação com tarifa e cheque especial" in w]
        # As duas parcelas de cheque especial da transação (70,00 do Pix e 1,00 da tarifa) podem
        # ser da tarifa: nada as liga a ela. O aviso sai para cada uma.
        self.assertEqual(2, len(avisos), report.warnings)
        self.assertTrue(any("parcela de 1.00" in w for w in avisos), avisos)
        self.assertTrue(any("parcela de 70.00" in w for w in avisos), avisos)


class Deriva(unittest.TestCase):
    """O que o script copia dos documentos continua igual ao que os documentos escrevem."""

    def contract(self, folder: str) -> dict:
        return yaml.safe_load((conf.ROOT / "br" / "bcb" / "simba" / folder / "contract.yaml").read_text(encoding="utf-8"))

    def fields(self, folder: str, dataset: str) -> set[str]:
        for d in self.contract(folder)["datasets"]:
            if d["name"] == dataset:
                return {f["name"] for f in d["fields"]}
        self.fail(f"{folder} não declara {dataset}")

    def test_a_frase_da_contraparte_vazia_e_a_do_template(self) -> None:
        template = (conf.ROOT / "br" / "bcb" / "simba" / "origem-destino" / "template.tpl").read_text(encoding="utf-8")
        self.assertIn("\t" + conf.UNIDENTIFIED + "\t", template)

    def test_os_campos_do_contas_lidos_existem(self) -> None:
        for dataset in conf.CONTAS_SETS:
            self.assertLessEqual({"numeroAgencia", "numeroConta", "saldoInicial", "saldoFinal"},
                                 self.fields("contas", dataset))

    def test_os_campos_do_extrato_lidos_existem(self) -> None:
        self.assertLessEqual({"numeroAgencia", "numeroConta", "horaLancamento", "saldoApos", "bloqueadoApos",
                              "chequeEspecialApos"},
                             self.fields("extrato", conf.EXTRATO_ENTRIES))

    def test_os_ids_dos_documentos_existem(self) -> None:
        ids = {self.contract(f)["metadata"]["id"] for f in ("contas", "extrato")}
        self.assertEqual({conf.CONTAS_DOCUMENT, conf.EXTRATO_DOCUMENT}, ids)


class Mutations(unittest.TestCase):
    """Os avisos e bloqueios que uma decisão exige, vistos sumindo: sem eles, o teste reprova."""

    def failures_with(self, target: str, replacement, test: str) -> int:
        with mock.patch.object(conf, target, replacement):
            result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
                unittest.defaultTestLoader.loadTestsFromName(test, Conferencia))
        return len(result.failures)

    def test_tirar_o_aviso_de_saldo_devedor_reprova_o_teste(self) -> None:
        self.assertEqual(1, self.failures_with(
            "check_overdraft_rows", lambda drafts, report: None, "test_saldo_devedor_sem_movimento_e_aviso"))

    def test_tirar_o_aviso_de_documento_sem_conta_reprova_o_teste(self) -> None:
        self.assertEqual(1, self.failures_with(
            "check_case_documents", lambda path, titulares, report: None,
            "test_documento_da_ordem_sem_conta_e_aviso_pela_posicao"))

    def test_tirar_o_aviso_de_tarifa_com_cheque_especial_reprova_o_gabarito(self) -> None:
        silenciado = conf.check_entry_balances

        def sem_o_aviso(drafts, report):
            silenciado(drafts, report)
            report.warnings[:] = [w for w in report.warnings if "transação com tarifa e cheque especial" not in w]

        with mock.patch.object(conf, "check_entry_balances", sem_o_aviso):
            result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
                unittest.defaultTestLoader.loadTestsFromName(
                    "test_a_transacao_com_tarifa_e_cheque_especial_tem_o_aviso", GabaritoChequeEspecial))
        self.assertEqual(1, len(result.failures))

    def test_ler_a_parcela_como_saldo_da_conta_reprova_o_teste(self) -> None:
        self.assertEqual(1, self.failures_with(
            "_carries_the_account_balance", lambda row: True,
            "test_parcela_de_cheque_especial_por_ultimo_nao_e_o_saldo_da_conta"))

    def test_exigir_extrato_sem_movimento_reprova_o_teste(self) -> None:
        def ausente_e_sempre_erro(files, missing, folder, report):
            for path in missing.values():
                report.error(f"{path.name}: não encontrado em {folder}")

        self.assertEqual(1, self.failures_with(
            "check_movement_files", ausente_e_sempre_erro,
            "test_sem_movimento_extrato_e_od_ausentes_e_aviso_para_entregar_o_vazio"))

    def test_aceitar_extrato_vazio_com_movimento_reprova_o_teste(self) -> None:
        self.assertEqual(1, self.failures_with(
            "check_movement_files", lambda files, missing, folder, report: None,
            "test_conta_movimentada_com_extrato_vazio_e_erro"))

    def test_tirar_o_aviso_da_parcela_reprova_o_gabarito(self) -> None:
        silenciado = conf.check_entry_balances

        def sem_o_aviso(drafts, report):
            silenciado(drafts, report)
            report.warnings[:] = [w for w in report.warnings if "tem uma parcela de cheque especial de" not in w]

        with mock.patch.object(conf, "check_entry_balances", sem_o_aviso):
            result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
                unittest.defaultTestLoader.loadTestsFromName(
                    "test_cada_parcela_de_cheque_especial_tem_o_aviso", GabaritoChequeEspecial))
        self.assertEqual(1, len(result.failures))

    def test_aceitar_extrato_de_conta_sem_movimento_reprova_o_teste(self) -> None:
        self.assertEqual(1, self.failures_with(
            "moved_accounts", lambda contas: {(conf.field(r, 2), conf.field(r, 3)) for r in contas},
            "test_conta_do_extrato_sem_movimento_no_contas_e_erro"))

    def test_aceitar_conta_movimentada_sem_extrato_reprova_o_teste(self) -> None:
        self.assertEqual(1, self.failures_with(
            "unstated_accounts", lambda moved, statement: set(),
            "test_conta_movimentada_sem_linha_no_extrato_e_erro"))

    def test_rebaixar_o_bloqueio_a_aviso_reprova_o_teste(self) -> None:
        self.assertEqual(1, self.failures_with(
            "Report", _ReportBlocksAsWarnings, "test_linha_do_final_que_falta_no_rascunho_bloqueia"))
        self.assertEqual(1, self.failures_with(
            "Report", _ReportBlocksAsWarnings, "test_bloqueio_sai_com_codigo_de_erro"))


class _ReportBlocksAsWarnings(conf.Report):
    """A mutação: a linha perdida vira só um aviso."""

    def block(self, text: str) -> None:
        self.warn(text)


if __name__ == "__main__":
    unittest.main(verbosity=1)
