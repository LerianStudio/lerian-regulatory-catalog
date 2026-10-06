#!/usr/bin/env python3
"""Catálogo de fixtures para a suíte do validador.

Constrói, num diretório temporário, um catálogo MÍNIMO E VÁLIDO que exercita todas
as construções do formato. Cada prova de mutação parte daqui, quebra uma coisa e
espera a reprovação correspondente.

Três documentos, porque as construções são mutuamente exclusivas num só:

  doc-plano      conjunto ABERTO de linhas (o balancete): grain, consulta agregada,
                 natureza pela tabela de prefixo. É a forma do 4010/4016.
  doc-fechado    conjunto FECHADO (o 4111): rowSet vindo do catálogo, byRowClass com
                 pendência declarada, generatable: false.
  doc-hierarquia hierarquia e reconciliação (o DIMP): childOf, parentMatch,
                 refersTo, equalsSumOf, having, consulta composta, derive.

São fixtures, não documentos reais: os nomes e códigos são inventados de propósito,
para ninguém confundir com contrato curado nem copiar daqui para o catálogo.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

APIV = "reporter.lerian.io/v1alpha1"


def _meta(doc_id: str, doc: str, **extra) -> dict:
    meta = {
        "id": doc_id,
        "country": "ZZ",
        "regulator": "FIXTURE",
        "document": doc,
        "title": f"Fixture {doc}",
        "version": "1.0.0",
        "status": "draft",
        "appliesTo": {"institutionTypes": ["IP"]},
        "periodicity": "monthly",
        "sourceOfTruth": {"layoutManual": "https://example.invalid/leiaute", "schema": "schema/leiaute.txt"},
    }
    meta["sourceOfTruth"].update(extra.pop("sourceOfTruth", {}))
    meta.update(extra)
    return meta


# ---------------------------------------------------------------------------
# doc-plano — conjunto aberto (forma do 4010/4016)
# ---------------------------------------------------------------------------

PLANO_CONTRACT = {
    "apiVersion": APIV,
    "kind": "DocumentContract",
    "metadata": _meta("zz.fixture.plano", "PLANO"),
    "parameters": [
        {"name": "dataBase", "type": "month", "required": True, "allowedMonths": ["06", "12"],
         "closed": True, "description": "Competência."},
        {"name": "tipoRemessa", "type": "string", "required": True, "default": "I", "domain": ["I", "S"],
         "description": "Remessa."},
    ],
    "datasets": [
        {"name": "institution", "description": "Declarante.", "grain": "singleton",
         "fields": [{"name": "cnpj", "type": "string", "length": 14, "required": True,
                     "normalize": "alphanumeric", "checkDigit": "cnpj", "description": "CNPJ."},
                    {"name": "cnpj8", "type": "string", "length": 8, "required": True, "prefixOf": "cnpj",
                     "pattern": "^[A-Za-z0-9]{8}$", "description": "Raiz do CNPJ."}]},
        {"name": "saldos", "description": "Saldo por rubrica.", "grain": ["codigo"], "nonEmpty": True,
         "fields": [
             {"name": "codigo", "type": "string", "required": True, "pattern": "^[0-9]{10}$",
              "normalize": "digits", "description": "Rubrica."},
             {"name": "valor", "type": "decimal", "required": True,
              "format": {"scale": 2, "scaleIsExact": True, "decimalSeparator": ".", "groupSeparator": ""},
              "means": "Saldo na natureza da conta.", "description": "Saldo."},
         ]},
    ],
    "rules": [
        {"id": "sem-duplicata", "severity": "error", "appliesTo": "saldos",
         "assert": "unique(codigo)", "message": "Uma linha por rubrica."},
    ],
}

PLANO_TEMPLATE = """{# Fixture PLANO — conjunto aberto. #}
{# Define apenas posição e sintaxe. #}
<?xml version="1.0" encoding="UTF-8"?>
<documento codigoDocumento="PLANO" cnpj="{{ institution.cnpj8 }}" dataBase="{{ system.dataBase }}" tipoRemessa="{{ system.tipoRemessa }}">
  <contas>
{%- for c in saldos %}
    <conta codigoConta="{{ c.codigo }}" saldo="{{ c.valor }}" />
{%- endfor %}
  </contas>
</documento>
"""

PLANO_BINDING = {
    "apiVersion": APIV,
    "kind": "DocumentBinding",
    "contract": "zz.fixture.plano",
    "contractVersion": "1.0.0",
    "queries": [
        {"name": "declarante", "dataSource": "fonte_cadastro", "table": "organizacao"},
        {"name": "saldos_por_rubrica", "dataSource": "fonte_x", "table": "lancamento",
         "filters": [{"field": "status", "operator": "eq", "values": ["OK"]}],
         "aggregate": {
             "groupBy": ["rota"],
             "measures": [{"as": "valor", "fn": "sum", "of": "montante",
                           "sign": {"column": "lado", "debit": "-", "credit": "+"},
                           "statedIn": {"natureByPrefix": {"1": "debit", "4": "credit"}, "key": "rota"}}],
             "accumulate": {"on": "criado_em", "until": "system.dataBase"},
         }},
    ],
    "datasets": {
        "institution": {"from": {"query": "declarante"},
                        "fields": {"cnpj": {"from": "query", "column": "documento"}}},
        "saldos": {"from": {"query": "saldos_por_rubrica"},
                   "fields": {"codigo": {"from": "query", "column": "rota"},
                              "valor": {"from": "query", "column": "valor"}}},
    },
    "manualOverrides": [],
}


# ---------------------------------------------------------------------------
# doc-fechado — conjunto fechado (forma do 4111)
# ---------------------------------------------------------------------------

FECHADO_CONTRACT = {
    "apiVersion": APIV,
    "kind": "DocumentContract",
    "metadata": _meta("zz.fixture.fechado", "FECHADO", periodicity="daily",
                      sourceOfTruth={"accountSet": "contas.yaml"}),
    "parameters": [
        {"name": "dataBase", "type": "date", "required": True, "description": "Dia."},
        {"name": "tipoRemessa", "type": "string", "required": True, "default": "I", "domain": ["I", "S"],
         "description": "Remessa."},
    ],
    "datasets": [
        {"name": "institution", "description": "Declarante.", "grain": "singleton",
         "fields": [{"name": "cnpj8", "type": "string", "length": 8, "required": True,
                     "pattern": "^[A-Za-z0-9]{8}$", "description": "Raiz do CNPJ."}]},
        {"name": "linhas", "description": "Uma linha por conta do conjunto fechado.",
         "rowSet": {"from": "contas.yaml", "key": "codigo"},
         "fields": [
             {"name": "codigo", "type": "string", "required": True, "pattern": "^[0-9]{10}$",
              "normalize": "digits", "description": "Conta do conjunto."},
             {"name": "valor", "type": "decimal", "required": True,
              "format": {"scale": 2, "scaleIsExact": True, "decimalSeparator": ".", "groupSeparator": ""},
              "means": "Estoque ou fluxo, conforme a classe da conta.", "description": "Valor."},
         ]},
    ],
    "rules": [
        {"id": "conta-do-conjunto", "severity": "error", "appliesTo": "linhas.codigo",
         "assert": "existsIn(contas.yaml)", "message": "Só contas do conjunto fechado."},
    ],
}

# A coluna de identidade chama-se como o contrato declara em `rowSet.key` — aqui
# `codigo`. É a mesma exigência do motor: a linha carrega a coluna que a nomeia.
FECHADO_CONTAS = {
    "apiVersion": APIV,
    "kind": "DocumentRowSet",
    "rows": [
        {"codigo": "1100000002", "masked": "1.1.0.00.00.00-2", "measure": "stock", "description": "Estoque A"},
        {"codigo": "4193000009", "masked": "4.1.9.30.00.00-9", "measure": "stock", "description": "Estoque B"},
        {"codigo": "3097010000", "masked": "3.0.9.70.10.00-0", "measure": "flow", "description": "Fluxo A"},
    ]
}

FECHADO_TEMPLATE = """{# Fixture FECHADO — conjunto fechado de linhas. #}
<?xml version="1.0" encoding="UTF-8"?>
<documento codigoDocumento="FECHADO" cnpj="{{ institution.cnpj8 }}" dataBase="{{ system.dataBase }}" tipoRemessa="{{ system.tipoRemessa }}">
  <contas>
{%- for c in linhas %}
    <conta codigoConta="{{ c.codigo }}" saldoDia="{{ c.valor }}" />
{%- endfor %}
  </contas>
</documento>
"""

FECHADO_BINDING = {
    "apiVersion": APIV,
    "kind": "DocumentBinding",
    "contract": "zz.fixture.fechado",
    "contractVersion": "1.0.0",
    "generatable": False,
    "incompleteReason": "A conta de fluxo exige acumulação com reinício mensal, que não existe.",
    "incompleteFields": ["linhas.valor"],
    "queries": [
        {"name": "estoque", "dataSource": "fonte_x", "table": "lancamento",
         "aggregate": {"groupBy": ["rota"],
                       "measures": [{"as": "valor", "fn": "sum", "of": "montante"}],
                       "accumulate": {"on": "criado_em", "until": "system.dataBase"}}},
    ],
    "datasets": {
        "institution": {"fields": {"cnpj8": {"from": "constant", "value": "12345678"}}},
        "linhas": {
            "from": {"query": "estoque"},
            "rowKey": {"codigo": "rota"},
            "fields": {
                "codigo": {"from": "rowSet", "column": "codigo"},
                "valor": {"byRowClass": [
                    {"when": {"rowSet": "measure", "equals": "stock"}, "from": "query", "column": "valor"},
                    {"when": {"rowSet": "measure", "equals": "flow"}, "from": "manual",
                     "pendingReason": "acumulação com reinício mensal ainda não existe"},
                ]},
            },
        },
    },
    "manualOverrides": [],
}


# ---------------------------------------------------------------------------
# doc-hierarquia — hierarquia e reconciliação (forma do DIMP)
# ---------------------------------------------------------------------------

HIER_CONTRACT = {
    "apiVersion": APIV,
    "kind": "DocumentContract",
    "metadata": _meta("zz.fixture.hierarquia", "HIER"),
    "parameters": [{"name": "dataBase", "type": "month", "required": True, "description": "Competência."}],
    "datasets": [
        {"name": "titulares", "description": "Titulares.", "grain": ["codigo"],
         "fields": [
             {"name": "codigo", "type": "string", "required": True, "description": "Código do titular."},
             {"name": "tipo", "type": "string", "required": True, "domain": ["PF", "PJ"], "description": "Tipo."},
             {"name": "cnpj", "type": "string", "length": 14,
              "requiredWhen": {"field": "tipo", "equals": "PJ"},
              "forbiddenWhen": {"field": "tipo", "equals": "PF"}},
         ]},
        {"name": "resumos", "description": "Resumo por titular.", "grain": ["codTitular"],
         "fields": [
             {"name": "codTitular", "type": "string", "required": True,
              "refersTo": {"dataset": "titulares", "field": "codigo"}},
             {"name": "total", "type": "decimal", "required": True,
              "format": {"scale": 2, "scaleIsExact": True, "decimalSeparator": ".", "groupSeparator": ""},
              "equalsSumOf": {"dataset": "detalhes", "field": "valor"}},
             # `via`: a condição lê um campo do conjunto REFERENCIADO por codTitular,
             # e não do próprio. Está aqui porque nenhuma fixture o usava — e a
             # varredura só alcança construção que alguma fixture declare, então o
             # ramo do `via` no validador nunca era executado por ela.
             {"name": "inscricao", "type": "string",
              "requiredWhen": {"via": "codTitular", "field": "tipo", "equals": "PJ"},
              "description": "Inscrição, exigida quando o titular referido é PJ."},
         ]},
        {"name": "detalhes", "description": "Detalhe do resumo.",
         "childOf": {"dataset": "resumos"}, "grain": ["id"],
         "fields": [
             {"name": "id", "type": "string", "required": True, "description": "Id do detalhe."},
             {"name": "valor", "type": "decimal", "required": True,
              "format": {"scale": 2, "scaleIsExact": True, "decimalSeparator": ".", "groupSeparator": ""},
              "description": "Valor."},
         ]},
    ],
    "rules": [
        {"id": "resumo-unico", "severity": "error", "appliesTo": "resumos",
         "assert": "unique(codTitular)", "message": "Um resumo por titular."},
    ],
}

HIER_TEMPLATE = """{# Fixture HIER — hierarquia de conjuntos. #}
{# As filhas são alcançadas como lista aninhada na linha do pai. #}
|H|{{ system.dataBase }}|
{%- for t in titulares %}
|T|{{ t.codigo }}|{{ t.tipo }}|{{ t.cnpj }}|
{%- endfor %}
{%- for r in resumos %}
|R|{{ r.codTitular }}|{{ r.total }}|{{ r.inscricao }}|
{%- for d in r.detalhes %}
|D|{{ d.id }}|{{ d.valor }}|
{%- endfor %}
{%- endfor %}
"""

HIER_BINDING = {
    "apiVersion": APIV,
    "kind": "DocumentBinding",
    "contract": "zz.fixture.hierarquia",
    "contractVersion": "1.0.0",
    "queries": [
        {"name": "base_titulares", "dataSource": "crm", "table": "holders",
         "join": [{"table": "aliases", "match": {"holder_id": "_id"}}]},
        {"name": "movimento", "dataSource": "fonte_x", "table": "lancamento",
         "join": [{"query": "base_titulares", "match": {"conta": "conta"}}],
         "derive": [{"as": "dia", "from": "criado_em", "apply": "date"}]},
        {"name": "por_titular", "from": "movimento",
         "aggregate": {"groupBy": ["titular", "tipo", "inscricao"],
                       "measures": [{"as": "total", "fn": "sum", "of": "montante"}]},
         "having": [{"anyOf": [
             {"field": "tipo", "operator": "eq", "values": ["PJ"]},
             {"field": "total", "operator": "gte", "values": ["100.00"]},
         ]}]},
        {"name": "detalhado", "from": "movimento",
         "aggregate": {"groupBy": ["titular", "ident", "dia"],
                       "measures": [{"as": "valor", "fn": "sum", "of": "montante"}]}},
    ],
    "datasets": {
        "titulares": {"from": {"query": "base_titulares"},
                      "fields": {"codigo": {"from": "query", "column": "_id"},
                                 "tipo": {"from": "query", "column": "tipo_pessoa"},
                                 "cnpj": {"from": "query", "column": "documento"}}},
        "resumos": {"from": {"query": "por_titular"},
                    "fields": {"codTitular": {"from": "query", "column": "titular"},
                               "total": {"from": "query", "column": "total"},
                               "inscricao": {"from": "query", "column": "inscricao"}}},
        "detalhes": {"from": {"query": "detalhado"},
                     "parentMatch": {"codTitular": "titular"},
                     "fields": {"id": {"from": "query", "column": "ident"},
                                "valor": {"from": "query", "column": "valor"}}},
    },
    "manualOverrides": [],
}


# ---------------------------------------------------------------------------
# doc-janelas — conjunto fechado cujas classes leem CONSULTAS DIFERENTES
#
# A forma que o 4111 real tem: a janela de acumulação pertence à consulta, então
# duas janelas são duas consultas, e cada campo diz de qual delas lê.
# ---------------------------------------------------------------------------

JANELAS_CONTRACT = {
    "apiVersion": APIV,
    "kind": "DocumentContract",
    "metadata": _meta("zz.fixture.janelas", "JANELAS", periodicity="daily",
                      sourceOfTruth={"accountSet": "contas.yaml"}),
    "parameters": [
        {"name": "dataBase", "type": "date", "required": True, "description": "Dia."},
    ],
    "datasets": [
        {"name": "linhas", "description": "Uma linha por conta do conjunto fechado.",
         "rowSet": {"from": "contas.yaml", "key": "codigo"},
         "fields": [
             {"name": "codigo", "type": "string", "required": True, "pattern": "^[0-9]{10}$",
              "normalize": "digits", "description": "Conta do conjunto."},
             {"name": "valor", "type": "decimal", "required": True,
              "format": {"scale": 2, "scaleIsExact": True, "decimalSeparator": ".", "groupSeparator": ""},
              "means": "Estoque ou fluxo, conforme a classe da conta.", "description": "Valor."},
         ]},
    ],
}

JANELAS_CONTAS = {
    "apiVersion": APIV,
    "kind": "DocumentRowSet",
    "rows": [
        {"codigo": "1100000002", "masked": "1.1.0.00.00.00-2", "measure": "stock", "description": "Estoque A"},
        {"codigo": "3097010000", "masked": "3.0.9.70.10.00-0", "measure": "flow", "description": "Fluxo A"},
    ]
}

JANELAS_TEMPLATE = """{# Fixture JANELAS — duas janelas sobre o mesmo conjunto. #}
<?xml version="1.0" encoding="UTF-8"?>
<documento codigoDocumento="JANELAS" dataBase="{{ system.dataBase }}">
{%- for c in linhas %}
  <conta codigoConta="{{ c.codigo }}" valor="{{ c.valor }}" />
{%- endfor %}
</documento>
"""

JANELAS_BINDING = {
    "apiVersion": APIV,
    "kind": "DocumentBinding",
    "contract": "zz.fixture.janelas",
    "contractVersion": "1.0.0",
    "queries": [
        {"name": "estoque", "dataSource": "fonte_x", "table": "lancamento",
         "aggregate": {"groupBy": ["rota"],
                       "measures": [{"as": "saldo", "fn": "sum", "of": "montante"}],
                       "accumulate": {"on": "criado_em", "until": "system.dataBase",
                                      "from": "opening"}}},
        {"name": "volume", "dataSource": "fonte_x", "table": "lancamento",
         "aggregate": {"groupBy": ["rota"],
                       "measures": [{"as": "volumeMes", "fn": "sum", "of": "montante"}],
                       "accumulate": {"on": "criado_em", "until": "system.dataBase",
                                      "from": "month"}}},
    ],
    "datasets": {
        "linhas": {
            "from": {"query": "estoque"},
            "rowKey": {"codigo": "rota"},
            "fields": {
                "codigo": {"from": "rowSet", "column": "codigo"},
                # A classe de fluxo lê a OUTRA consulta, porque é a janela que difere.
                "valor": {"byRowClass": [
                    {"when": {"rowSet": "measure", "equals": "stock"}, "from": "query", "column": "saldo"},
                    {"when": {"rowSet": "measure", "equals": "flow"}, "from": "query",
                     "query": "volume", "column": "volumeMes"},
                ]},
            },
        },
    },
    "manualOverrides": [],
}


DOCS = {
    "zz/fixture/plano": (PLANO_CONTRACT, PLANO_TEMPLATE, PLANO_BINDING, None),
    "zz/fixture/fechado": (FECHADO_CONTRACT, FECHADO_TEMPLATE, FECHADO_BINDING, FECHADO_CONTAS),
    "zz/fixture/hierarquia": (HIER_CONTRACT, HIER_TEMPLATE, HIER_BINDING, None),
    "zz/fixture/janelas": (JANELAS_CONTRACT, JANELAS_TEMPLATE, JANELAS_BINDING, JANELAS_CONTAS),
}


def _index_entry(contract: dict, path: str) -> dict:
    m = contract["metadata"]
    return {
        "id": m["id"], "path": path, "country": m["country"], "regulator": m["regulator"],
        "document": m["document"], "title": m["title"], "version": m["version"],
        "status": m["status"], "periodicity": m["periodicity"], "appliesTo": m["appliesTo"],
        "summary": "Fixture da suíte do validador.",
    }


def bundle() -> dict:
    """Os dados das fixtures, em estrutura — não em texto.

    As mutações da suíte operam AQUI, e não sobre o YAML serializado: uma prova
    escrita contra a indentação do dump quebra quando o dump muda de forma, e uma
    suíte que quebra por formatação é uma suíte que se aprende a ignorar.
    """
    return {
        path: {
            "contract": deepcopy(contract),
            "template": template,
            "binding": deepcopy(binding),
            "contas": deepcopy(contas),
        }
        for path, (contract, template, binding, contas) in DOCS.items()
    }


def write(root: Path, data: dict) -> None:
    """Serializa um bundle (possivelmente mutado) como catálogo em `root`."""
    documents = []

    for path, parts in data.items():
        contract = parts["contract"]
        template = parts["template"]
        binding = parts["binding"]
        contas = parts["contas"]
        doc_dir = root / path
        (doc_dir / "schema").mkdir(parents=True, exist_ok=True)

        (doc_dir / "schema" / "leiaute.txt").write_text(
            "Material de curadoria de fixture — não é leiaute real.\n", encoding="utf-8")
        (doc_dir / "contract.yaml").write_text(
            yaml.safe_dump(contract, sort_keys=False, allow_unicode=True), encoding="utf-8")
        (doc_dir / "template.tpl").write_text(template, encoding="utf-8")
        (doc_dir / "binding.example.yaml").write_text(
            yaml.safe_dump(binding, sort_keys=False, allow_unicode=True), encoding="utf-8")

        if contas is not None:
            (doc_dir / "contas.yaml").write_text(
                yaml.safe_dump(contas, sort_keys=False, allow_unicode=True), encoding="utf-8")

        documents.append(parts.get("indexEntry") or _index_entry(contract, path))

    (root / "catalog.yaml").write_text(
        yaml.safe_dump({"apiVersion": APIV, "kind": "Catalog", "documents": documents},
                       sort_keys=False, allow_unicode=True),
        encoding="utf-8")


def build(root: Path) -> None:
    """Escreve o catálogo de fixtures válido — atalho para write(root, bundle())."""
    write(root, bundle())
