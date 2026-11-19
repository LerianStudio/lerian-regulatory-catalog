#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""O que os documentos do SIMBA (br/bcb/simba/<arquivo>/) têm de ter em comum.

Os cinco arquivos de um caso são gerados um a um, cada um pelo seu binding, e o
órgão os cruza (as contas do CONTAS são as do TITULARES e do EXTRATO). Duas
conferências que o validador, documento a documento, não faz:

  * a mesma consulta tem o mesmo texto em todo binding do SIMBA que a declara — a
    `contas_do_caso` reescrita num deles, com um filtro a menos, faz um arquivo falar
    de outras contas sem erro nenhum;
  * o conjunto `lancamentos` do EXTRATO e o do ORIGEM-DESTINO têm o mesmo grão, e todo
    campo do ORIGEM-DESTINO existe no EXTRATO com o mesmo tipo — os dois numeram os
    lançamentos igual (o campo 2 do ORIGEM-DESTINO é o campo 1 do EXTRATO);
  * todo cenário de gabarito do SIMBA (tools/homologation/simba/<cenário>/) traz o
    `mutants.json`: o teste do motor que lê os cenários pula as quebras quando o
    arquivo falta, e o gabarito passaria sem provar que pega alguma coisa;
  * toda consulta de lançamentos ou de saldo do razão deixa de fora as reservas e
    liberações do Midaz (ON_HOLD, RELEASE): a transferência que passou por reserva sai uma
    vez só, e o saldo não conta a reserva como débito;
  * as consultas que viram linha tiram a operação de valor zero (o Midaz grava 0,00 na
    parte do disponível de um saque inteiro no cheque especial);
  * as somas de saldo do CONTAS contam a chave de sistema overdraft, onde o Midaz grava a
    parte de um saque tirada do cheque especial: sem ela, a conta nunca sai devedora;
  * toda consulta alcança o parâmetro `documentos`, direto ou pela cadeia de valores
    de consulta e de `from` — sem isso, uma lista opcional ausente (`contas`) deixa uma
    consulta ler todas as contas da instituição. A exceção é a que lê a própria
    instituição (a organização do Midaz), que não é dado de cliente.

Só a biblioteca padrão e o pyyaml do validador:

    python3 tools/test_simba.py
"""

from __future__ import annotations

import copy
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FAMILY = Path("br") / "bcb" / "simba"
# A consulta que fixa as contas de um caso: todo documento a declara.
CASE_ACCOUNTS = "contas_do_caso"
# O parâmetro que nomeia os investigados: toda consulta de cliente chega nele.
INVESTIGATED = "documentos"
# Quem lê a própria instituição não lê cliente: fica fora da conferência acima.
INSTITUTION_SOURCES = {("midaz_onboarding", "organization")}


def bindings(root: Path) -> dict[str, dict]:
    """O binding de exemplo de cada documento do SIMBA, pelo nome da pasta."""
    found = {}
    for path in sorted((root / FAMILY).glob("*/binding.example.yaml")):
        found[path.parent.name] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return found


ENTRIES = "lancamentos"
GOLDEN = Path("tools") / "homologation" / "simba"
LEDGER = ("midaz_transaction", "operation")
HOLD_TYPES = {"ON_HOLD", "RELEASE"}
# Lida pelo id de uma entrada que já passou pelo filtro: não lista nem soma nada.
LOOKUP_QUERIES = {"lancamentos_descricao"}
# As consultas que viram linha do EXTRATO e do ORIGEM-DESTINO: sem a operação de 0,00
# que o Midaz grava quando a parte do disponível de um saque no cheque especial é zero.
ENTRY_QUERIES = {"lancamentos_dados", "pernas_lancamento"}
# As somas de saldo do CONTAS.
BALANCE_QUERIES = {"saldo_inicial_caso", "saldo_final_caso", "saldo_inicial_contraparte", "saldo_final_contraparte"}


def _filters(query: dict) -> list[dict]:
    return [c for c in query.get("filters") or [] if isinstance(c, dict)]


def holds_not_excluded(found: dict[str, dict]) -> list[str]:
    """As consultas do razão que listam ou somam sem tirar as reservas e liberações."""
    problems = []
    for document, binding in found.items():
        for name, query in queries_of(binding).items():
            if (query.get("dataSource"), query.get("table")) != LEDGER or name in LOOKUP_QUERIES:
                continue
            if not any(c.get("field") == "type" and c.get("operator") == "nin" and HOLD_TYPES <= set(c.get("values") or [])
                       for c in _filters(query)):
                problems.append(f"{document}: a consulta '{name}' não tira ON_HOLD e RELEASE")
    return problems


def zero_entries_kept(found: dict[str, dict]) -> list[str]:
    """As consultas de linha que não tiram a operação de valor zero."""
    problems = []
    for document, binding in found.items():
        for name, query in queries_of(binding).items():
            if name in ENTRY_QUERIES and not any(
                    c.get("field") == "amount" and c.get("operator") == "gt" and c.get("values") == ["0"]
                    for c in _filters(query)):
                problems.append(f"{document}: a consulta '{name}' não tira a operação de valor zero")
    return problems


def overdraft_left_out(found: dict[str, dict]) -> list[str]:
    """As somas de saldo do CONTAS que deixam de fora a chave overdraft."""
    queries = queries_of(found.get("contas", {}))
    problems = [f"contas: a soma '{name}' não existe" for name in sorted(BALANCE_QUERIES - set(queries))]
    for name in sorted(BALANCE_QUERIES & set(queries)):
        if any(c.get("field") == "balance_key" for c in _filters(queries[name])):
            problems.append(f"contas: a soma '{name}' filtra a chave de saldo; a chave overdraft entra no saldo")
    return problems


def scenarios_without_mutants(root: Path) -> list[str]:
    """Os cenários de gabarito do SIMBA sem o arquivo das quebras que eles têm de pegar."""
    return [d.name for d in sorted((root / GOLDEN).iterdir())
            if (d / "scenario.json").is_file() and not (d / "mutants.json").is_file()]


def contracts(root: Path) -> dict[str, dict]:
    """O contrato de cada documento do SIMBA, pelo nome da pasta."""
    found = {}
    for path in sorted((root / FAMILY).glob("*/contract.yaml")):
        found[path.parent.name] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return found


def entries_mismatch(found: dict[str, dict]) -> list[str]:
    """Onde o `lancamentos` do ORIGEM-DESTINO deixa de ser o do EXTRATO."""
    def dataset(document: str) -> dict:
        for d in found.get(document, {}).get("datasets") or []:
            if isinstance(d, dict) and d.get("name") == ENTRIES:
                return d
        return {}

    extrato, od = dataset("extrato"), dataset("origem-destino")
    if not extrato or not od:
        return [f"{ENTRIES}: falta no EXTRATO ou no ORIGEM-DESTINO"]
    problems = []
    if extrato.get("grain") != od.get("grain"):
        problems.append(f"{ENTRIES}: grão {extrato.get('grain')} no EXTRATO e {od.get('grain')} no ORIGEM-DESTINO")
    types = {f.get("name"): f.get("type") for f in extrato.get("fields") or []}
    for f in od.get("fields") or []:
        if types.get(f.get("name")) != f.get("type"):
            problems.append(f"{ENTRIES}.{f.get('name')}: {f.get('type')} no ORIGEM-DESTINO e "
                            f"{types.get(f.get('name'))} no EXTRATO")
    return problems


def queries_of(binding: dict) -> dict[str, dict]:
    return {q["name"]: q for q in binding.get("queries") or []
            if isinstance(q, dict) and isinstance(q.get("name"), str)}


def divergent_queries(found: dict[str, dict]) -> list[str]:
    """As consultas declaradas em mais de um documento com textos diferentes."""
    seen: dict[str, tuple[str, dict]] = {}
    problems = []
    for document, binding in found.items():
        for name, query in queries_of(binding).items():
            if name not in seen:
                seen[name] = (document, query)
            elif seen[name][1] != query:
                problems.append(f"{name}: {seen[name][0]} e {document} declaram textos diferentes")
    return problems


def missing_case_accounts(found: dict[str, dict]) -> list[str]:
    return [document for document, binding in found.items() if CASE_ACCOUNTS not in queries_of(binding)]


def _reads(query: dict) -> tuple[set[str], set[str]]:
    """Os parâmetros e as consultas de que uma consulta depende para ler."""
    parameters, sources = set(), set()
    for condition in query.get("filters") or []:
        if not isinstance(condition, dict):
            continue
        for value in condition.get("values") or []:
            if isinstance(value, dict) and isinstance(value.get("parameter"), str):
                parameters.add(value["parameter"])
            if isinstance(value, dict) and isinstance(value.get("query"), str):
                sources.add(value["query"])
    if isinstance(query.get("from"), str):
        sources.add(query["from"])
    return parameters, sources


def unscoped_queries(found: dict[str, dict]) -> list[str]:
    """As consultas de cliente que não chegam ao parâmetro dos investigados."""
    problems = []
    for document, binding in found.items():
        queries = queries_of(binding)

        def reaches(name: str, path: tuple[str, ...] = ()) -> bool:
            if name in path or name not in queries:
                return False
            parameters, sources = _reads(queries[name])
            return INVESTIGATED in parameters or any(reaches(s, (*path, name)) for s in sources)

        for name, query in queries.items():
            if (query.get("dataSource"), query.get("table")) in INSTITUTION_SOURCES:
                continue
            if not reaches(name):
                problems.append(f"{document}: a consulta '{name}' não chega ao parâmetro {INVESTIGATED}")
    return problems


class SimbaBindings(unittest.TestCase):
    def test_o_catalogo_tem_documentos_do_simba(self) -> None:
        # Controle positivo: sem documento nenhum, as conferências abaixo passariam vazias.
        self.assertEqual({"agencias", "contas", "titulares", "extrato", "origem-destino"}, set(bindings(ROOT)))

    def test_a_mesma_consulta_tem_o_mesmo_texto(self) -> None:
        self.assertEqual([], divergent_queries(bindings(ROOT)))

    def test_todo_documento_declara_as_contas_do_caso(self) -> None:
        self.assertEqual([], missing_case_accounts(bindings(ROOT)))

    def test_toda_consulta_de_cliente_chega_aos_investigados(self) -> None:
        self.assertEqual([], unscoped_queries(bindings(ROOT)))

    def test_reservas_e_liberacoes_ficam_fora(self) -> None:
        self.assertEqual([], holds_not_excluded(bindings(ROOT)))

    def test_operacao_de_valor_zero_nao_vira_linha(self) -> None:
        self.assertEqual([], zero_entries_kept(bindings(ROOT)))

    def test_o_saldo_do_contas_conta_o_cheque_especial(self) -> None:
        self.assertEqual([], overdraft_left_out(bindings(ROOT)))

    def test_todo_cenario_de_gabarito_traz_as_quebras(self) -> None:
        self.assertTrue(any((ROOT / GOLDEN).glob("*/scenario.json")), "nenhum cenário de gabarito")
        self.assertEqual([], scenarios_without_mutants(ROOT))

    def test_os_lancamentos_do_od_sao_os_do_extrato(self) -> None:
        self.assertEqual([], entries_mismatch(contracts(ROOT)))


class Mutations(unittest.TestCase):
    """Cada conferência acima, vista recusando: uma quebra deliberada numa cópia."""

    def setUp(self) -> None:
        self.found = bindings(ROOT)
        self.assertIn("contas", self.found)

    def test_um_filtro_a_menos_numa_copia_da_consulta_e_pego(self) -> None:
        found = copy.deepcopy(self.found)
        query = queries_of(found["contas"])[CASE_ACCOUNTS]
        query["filters"] = query["filters"][1:]
        self.assertTrue(any(p.startswith(CASE_ACCOUNTS) for p in divergent_queries(found)))

    def test_documento_sem_as_contas_do_caso_e_pego(self) -> None:
        found = copy.deepcopy(self.found)
        found["contas"]["queries"] = [q for q in found["contas"]["queries"] if q.get("name") != CASE_ACCOUNTS]
        self.assertIn("contas", missing_case_accounts(found))

    def test_consulta_que_perde_a_cadeia_ate_os_investigados_e_pega(self) -> None:
        # `lancamentos` chega a `documentos` pela consulta `contas_do_caso`; trocada pela
        # consulta da instituicao, que nao le cliente, a cadeia se perde.
        found = copy.deepcopy(self.found)
        query = queries_of(found["contas"])["lancamentos"]
        for condition in query["filters"]:
            for value in condition.get("values") or []:
                if isinstance(value, dict) and value.get("query") == CASE_ACCOUNTS:
                    value["query"] = "declarante"
        self.assertTrue(any("'lancamentos'" in p for p in unscoped_queries(found)))

    def test_consulta_que_volta_a_ler_reservas_e_pega(self) -> None:
        found = copy.deepcopy(self.found)
        query = queries_of(found["extrato"])["lancamentos_dados"]
        query["filters"] = [c for c in query["filters"] if c.get("field") != "type"]
        self.assertTrue(any("'lancamentos_dados'" in p for p in holds_not_excluded(found)))

    def test_linha_de_valor_zero_e_pega(self) -> None:
        found = copy.deepcopy(self.found)
        query = queries_of(found["origem-destino"])["pernas_lancamento"]
        query["filters"] = [c for c in query["filters"] if c.get("field") != "amount"]
        self.assertTrue(any("'pernas_lancamento'" in p for p in zero_entries_kept(found)))

    def test_soma_que_volta_a_tirar_o_cheque_especial_e_pega(self) -> None:
        found = copy.deepcopy(self.found)
        queries_of(found["contas"])["saldo_final_caso"]["filters"].append(
            {"field": "balance_key", "operator": "nin", "values": ["overdraft"]})
        self.assertTrue(any("'saldo_final_caso'" in p for p in overdraft_left_out(found)))

    def test_cenario_sem_as_quebras_e_pego(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / GOLDEN, root / GOLDEN)
            (root / GOLDEN / "a-saldo-e-contraparte" / "mutants.json").unlink()
            self.assertEqual(["a-saldo-e-contraparte"], scenarios_without_mutants(root))

    def test_um_campo_do_od_que_o_extrato_nao_tem_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for d in found["origem-destino"]["datasets"]:
            if d["name"] == ENTRIES:
                d["fields"].append({"name": "campoSoDoOd", "type": "string"})
        self.assertTrue(any("campoSoDoOd" in p for p in entries_mismatch(found)))

    def test_grao_diferente_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for d in found["origem-destino"]["datasets"]:
            if d["name"] == ENTRIES:
                d["grain"] = ["transacaoId"]
        self.assertTrue(any("grão" in p for p in entries_mismatch(found)))

    def test_consulta_sem_os_investigados_e_pega(self) -> None:
        found = copy.deepcopy(self.found)
        query = queries_of(found["contas"])[CASE_ACCOUNTS]
        query["filters"] = [c for c in query["filters"]
                            if not any(isinstance(v, dict) and v.get("parameter") == INVESTIGATED
                                       for v in c.get("values") or [])]
        self.assertTrue(any(f"'{CASE_ACCOUNTS}'" in p for p in unscoped_queries(found)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
