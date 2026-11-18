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
  * toda consulta alcança o parâmetro `documentos`, direto ou pela cadeia de valores
    de consulta e de `from` — sem isso, uma lista opcional ausente (`contas`) deixa uma
    consulta ler todas as contas da instituição. A exceção é a que lê a própria
    instituição (a organização do Midaz), que não é dado de cliente.

Só a biblioteca padrão e o pyyaml do validador:

    python3 tools/test_simba.py
"""

from __future__ import annotations

import copy
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
        self.assertGreaterEqual(len(bindings(ROOT)), 3)

    def test_a_mesma_consulta_tem_o_mesmo_texto(self) -> None:
        self.assertEqual([], divergent_queries(bindings(ROOT)))

    def test_todo_documento_declara_as_contas_do_caso(self) -> None:
        self.assertEqual([], missing_case_accounts(bindings(ROOT)))

    def test_toda_consulta_de_cliente_chega_aos_investigados(self) -> None:
        self.assertEqual([], unscoped_queries(bindings(ROOT)))


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

    def test_consulta_sem_os_investigados_e_pega(self) -> None:
        found = copy.deepcopy(self.found)
        query = queries_of(found["contas"])[CASE_ACCOUNTS]
        query["filters"] = [c for c in query["filters"]
                            if not any(isinstance(v, dict) and v.get("parameter") == INVESTIGATED
                                       for v in c.get("values") or [])]
        self.assertTrue(any(f"'{CASE_ACCOUNTS}'" in p for p in unscoped_queries(found)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
