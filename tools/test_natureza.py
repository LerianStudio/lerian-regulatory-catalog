#!/usr/bin/env python3
"""A regra com que tools/natureza.py lê a natureza das rubricas no elenco COSIF.

Sobre um trecho de elenco escrito à mão, com as formas que o PDF do BACEN tem: a
retificadora "(-)" no ativo e no patrimônio líquido, a bilateral "(+/-)", a marca
partida pela extração ("(- )"), e o grupo 8, onde a marca não quer dizer
retificadora. Só biblioteca padrão:

    python3 tools/test_natureza.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import natureza  # noqa: E402

ELENCO = """
I - ATIVO
1.6.0.00.00.00-7 OPERAÇÕES DE CRÉDITO
1.6.1.00.00.00-4 Empréstimos e Direitos Creditórios  Descontados
1.6.1.20.00.00-2 EMPRÉSTIMOS
1.6.1.20.01.00-1 Empréstimos
1.6.1.20.01.10-4 Saldo Contratual
1.6.1.20.01.14-2 (+/-) Prêmio ou Desconto
1.6.1.20.01.60-9 (-) Perda Esperada Associada ao Ri sco de Crédito
2.3.2.10.30.00-1 (- ) Depreciação acumulada
3.0.9.70.00.00-8 TRANSAÇÕES DE PAGAMENTO
II - PASSIVO
4.1.1.00.00.00-1 Depósitos à Vista
6.1.1.50.00.00-9 (-) CAPITAL A REALIZAR
7.1.1.00.00.00-6 Rendas de Operações de Crédito
8.1.1.00.00.00-2 (-) Despesas de Captação
8.1.1.90.00.00-3 DESPESAS DE DEBÊNTURES
9.0.9.70.00.00-7 TRANSAÇÕES DE PAGAMENTO
"""


class Natureza(unittest.TestCase):
    def setUp(self) -> None:
        self.accounts = natureza.parse_elenco(ELENCO)
        self.sides, self.unmarked = natureza.natures_of(self.accounts)
        self.table = natureza.minimal_table(self.sides)

    def side(self, code: str) -> str:
        return natureza.decide(self.table, natureza.prefix_of(code))

    def test_o_prefixo_e_a_subarvore_da_rubrica(self) -> None:
        self.assertEqual(natureza.prefix_of("1.6.1.20.01.60-9"), "161200160")
        self.assertEqual(natureza.prefix_of("1.6.0.00.00.00-7"), "16")
        self.assertEqual(natureza.prefix_of("3.0.9.70.00.00-8"), "30970")

    def test_a_retificadora_inverte_o_lado_da_secao(self) -> None:
        self.assertEqual(self.side("1.6.1.20.01.60-9"), "credit", "perda esperada, credora dentro do ativo")
        self.assertEqual(self.side("2.3.2.10.30.00-1"), "credit", "a marca partida pela extração é a mesma marca")
        self.assertEqual(self.side("6.1.1.50.00.00-9"), "debit", "capital a realizar, devedor dentro do PL")

    def test_a_bilateral_e_a_sem_marca_herdam_a_mae(self) -> None:
        self.assertEqual(self.side("1.6.1.20.01.14-2"), "debit")
        self.assertEqual(self.side("1.6.1.20.01.10-4"), "debit")
        self.assertEqual(self.side("4.1.1.00.00.00-1"), "credit")
        self.assertEqual(self.side("7.1.1.00.00.00-6"), "credit")

    def test_compensacao_ativa_e_passiva(self) -> None:
        self.assertEqual(self.side("3.0.9.70.00.00-8"), "debit")
        self.assertEqual(self.side("9.0.9.70.00.00-7"), "credit")

    def test_o_grupo_8_e_devedor_inteiro(self) -> None:
        self.assertEqual(self.side("8.1.1.00.00.00-2"), "debit", "a marca no grupo 8 diz 'subtrai do resultado'")
        self.assertEqual(self.side("8.1.1.90.00.00-3"), "debit", "a omissão da marca não troca o sinal")
        self.assertEqual([code for code, _ in self.unmarked], ["8.1.1.90.00.00-3"], "e fica listada para revisão")

    def test_a_tabela_minima_da_a_toda_rubrica_o_lado_da_regra(self) -> None:
        for prefix, side in self.sides.items():
            self.assertEqual(natureza.decide(self.table, prefix), side, prefix)
        self.assertNotIn("161200110", self.table, "rubrica com o lado da mãe não é escrita")
        self.assertIn("161200160", self.table)

    def test_o_arquivo_gerado_e_legivel(self) -> None:
        import yaml

        titles = {natureza.prefix_of(code): (code, title) for code, title in self.accounts}
        text = natureza.render(self.table, titles, self.unmarked, "ab" * 32)
        loaded = yaml.safe_load(text)
        self.assertEqual(loaded["sha256"], "ab" * 32)
        self.assertEqual(loaded["byPrefix"], self.table)
        self.assertTrue(all(isinstance(prefix, str) for prefix in loaded["byPrefix"]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
