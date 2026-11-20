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
  * as consultas que viram linha mantêm a operação de valor zero (o Midaz grava 0,00 na
    parte do disponível de um saque inteiro no cheque especial, e é ela que traz o saldo
    real da conta);
  * as somas de saldo do CONTAS contam a chave de sistema overdraft, onde o Midaz grava a
    parte de um saque tirada do cheque especial: sem ela, a conta nunca sai devedora;
  * toda consulta alcança o parâmetro `documentos`, direto ou pela cadeia de valores
    de consulta e de `from` — sem isso, uma lista opcional ausente (`contas`) deixa uma
    consulta ler todas as contas da instituição. A exceção é a que lê a própria
    instituição (a organização do Midaz), que não é dado de cliente;
  * o TITULARES escreve o nome do país (campo 15) pela tabela de países da Receita, e
    as duas consultas de titular traduzem o código ISO com o mesmo `case`, igual à
    tabela, em maiúscula e em minúscula (`br` é o Brasil, não o exterior); sigla de UF ou país sem tradução viram um marcador ("00", "-"), não uma
    recusa, porque quem mora no exterior não tem UF nossa e quem não tem país mora no
    Brasil;
  * o contrato do TITULARES recusa, nos dois conjuntos de titular, quem mora no Brasil
    sem UF da tabela (a IN só dá o 00 para o exterior) e o país informado que a tabela
    não tem;
  * o AGENCIAS, o CONTAS e o TITULARES não saem sem conta nenhuma (`nonEmpty` no conjunto
    das contas do caso: o investigado sem conta é respondido pelo atendimento, sem
    arquivo), e o EXTRATO e o ORIGEM-DESTINO não declaram isso, porque conta sem
    lançamento no período os deixa sem linha: eles declaram `filing.allowEmpty`, e o
    arquivo vazio é gerado e entregue;
  * o tipo de conta do pagador da TED recebida (ORIGEM-DESTINO campo 8) só vira código
    da IN onde o domínio TpCt do STR e a IN casam ao pé da letra (CC 1, PP 2, CI 3); os
    outros valores do domínio ficam com o próprio código, e o resto vira "-" (a TED enviada
    traduz no template, porque o tipo dela vem de um subcaminho JSON); no Pix lerian,
    pelo domínio do SPI (CACC 1, SVGS 2); no Pix JD, o código do fornecedor nunca vira
    código da IN;
  * nenhum `case` de fonte Postgres lê um subcaminho JSON (`a.b`): o motor o recusa na
    carga, e o documento inteiro deixaria de gerar.

Só a biblioteca padrão e o pyyaml do validador:

    python3 tools/test_simba.py
"""

from __future__ import annotations

import copy
import datetime
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

import tabelas_receita

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
# As consultas que viram linha do EXTRATO e do ORIGEM-DESTINO: a operação de 0,00 que o
# Midaz grava quando a parte do disponível de um saque no cheque especial é zero fica nelas;
# é ela que traz o saldo real da conta.
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


def zero_entries_dropped(found: dict[str, dict]) -> list[str]:
    """As consultas de linha que filtram pelo valor, e perderiam a operação de 0,00."""
    problems = []
    for document, binding in found.items():
        for name, query in queries_of(binding).items():
            if name in ENTRY_QUERIES and any(c.get("field") == "amount" for c in _filters(query)):
                problems.append(f"{document}: a consulta '{name}' filtra o valor e perde a operação de 0,00")
    return problems


def overdraft_left_out(found: dict[str, dict]) -> list[str]:
    """As somas de saldo do CONTAS que deixam de fora a chave overdraft."""
    queries = queries_of(found.get("contas", {}))
    problems = [f"contas: a soma '{name}' não existe" for name in sorted(BALANCE_QUERIES - set(queries))]
    for name in sorted(BALANCE_QUERIES & set(queries)):
        if any(c.get("field") == "balance_key" for c in _filters(queries[name])):
            problems.append(f"contas: a soma '{name}' filtra a chave de saldo; a chave overdraft entra no saldo")
    return problems


HOLDER_QUERIES = ("cadastro_titulares", "cadastro_contraparte")
HOLDER_SETS = ("titulares", "titulares_contraparte")
# A data em que o binding leu as linhas vigentes da tabela de países (o comentário dele diz).
COUNTRIES_READ_ON = datetime.date(2026, 11, 19)
NO_UF, NO_COUNTRY = "00", "-"
# UF (sigla) -> código IBGE, a tabela do catálogo de onde o bloco de UF dos bindings é copiado.
UF_TABLE = ROOT / "br" / "bcb" / "simba" / "tabelas" / "uf-ibge.yaml"
LETTERS = [chr(c) for c in range(ord("A"), ord("Z") + 1)] + [chr(c) for c in range(ord("a"), ord("z") + 1)]


def _compute(query: dict, name: str) -> dict:
    return next((c for c in query.get("compute") or [] if isinstance(c, dict) and c.get("as") == name), {})


def country_names_mismatch(found: dict[str, dict]) -> list[str]:
    """Onde as consultas de titular deixam de traduzir país e UF como a tabela e o contrato esperam."""
    # O motor compara o texto como está: o código vem nas duas grafias (BR e br).
    expected = {spelled: {"constant": name} for code, name in
                tabelas_receita.load("paises.txt", COUNTRIES_READ_ON).items() for spelled in (code, code.lower())}
    ufs = {sigla: {"constant": code} for sigla, code in yaml.safe_load(UF_TABLE.read_text(encoding="utf-8")).items()}
    queries = queries_of(found.get("titulares", {}))
    problems = []
    for name in HOLDER_QUERIES:
        if name not in queries:
            problems.append(f"titulares: a consulta '{name}' não existe")
            continue
        country = _compute(queries[name], "nome_pais").get("case") or {}
        if country.get("column") != "addresses.primary.country":
            problems.append(f"titulares: '{name}' não traduz addresses.primary.country em nome_pais")
        when = country.get("when") or {}
        for code in sorted(set(expected) ^ set(when)):
            problems.append(f"titulares: '{name}' traduz o país {code!r}, que a tabela da Receita "
                            + ("não tem" if code in when else "tem e a consulta não"))
        for code in sorted(set(expected) & set(when)):
            if when[code] != expected[code]:
                problems.append(f"titulares: '{name}' escreve {when[code]} para {code}, e a tabela, {expected[code]}")
        if country.get("otherwise") != {"constant": NO_COUNTRY}:
            problems.append(f"titulares: '{name}' não marca o país sem tradução com {NO_COUNTRY!r}")
        uf = _compute(queries[name], "codigo_uf").get("case") or {}
        if uf.get("otherwise") != {"constant": NO_UF}:
            problems.append(f"titulares: '{name}' não marca a UF sem tradução com {NO_UF!r}")
        if uf.get("column") != "addresses.primary.state":
            problems.append(f"titulares: '{name}' não traduz addresses.primary.state em codigo_uf")
        uf_when = uf.get("when") or {}
        for code in sorted(set(ufs) ^ set(uf_when)):
            problems.append(f"titulares: '{name}' traduz a UF {code!r}, que a tabela do IBGE "
                            + ("não tem" if code in uf_when else "tem e a consulta não"))
        for code in sorted(set(ufs) & set(uf_when)):
            if uf_when[code] != ufs[code]:
                problems.append(f"titulares: '{name}' escreve {uf_when[code]} para a UF {code}, e a tabela, {ufs[code]}")
    return problems


def domicile_rules_missing(found: dict[str, dict]) -> list[str]:
    """Os conjuntos de titular sem as recusas da UF de quem mora no Brasil e do país fora da tabela."""
    rules = [r for r in found.get("titulares", {}).get("rules") or [] if isinstance(r, dict)]

    def has(target: str, where: dict, field: str, values: list[str]) -> bool:
        return any(r.get("appliesTo") == target and r.get("severity") == "error"
                   and r.get("where") == where
                   and (r.get("check") or {}).get("notStartsWith") == {"field": field, "values": values}
                   for r in rules)

    problems = []
    for target in HOLDER_SETS:
        if not has(target, {"field": "nomePais", "in": ["Brasil", NO_COUNTRY]}, "codigoUf", ["0"]):
            problems.append(f"titulares: '{target}' não recusa quem mora no Brasil com a UF {NO_UF!r}")
        if not has(target, {"field": "nomePais", "equals": NO_COUNTRY}, "pais", LETTERS):
            problems.append(f"titulares: '{target}' não recusa o país informado que a tabela não tem")
    return problems


# O conjunto das contas do caso de cada arquivo que não sai sem conta nenhuma.
CASE_SETS = {"agencias": "agencias_do_caso", "contas": "contas_investigadas", "titulares": "titulares"}
MOVEMENT_DOCUMENTS = ("extrato", "origem-destino")


def empty_case_rules_off(found: dict[str, dict]) -> list[str]:
    """Onde o `nonEmpty` dos conjuntos de contas do caso falta, ou aparece no EXTRATO e no ORIGEM-DESTINO."""
    def sets(document: str) -> dict[str, dict]:
        return {d.get("name"): d for d in found.get(document, {}).get("datasets") or [] if isinstance(d, dict)}

    problems = [f"{document}: '{name}' não é nonEmpty; sem conta nenhuma o arquivo sairia vazio"
                for document, name in sorted(CASE_SETS.items()) if sets(document).get(name, {}).get("nonEmpty") is not True]
    problems += [f"{document}: '{name}' é nonEmpty; conta sem lançamento no período deixa o arquivo sem linha"
                 for document in MOVEMENT_DOCUMENTS for name, d in sorted(sets(document).items()) if d.get("nonEmpty")]

    def allows_empty(document: str) -> bool:
        return ((found.get(document, {}).get("filing") or {}).get("allowEmpty")) is True

    problems += [f"{document}: não declara filing.allowEmpty; sem lançamento no caso o arquivo vazio seria recusado"
                 for document in MOVEMENT_DOCUMENTS if not allows_empty(document)]
    problems += [f"{document}: declara filing.allowEmpty; sem conta nenhuma ele não sai (nonEmpty)"
                 for document in sorted(CASE_SETS) if allows_empty(document)]
    return problems


# TpCt do STR -> código do campo 8 do ORIGEM-DESTINO (IN :209), só os casamentos literais;
# o domínio sem código na IN fica com o próprio código, para o motivo no campo 18.
TED_ACCOUNT_TYPES = {"CACC": "1", "SVGS": "2", "PP": "2", "CI": "3", "CPAY": "CPAY", "PG": "CPAY", "PAYMENT": "CPAY",
                     "TRAN": "CPAY", "4": "CPAY", "CD": "CD", "CG": "CG", "SLRY": "SLRY"}
# A TED enviada traduz no template: o tipo vem de um subcaminho JSONB, e o motor não aceita
# `case` sobre ele (ver plain_computes_off).
TED_ACCOUNT_QUERIES = {"ted_recebidas": ("sender_account_type", "tipo_conta_pagador")}
# As fontes Postgres do SIMBA: nelas o motor só aceita `case` sobre coluna da tabela ou trazida
# por join, nunca sobre um subcaminho (`a.b`) de uma coluna JSON. As fontes Mongo (CRM,
# metadata do Midaz) aceitam o caminho do documento.
POSTGRES_SOURCES = {"bank_transfer", "midaz_onboarding", "midaz_transaction", "pix_jd", "pix_lerian"}


# Domínio do tipo de conta do SPI -> código do campo 8, só os casamentos literais.
PIX_LERIAN_ACCOUNT_TYPES = {"CACC": "1", "SVGS": "2", "TRAN": "TRAN", "SLRY": "SLRY", "OTHR": "OTHR"}
# O tpConta da JDPI (ListaAPIs 5.5.0) tem as descrições do domínio do SPI: 0 e 2 viram 1 e 2,
# e 1, 3 e 4 ficam com o código SPI equivalente.
PIX_JD_ACCOUNT_TYPES = {"0": "1", "1": "SLRY", "2": "2", "3": "TRAN", "4": "OTHR"}
PIX_ACCOUNT_QUERIES = {
    "pix_lerian_envios": ("destination_account_type", PIX_LERIAN_ACCOUNT_TYPES),
    "pix_lerian_recebimentos": ("source_account_type", PIX_LERIAN_ACCOUNT_TYPES),
    "pix_jd_envios": ("payee_account_type", PIX_JD_ACCOUNT_TYPES),
    "pix_jd_recebimentos": ("payer_account_type", PIX_JD_ACCOUNT_TYPES),
}


def pix_account_type_off(found: dict[str, dict]) -> list[str]:
    """Onde a tradução do tipo de conta da contraparte do Pix deixa de ser a decidida."""
    queries = queries_of(found.get("origem-destino", {}))
    problems = []
    for name, (column, expected) in sorted(PIX_ACCOUNT_QUERIES.items()):
        case = _compute(queries.get(name) or {}, "tipo_conta_od").get("case") or {}
        when = {str(k): (v or {}).get("constant") for k, v in (case.get("when") or {}).items()}
        if case.get("column") != column or when != expected or case.get("otherwise") != {"constant": "-"}:
            problems.append(f"origem-destino: '{name}' traduz {column} como {when}, e a decisão é {expected} (resto '-')")
    return problems


def plain_computes_off(found: dict[str, dict]) -> list[str]:
    """Os `case` de fonte Postgres que leem um subcaminho JSON, que o motor recusa."""
    problems = []
    for document, binding in sorted(found.items()):
        for name, query in sorted(queries_of(binding).items()):
            if query.get("dataSource") not in POSTGRES_SOURCES:
                continue
            for compute in query.get("compute") or []:
                column = ((compute or {}).get("case") or {}).get("column")
                if isinstance(column, str) and "." in column:
                    problems.append(f"{document}: '{name}' ({query.get('dataSource')}) calcula sobre {column}, "
                                    "um subcaminho JSON que o motor recusa numa fonte Postgres")
    return problems


def ted_account_type_off(found: dict[str, dict]) -> list[str]:
    """Onde a tradução do tipo de conta do pagador da TED recebida deixa de ser a decidida."""
    problems = []
    for name, (column, computed) in sorted(TED_ACCOUNT_QUERIES.items()):
        query = queries_of(found.get("origem-destino", {})).get(name)
        if query is None:
            problems.append(f"origem-destino: a consulta '{name}' não existe")
            continue
        case = _compute(query, computed).get("case") or {}
        if case.get("column") != column:
            problems.append(f"origem-destino: '{name}' não traduz {column} em {computed}")
        when = {str(k): (v or {}).get("constant") for k, v in (case.get("when") or {}).items()}
        if when != TED_ACCOUNT_TYPES:
            problems.append(f"origem-destino: '{name}' traduz o tipo de conta como {when}, e a decisão é {TED_ACCOUNT_TYPES}")
        if case.get("otherwise") != {"constant": "-"}:
            problems.append(f"origem-destino: '{name}' não marca o tipo de conta fora do domínio com '-'")
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



# Campos que o template trata como sempre presentes: sem eles a linha cai num ramo errado
# (a TED enviada sem tipo no motivo de fora do domínio; o débito sem tipo de operação fora da
# devolução da TED recebida e a cobrança de dívida de tarifa fora da tarifa), e não na recusa.
REQUIRED_FIELDS = {("origem-destino", "trilho_ted_enviadas", "tipoContaInformado"),
                   ("origem-destino", ENTRIES, "tipoOperacao"), ("extrato", ENTRIES, "tipoOperacao")}


def required_fields_off(found: dict[str, dict]) -> list[str]:
    """Os campos de REQUIRED_FIELDS que o contrato não declara `required: true`."""
    problems = []
    for document, dataset, field in sorted(REQUIRED_FIELDS):
        fields = {f.get("name"): f for d in found.get(document, {}).get("datasets") or []
                  if isinstance(d, dict) and d.get("name") == dataset for f in d.get("fields") or []}
        if fields.get(field, {}).get("required") is not True:
            problems.append(f"{document}: '{dataset}.{field}' não é required: true")
    return problems


# O número da conta sai sem passar pela troca de TAB, CR e LF do macro ascii: um desses
# caracteres partiria o registro (TAB entre colunas, CR LF no fim da linha).
ACCOUNT_FIELDS = {"contas": "numeroConta", "titulares": "numeroConta", "extrato": "numeroConta",
                  "origem-destino": "numeroConta"}
DELIMITERS = ("\t", "\r", "\n")


def account_patterns_off(found: dict[str, dict]) -> list[str]:
    """Os padrões do número da conta que aceitam TAB, CR ou LF (ou recusam um número comum)."""
    import re

    problems = []
    for document, name in sorted(ACCOUNT_FIELDS.items()):
        for d in found.get(document, {}).get("datasets") or []:
            for f in d.get("fields") or []:
                if f.get("name") != name:
                    continue
                pattern = re.compile(f.get("pattern") or ".*")
                leaks = [repr(c) for c in DELIMITERS if pattern.fullmatch("123" + c + "4")]
                if leaks:
                    problems.append(f"{document}: '{d.get('name')}.{name}' aceita {', '.join(leaks)}")
                # Com normalize: digits o valor chega ao pattern já sem o hífen do DV.
                sample = "12345678" if f.get("normalize") == "digits" else "1234567-8"
                if not pattern.fullmatch(sample):
                    problems.append(f"{document}: '{d.get('name')}.{name}' recusa um número de conta comum")
    return problems


# A renda e o faturamento do TITULARES só saem em BRL: o catálogo não converte moeda. O campo 18
# leva o faturamento da pessoa jurídica (tipoPessoa 2) e a renda dos demais; só a figura que vai
# ao arquivo é conferida. Fora do formato ISO (três maiúsculas), a moeda recusa sempre.
HOLDER_CURRENCIES = ("titulares", "titulares_contraparte")
FILED = {"moedaRenda": ("1", "2"), "moedaFaturamento": ("2", "1")}  # campo -> (tipo que imprime, tipo que não)


def _row_refused(contract_doc: dict, dataset: str, row: dict) -> bool:
    import re

    for d in contract_doc.get("datasets") or []:
        if d.get("name") != dataset:
            continue
        for f in d.get("fields") or []:
            value = row.get(f.get("name"))
            if value is not None and f.get("pattern") and not re.fullmatch(f["pattern"], value):
                return True
    for r in contract_doc.get("rules") or []:
        if not isinstance(r, dict) or r.get("appliesTo") != dataset or r.get("severity") != "error":
            continue
        where, check = r.get("where") or {}, (r.get("check") or {}).get("notStartsWith") or {}
        if check.get("field") not in FILED:
            continue
        held = row.get(where.get("field"), "")
        if "equals" in where and held != where["equals"]:
            continue
        if "in" in where and held not in where["in"]:
            continue
        if "notIn" in where and held in where["notIn"]:
            continue
        value = row.get(check["field"], "")
        if any(value.startswith(v) for v in check.get("values") or []):
            return True
    return False


def currency_rules_off(found: dict[str, dict]) -> list[str]:
    """Onde a moeda da figura impressa não é conferida, a da outra figura é, ou BRL e o vazio seriam recusados."""
    doc = found.get("titulares", {})
    problems = []
    for dataset in HOLDER_CURRENCIES:
        for field, (filed, other) in sorted(FILED.items()):
            def refused(tipo: str, value: str) -> bool:
                return _row_refused(doc, dataset, {"tipoPessoa": tipo, field: value})
            for value in ("USD", "BRA", "BZD"):
                if not refused(filed, value):
                    problems.append(f"titulares: '{dataset}.{field}' = {value!r} passaria com tipoPessoa {filed}")
            if refused(other, "USD"):
                problems.append(f"titulares: '{dataset}.{field}' = 'USD' recusaria tipoPessoa {other}, que não o imprime")
            for value in ("BRL", ""):
                if refused(filed, value):
                    problems.append(f"titulares: '{dataset}.{field}' = {value!r} seria recusado")
            for value in ("$BRL", " BRL", "brl"):
                if not refused(other, value):
                    problems.append(f"titulares: '{dataset}.{field}' = {value!r} passaria fora do formato ISO")
    return problems

def exchange_refusal_off(root: Path) -> list[str]:
    """O TITULARES recusa a geração só com operaCambio "sim": o pendente (vazio) deixa o rascunho sair."""
    text = (root / FAMILY / "titulares" / "template.tpl").read_text(encoding="utf-8")
    problems = []
    if '{%- if instituicao.operaCambio == "sim" %}{% fail ' not in text:
        problems.append('titulares: a recusa do campo 28 não é condicionada a operaCambio == "sim"')
    if "operaCambio !=" in text:
        problems.append("titulares: uma comparação com != recusaria o operaCambio pendente (vazio)")
    return problems


# O arquivo é ASCII (IN art. 3º). O macro ascii dos templates converte uma lista fixa de letras;
# todo campo de texto que passa por ele declara um pattern feito dessa mesma lista, e o que o
# macro não converte recusa a geração. Texto livre (a mensagem do Pix, a descrição do
# lançamento) fica fora até o Reporter transliterar: um emoji não pode recusar o arquivo.
ASCII_FIELDS = {
    "agencias": {(ds, f) for ds in ("agencias_do_caso", "agencias_contraparte")
                 for f in ("endereco", "nomeAgencia", "pais", "telefone")} | {("instituicao", "nomeUnicad")},
    "contas": {("instituicao", "nomeUnicad")},
    "titulares": {(ds, f) for ds in ("titulares", "titulares_contraparte")
                  for f in ("nome", "nomeSocial", "logradouro", "complemento", "nomePais", "celular",
                            "outroTelefone", "emailPrincipal", "emailSecundario")}
                 | {("partes", "nome"), ("partes_contraparte", "nome"), ("instituicao", "nomeUnicad")},
    "extrato": {("instituicao", "nomeUnicad")},
    "origem-destino": {(ds, "nome") for ds in ("trilho_pix_lerian_envios", "trilho_pix_lerian_recebimentos",
                                               "trilho_pix_jd_envios", "trilho_pix_jd_recebimentos",
                                               "trilho_ted_enviadas", "titulares_od")}
                      | {("instituicao", "nomeUnicad")},
}
# Argumentos do ascii que não são um campo com pattern: o parâmetro do próprio macro (s), os do
# macro trilho do OD (nome, comentario), a junção de campos do TITULARES (e) e o texto livre.
ASCII_ARGS_OUTSIDE = {"s", "e", "nome", "comentario", "descricao", "descricaoTransacao"}
NOT_ASCII = ("°", "’", "–", "ø", "ß", "🙏")


def _macro_letters(text: str) -> str:
    import re

    macro = re.search(r"\{% macro ascii\(s\) %\}(.*?)\{% endmacro %\}", text, re.S)
    if not macro:
        return ""
    return "".join(sorted({a for a, _ in re.findall(r'replace:"([^":]+):([^"]*)"', macro.group(1))
                           if any(ord(ch) > 126 for ch in a)}))


def ascii_fields_off(root: Path, found: dict[str, dict]) -> list[str]:
    """Campos que passam pelo ascii sem o pattern ASCII do macro, ou com um pattern diferente dele."""
    import re

    problems = []
    for document, wanted in sorted(ASCII_FIELDS.items()):
        text = (root / FAMILY / document / "template.tpl").read_text(encoding="utf-8")
        letters = _macro_letters(text)
        fields = {(d.get("name"), f.get("name")): f for d in found.get(document, {}).get("datasets") or []
                  for f in d.get("fields") or []}
        names = {f for _, f in wanted}
        for arg in sorted(set(re.findall(r"ascii\(([A-Za-z_.]+)\)", text))):
            name = arg.split(".")[-1]
            if name not in names and name not in ASCII_ARGS_OUTSIDE:
                problems.append(f"{document}: ascii({arg}) escreve um campo sem o pattern ASCII")
        for key in sorted(wanted):
            pattern = (fields.get(key) or {}).get("pattern")
            if not pattern:
                problems.append(f"{document}: '{key[0]}.{key[1]}' passa pelo ascii sem pattern")
                continue
            compiled = re.compile(pattern)
            if not compiled.fullmatch("Ab 09 ~!" + letters + "\t\r\n"):
                problems.append(f"{document}: '{key[0]}.{key[1]}' recusa o que o macro converte")
            leaks = [c for c in NOT_ASCII if compiled.fullmatch("a" + c)]
            if leaks:
                problems.append(f"{document}: '{key[0]}.{key[1]}' aceita {''.join(leaks)}, que o macro não converte")
    return problems


def reversed_period_allowed(found: dict[str, dict]) -> list[str]:
    """Os documentos cujo fim não declara notBefore: inicio."""
    problems = []
    for document in sorted(ASCII_FIELDS):
        fim = [p for p in found.get(document, {}).get("parameters") or [] if p.get("name") == "fim"]
        if not fim or fim[0].get("notBefore") != "inicio":
            problems.append(f"{document}: o fim não declara notBefore: inicio")
    return problems


# Os identificadores da metadata (EndToEndId de envio e de recebimento) saem crus no campo 26
# do EXTRATO: a metadata do Midaz aceita TAB, CR e LF, que partiriam o registro.
RAW_METADATA_FIELDS = ("e2e", "e2eEnvio", "e2eRecebimento")
# Uma transação é uma sessão do EXTRATO (campo 27): o motor ordena cada conjunto pelo grão, e
# só com a transação na frente as operações dela ficam juntas.
ENTRY_GRAIN = ["transacaoId", "operacaoId"]


def raw_metadata_unguarded(found: dict[str, dict]) -> list[str]:
    """Os identificadores da metadata que o EXTRATO imprime sem um pattern que recuse TAB, CR e LF."""
    import re

    fields = {f.get("name"): f for d in found.get("extrato", {}).get("datasets") or []
              if d.get("name") == ENTRIES for f in d.get("fields") or []}
    problems = []
    for name in RAW_METADATA_FIELDS:
        pattern = (fields.get(name) or {}).get("pattern")
        if not pattern or any(re.fullmatch(pattern, "E2E" + c + "X") for c in ("\t", "\r", "\n")):
            problems.append(f"extrato: '{ENTRIES}.{name}' aceita TAB, CR ou LF")
    return problems


def entry_grain_off(found: dict[str, dict]) -> list[str]:
    """Onde o grão (e a chave) dos lançamentos não põe a transação antes da operação."""
    problems = []
    for document in ("extrato", "origem-destino"):
        for d in found.get(document, {}).get("datasets") or []:
            if d.get("name") != ENTRIES:
                continue
            if d.get("grain") != ENTRY_GRAIN or (d.get("consolidation") or {}).get("key") != ENTRY_GRAIN:
                problems.append(f"{document}: '{ENTRIES}' não ordena por {ENTRY_GRAIN}")
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


# Só o filtro de pertinência restringe a leitura ao conjunto: um `nin` pelos documentos lê
# todo cliente MENOS os investigados.
MEMBERSHIP = "in"


def _reads(query: dict) -> tuple[set[str], set[str]]:
    """Os parâmetros e as consultas que restringem por pertinência (`in`) o que a consulta lê."""
    parameters, sources = set(), set()
    for condition in query.get("filters") or []:
        if not isinstance(condition, dict) or condition.get("operator") != MEMBERSHIP:
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

    def test_operacao_de_valor_zero_vira_linha(self) -> None:
        self.assertEqual([], zero_entries_dropped(bindings(ROOT)))

    def test_o_saldo_do_contas_conta_o_cheque_especial(self) -> None:
        self.assertEqual([], overdraft_left_out(bindings(ROOT)))

    def test_todo_cenario_de_gabarito_traz_as_quebras(self) -> None:
        self.assertTrue(any((ROOT / GOLDEN).glob("*/scenario.json")), "nenhum cenário de gabarito")
        self.assertEqual([], scenarios_without_mutants(ROOT))

    def test_pais_e_uf_do_titular_seguem_a_tabela(self) -> None:
        self.assertEqual([], country_names_mismatch(bindings(ROOT)))

    def test_o_contrato_recusa_uf_e_pais_sem_traducao(self) -> None:
        self.assertEqual([], domicile_rules_missing(contracts(ROOT)))

    def test_sem_conta_nenhuma_o_cadastro_nao_sai(self) -> None:
        self.assertEqual([], empty_case_rules_off(contracts(ROOT)))

    def test_tipo_de_conta_da_ted_recebida_so_onde_a_in_casa(self) -> None:
        self.assertEqual([], ted_account_type_off(bindings(ROOT)))

    def test_case_em_fonte_postgres_le_coluna_simples(self) -> None:
        self.assertEqual([], plain_computes_off(bindings(ROOT)))

    def test_tipo_de_conta_do_pix_so_onde_a_in_casa(self) -> None:
        self.assertEqual([], pix_account_type_off(bindings(ROOT)))

    def test_os_lancamentos_do_od_sao_os_do_extrato(self) -> None:
        self.assertEqual([], entries_mismatch(contracts(ROOT)))

    def test_campos_que_o_template_supoe_presentes_sao_obrigatorios(self) -> None:
        self.assertEqual([], required_fields_off(contracts(ROOT)))

    def test_numero_da_conta_nao_aceita_tab_cr_nem_lf(self) -> None:
        self.assertEqual([], account_patterns_off(contracts(ROOT)))

    def test_renda_e_faturamento_so_saem_em_brl(self) -> None:
        self.assertEqual([], currency_rules_off(contracts(ROOT)))

    def test_texto_que_passa_pelo_ascii_tem_o_pattern_do_macro(self) -> None:
        self.assertEqual([], ascii_fields_off(ROOT, contracts(ROOT)))

    def test_identificador_da_metadata_nao_parte_o_registro(self) -> None:
        self.assertEqual([], raw_metadata_unguarded(contracts(ROOT)))

    def test_lancamentos_ordenam_pela_transacao(self) -> None:
        self.assertEqual([], entry_grain_off(contracts(ROOT)))

    def test_periodo_invertido_e_recusado(self) -> None:
        self.assertEqual([], reversed_period_allowed(contracts(ROOT)))

    def test_so_o_cambio_declarado_sim_recusa_a_geracao(self) -> None:
        self.assertEqual([], exchange_refusal_off(ROOT))


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

    def test_filtro_que_perde_a_linha_de_valor_zero_e_pego(self) -> None:
        found = copy.deepcopy(self.found)
        queries_of(found["extrato"])["lancamentos_dados"]["filters"].append(
            {"field": "amount", "operator": "gt", "values": ["0"]})
        self.assertTrue(any("'lancamentos_dados'" in p for p in zero_entries_dropped(found)))

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

    def test_padrao_da_conta_que_aceita_cr_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for d in found["contas"]["datasets"]:
            for f in d.get("fields") or []:
                if f["name"] == "numeroConta":
                    f["pattern"] = "^.{1,20}$"
        self.assertTrue(any("aceita" in p and "\\r" in p for p in account_patterns_off(found)))

    def test_regra_de_moeda_que_deixa_passar_usd_e_pega(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        found["titulares"]["rules"] = [r for r in found["titulares"]["rules"]
                                       if not str(r.get("id", "")).startswith("moeda-da-renda")]
        problems = currency_rules_off(found)
        self.assertIn("titulares: 'titulares.moedaRenda' = 'USD' passaria com tipoPessoa 1", problems)
        self.assertIn("titulares: 'titulares_contraparte.moedaRenda' = 'USD' passaria com tipoPessoa 1", problems)

    def test_regra_de_moeda_que_recusa_brl_e_pega(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for r in found["titulares"]["rules"]:
            if r.get("id") == "moeda-da-renda":
                r["check"]["notStartsWith"]["values"].append("B")
        self.assertIn("titulares: 'titulares.moedaRenda' = 'BRL' seria recusado", currency_rules_off(found))

    def test_regra_de_moeda_que_olha_a_figura_nao_impressa_e_pega(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for r in found["titulares"]["rules"]:
            if r.get("id") == "moeda-do-faturamento":
                r["where"] = {"field": "moedaFaturamento", "notIn": ["BRL", ""]}
        self.assertIn("titulares: 'titulares.moedaFaturamento' = 'USD' recusaria tipoPessoa 1, que não o imprime",
                      currency_rules_off(found))

    def test_moeda_sem_o_formato_iso_e_pega(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for d in found["titulares"]["datasets"]:
            for f in d.get("fields") or []:
                if f["name"] == "moedaRenda":
                    f.pop("pattern", None)
        self.assertIn("titulares: 'titulares.moedaRenda' = '$BRL' passaria fora do formato ISO", currency_rules_off(found))

    def test_campo_ascii_sem_o_pattern_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for d in found["titulares"]["datasets"]:
            for f in d.get("fields") or []:
                if d["name"] == "titulares" and f["name"] == "logradouro":
                    f.pop("pattern")
        self.assertEqual(["titulares: 'titulares.logradouro' passa pelo ascii sem pattern"],
                         ascii_fields_off(ROOT, found))

    def test_pattern_que_deixa_passar_o_grau_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for d in found["agencias"]["datasets"]:
            for f in d.get("fields") or []:
                if d["name"] == "agencias_do_caso" and f["name"] == "endereco":
                    f["pattern"] = "^.*$"
        self.assertIn("agencias: 'agencias_do_caso.endereco' aceita °’–øß🙏, que o macro não converte",
                      ascii_fields_off(ROOT, found))

    def test_ascii_num_campo_novo_sem_pattern_e_pego(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for document in ASCII_FIELDS:
                target = Path(tmp) / FAMILY / document
                target.mkdir(parents=True)
                text = (ROOT / FAMILY / document / "template.tpl").read_text(encoding="utf-8")
                if document == "contas":
                    text += "{{ ascii(c.apelido) }}"
                (target / "template.tpl").write_text(text, encoding="utf-8")
            self.assertEqual(["contas: ascii(c.apelido) escreve um campo sem o pattern ASCII"],
                             ascii_fields_off(Path(tmp), contracts(ROOT)))

    def test_e2e_sem_o_pattern_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for d in found["extrato"]["datasets"]:
            for f in d.get("fields") or []:
                if d["name"] == ENTRIES and f["name"] == "e2eEnvio":
                    f.pop("pattern")
        self.assertEqual([f"extrato: '{ENTRIES}.e2eEnvio' aceita TAB, CR ou LF"], raw_metadata_unguarded(found))

    def test_grao_so_pela_operacao_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for d in found["origem-destino"]["datasets"]:
            if d["name"] == ENTRIES:
                d["grain"] = ["operacaoId"]
        self.assertEqual([f"origem-destino: '{ENTRIES}' não ordena por {ENTRY_GRAIN}"], entry_grain_off(found))

    def test_fim_sem_o_not_before_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for p in found["extrato"]["parameters"]:
            if p["name"] == "fim":
                p.pop("notBefore")
        self.assertEqual(["extrato: o fim não declara notBefore: inicio"], reversed_period_allowed(found))

    def test_cambio_comparado_com_nao_e_pego(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / FAMILY / "titulares"
            target.mkdir(parents=True)
            text = (ROOT / FAMILY / "titulares" / "template.tpl").read_text(encoding="utf-8")
            (target / "template.tpl").write_text(
                text.replace('operaCambio == "sim"', 'operaCambio != "nao"'), encoding="utf-8")
            self.assertEqual(['titulares: a recusa do campo 28 não é condicionada a operaCambio == "sim"',
                              "titulares: uma comparação com != recusaria o operaCambio pendente (vazio)"],
                             exchange_refusal_off(Path(tmp)))

    def test_campo_obrigatorio_que_vira_opcional_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for d in found["origem-destino"]["datasets"]:
            for f in d.get("fields") or []:
                if (d["name"], f["name"]) in {("trilho_ted_enviadas", "tipoContaInformado"), (ENTRIES, "tipoOperacao")}:
                    f["required"] = False
        self.assertEqual(["origem-destino: 'lancamentos.tipoOperacao' não é required: true",
                          "origem-destino: 'trilho_ted_enviadas.tipoContaInformado' não é required: true"],
                         required_fields_off(found))

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

    def test_consulta_que_exclui_os_investigados_e_pega(self) -> None:
        found = copy.deepcopy(self.found)
        for condition in queries_of(found["contas"])[CASE_ACCOUNTS]["filters"]:
            if any(isinstance(v, dict) and v.get("parameter") == INVESTIGATED for v in condition.get("values") or []):
                condition["operator"] = "nin"
        self.assertTrue(any(f"'{CASE_ACCOUNTS}'" in p for p in unscoped_queries(found)))

    def test_consulta_que_exclui_as_contas_do_caso_e_pega(self) -> None:
        found = copy.deepcopy(self.found)
        for condition in queries_of(found["contas"])["lancamentos"]["filters"]:
            if any(isinstance(v, dict) and v.get("query") == CASE_ACCOUNTS for v in condition.get("values") or []):
                condition["operator"] = "nin"
        self.assertTrue(any("'lancamentos'" in p for p in unscoped_queries(found)))

    def test_nome_de_pais_diferente_da_tabela_e_pego(self) -> None:
        found = copy.deepcopy(self.found)
        _compute(queries_of(found["titulares"])["cadastro_contraparte"], "nome_pais")["case"]["when"]["AR"] = {
            "constant": "Argentinia"}
        self.assertTrue(any("'cadastro_contraparte'" in p and "AR" in p for p in country_names_mismatch(found)))

    def test_pais_em_minuscula_sem_traducao_e_pego(self) -> None:
        found = copy.deepcopy(self.found)
        del _compute(queries_of(found["titulares"])["cadastro_titulares"], "nome_pais")["case"]["when"]["br"]
        self.assertTrue(any("'cadastro_titulares'" in p and "'br'" in p for p in country_names_mismatch(found)))

    def test_pais_sem_traducao_que_recusa_e_pego(self) -> None:
        found = copy.deepcopy(self.found)
        _compute(queries_of(found["titulares"])["cadastro_titulares"], "nome_pais")["case"]["otherwise"] = "refuse"
        self.assertTrue(any("marca o país" in p for p in country_names_mismatch(found)))

    def test_codigo_de_uf_diferente_da_tabela_e_pego(self) -> None:
        found = copy.deepcopy(self.found)
        _compute(queries_of(found["titulares"])["cadastro_contraparte"], "codigo_uf")["case"]["when"]["SP"] = {
            "constant": "33"}
        self.assertEqual(["titulares: 'cadastro_contraparte' escreve {'constant': '33'} para a UF SP, e a tabela, "
                          "{'constant': '35'}"], country_names_mismatch(found))

    def test_uf_que_falta_numa_consulta_e_pega(self) -> None:
        found = copy.deepcopy(self.found)
        del _compute(queries_of(found["titulares"])["cadastro_titulares"], "codigo_uf")["case"]["when"]["DF"]
        self.assertEqual(["titulares: 'cadastro_titulares' traduz a UF 'DF', que a tabela do IBGE tem e a consulta não"],
                         country_names_mismatch(found))

    def test_uf_sem_traducao_que_recusa_e_pega(self) -> None:
        found = copy.deepcopy(self.found)
        _compute(queries_of(found["titulares"])["cadastro_contraparte"], "codigo_uf")["case"]["otherwise"] = "refuse"
        self.assertTrue(any("marca a UF" in p for p in country_names_mismatch(found)))

    def test_conjunto_sem_a_recusa_da_uf_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        found["titulares"]["rules"] = [r for r in found["titulares"]["rules"]
                                       if not (r["appliesTo"] == "titulares_contraparte" and r["where"].get("in"))]
        self.assertEqual(["titulares: 'titulares_contraparte' não recusa quem mora no Brasil com a UF '00'"],
                         domicile_rules_missing(found))

    def test_recusa_de_pais_que_esquece_uma_letra_e_pega(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for r in found["titulares"]["rules"]:
            if r["appliesTo"] == "titulares" and r["where"].get("field") == "nomePais" and r["where"].get("equals"):
                r["check"]["notStartsWith"]["values"].remove("z")
        self.assertEqual(["titulares: 'titulares' não recusa o país informado que a tabela não tem"],
                         domicile_rules_missing(found))

    def test_contas_sem_o_nonempty_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for d in found["contas"]["datasets"]:
            d.pop("nonEmpty", None)
        self.assertEqual(["contas: 'contas_investigadas' não é nonEmpty; sem conta nenhuma o arquivo sairia vazio"],
                         empty_case_rules_off(found))

    def test_od_sem_o_allow_empty_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        found["origem-destino"]["filing"].pop("allowEmpty")
        self.assertEqual(["origem-destino: não declara filing.allowEmpty; sem lançamento no caso o arquivo vazio "
                          "seria recusado"], empty_case_rules_off(found))

    def test_contas_com_allow_empty_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        found["contas"]["filing"]["allowEmpty"] = True
        self.assertEqual(["contas: declara filing.allowEmpty; sem conta nenhuma ele não sai (nonEmpty)"],
                         empty_case_rules_off(found))

    def test_pg_traduzido_por_interpretacao_e_pego(self) -> None:
        found = copy.deepcopy(self.found)
        _compute(queries_of(found["origem-destino"])["ted_recebidas"], "tipo_conta_pagador")["case"]["when"]["CPAY"] = {
            "constant": "6"}
        self.assertTrue(any("'ted_recebidas'" in p and "a decisão é" in p for p in ted_account_type_off(found)))

    def test_case_sobre_subcaminho_json_em_postgres_e_pego(self) -> None:
        found = copy.deepcopy(self.found)
        queries_of(found["origem-destino"])["ted_enviadas"].setdefault("compute", []).append(
            {"as": "tipo_conta_recebedor", "case": {"column": "recipient_details.accountType",
                                                    "when": {"CACC": {"constant": "1"}}, "otherwise": {"constant": "-"}}})
        self.assertEqual(["origem-destino: 'ted_enviadas' (bank_transfer) calcula sobre recipient_details.accountType, "
                          "um subcaminho JSON que o motor recusa numa fonte Postgres"], plain_computes_off(found))

    def test_tran_traduzido_por_interpretacao_e_pego(self) -> None:
        found = copy.deepcopy(self.found)
        _compute(queries_of(found["origem-destino"])["pix_lerian_recebimentos"], "tipo_conta_od")["case"]["when"]["TRAN"] = {
            "constant": "6"}
        self.assertTrue(any("'pix_lerian_recebimentos'" in p for p in pix_account_type_off(found)))

    def test_conta_de_pagamento_do_fornecedor_traduzida_e_pega(self) -> None:
        found = copy.deepcopy(self.found)
        _compute(queries_of(found["origem-destino"])["pix_jd_envios"], "tipo_conta_od")["case"]["when"]["3"] = {
            "constant": "6"}
        self.assertTrue(any("'pix_jd_envios'" in p for p in pix_account_type_off(found)))

    def test_extrato_com_nonempty_e_pego(self) -> None:
        found = copy.deepcopy(contracts(ROOT))
        for d in found["extrato"]["datasets"]:
            if d["name"] == ENTRIES:
                d["nonEmpty"] = True
        self.assertEqual([f"extrato: '{ENTRIES}' é nonEmpty; conta sem lançamento no período deixa o arquivo sem linha"],
                         empty_case_rules_off(found))


if __name__ == "__main__":
    unittest.main(verbosity=1)
