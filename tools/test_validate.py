#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""Suíte do validador do catálogo — as provas de mutação, versionadas.

## Por que existe

Cada conferência de `validate.py` nasceu de um erro real que produziria arquivo
regulatório errado com aparência de certo, e cada uma foi provada quebrando o
catálogo de propósito e vendo a reprovação sair. Mas essas provas eram comandos
digitados à mão, que não sobrevivem à sessão.

Uma conferência sem prova versionada é uma conferência que amanhã pode estar frouxa
sem ninguém notar — e isso já aconteceu quatro vezes seguidas aqui: eu acrescentava
vocabulário ao validador (`rowSet`, `byRowClass`, `manualOverrides`) e esquecia a
precondição que o torna significativo. Duas vezes a frouxidão estava no caminho
gêmeo do que eu tinha acabado de corrigir.

O validador é a rede que impede um contrato regulatório errado de entrar. Ele merece
o rigor que impõe.

## Como funciona

Cada caso é uma MUTAÇÃO: parte do catálogo de fixtures válido (`fixtures.py`), quebra
exatamente uma coisa e exige que o validador reprove NOMEANDO o problema. Uma
mutação que deixa de reprovar é uma conferência que ficou frouxa.

As mutações operam sobre a ESTRUTURA das fixtures, não sobre o YAML serializado:
prova escrita contra indentação de dump quebra quando o dump muda de forma, e suíte
que quebra por formatação é suíte que se aprende a ignorar.

Só biblioteca padrão — o repositório carrega conteúdo regulatório e depende apenas de
pyyaml:

    python3 tools/test_validate.py
    python3 -m unittest discover -s tools -p 'test_*.py'
"""

from __future__ import annotations

import ast
import contextlib
import copy
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable, Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

import fixtures  # noqa: E402
import validate  # noqa: E402

TOOLS = Path(__file__).resolve().parent
VALIDATE = TOOLS / "validate.py"

PLANO = "zz/fixture/plano"
FECHADO = "zz/fixture/fechado"
HIER = "zz/fixture/hierarquia"
JANELAS = "zz/fixture/janelas"


# ---------------------------------------------------------------------------
# Acessores — deixam a mutação legível como a frase do defeito que ela encena.
# ---------------------------------------------------------------------------

def dataset(contract: dict, name: str) -> dict:
    return next(d for d in contract["datasets"] if d["name"] == name)


def field(contract: dict, ds_name: str, f_name: str) -> dict:
    return next(f for f in dataset(contract, ds_name)["fields"] if f["name"] == f_name)


def query(binding: dict, name: str) -> dict:
    return next(q for q in binding["queries"] if q["name"] == name)


def parameter(contract: dict, name: str) -> dict:
    return next(p for p in contract["parameters"] if p["name"] == name)


def rule(contract: dict, rule_id: str) -> dict:
    return next(r for r in contract["rules"] if r["id"] == rule_id)


class Mutation:
    """Uma quebra deliberada e a reprovação que ela deve provocar.

    `expect` é um fragmento da mensagem, porque a asserção é sobre o QUE a
    ferramenta diz: uma mensagem que não nomeia o problema não ajuda quem escreveu o
    contrato, e a conferência existe para ajudar.
    """

    def __init__(
        self,
        ident: str,
        why: str,
        apply: Callable[[dict], object],
        expect: str,
    ) -> None:
        self.ident = ident
        self.why = why
        self.apply = apply
        self.expect = expect

    def __str__(self) -> str:
        return f"{self.ident}: {self.why}"


def _mutate_template(bundle: dict, doc: str, old: str, new: str) -> None:
    """Template é texto, então aqui a substituição textual é a forma natural."""
    text = bundle[doc]["template"]
    assert old in text, f"template de {doc} não contém {old!r}"
    bundle[doc]["template"] = text.replace(old, new, 1)


MUTATIONS: list[Mutation] = [
    # ---------------------------------------------------------------- template
    Mutation(
        "template-campo-inexistente",
        "template posiciona campo que o contrato não declara",
        lambda b: _mutate_template(b, PLANO, "{{ c.codigo }}", "{{ c.naoDeclarado }}"),
        "que o contrato não declara",
    ),
    Mutation(
        "template-formatacao-duplicada",
        "formatação reaparece no template e pode divergir do contrato sem árbitro",
        lambda b: _mutate_template(b, PLANO, "{{ c.valor }}", "{{ c.valor|decimal:2 }}"),
        "Formato e sinal são propriedades do campo",
    ),
    Mutation(
        "template-comentario-multilinha",
        "pongo2 recusa salto de linha em {# #}: o template fica imparseável",
        lambda b: _mutate_template(
            b, PLANO, "{# Define apenas posição e sintaxe. #}",
            "{# Define apenas\n   posição e sintaxe. #}"),
        "comentário multi-linha",
    ),
    Mutation(
        "template-comentario-desbalanceado",
        "abertura sem fechamento leva o resto do arquivo embora em silêncio",
        lambda b: _mutate_template(
            b, PLANO, "{# Define apenas posição e sintaxe. #}", "{# Define apenas posição"),
        "desbalanceados",
    ),
    Mutation(
        "loop-aninhado-pai-errado",
        "filha alcançada pelo pai errado é seção que o render nunca popula",
        lambda b: _mutate_template(b, HIER, "for d in r.detalhes", "for d in t.detalhes"),
        "não resolve para nenhum conjunto",
    ),

    # ------------------------------------------------- separação de camadas
    Mutation(
        "contrato-com-agregacao",
        "regra de extração no contrato congela a forma da origem de UM cliente",
        lambda b: dataset(b[PLANO]["contract"], "saldos").update(
            {"aggregation": {"groupBy": ["rota"]}}),
        "pertence ao binding",
    ),
    Mutation(
        "contrato-com-datasource",
        "nome de fonte no contrato é dado do cliente vazando para a camada errada",
        lambda b: dataset(b[PLANO]["contract"], "saldos").update({"dataSource": "fonte_x"}),
        "pertence ao binding",
    ),
    Mutation(
        "contrato-com-coluna",
        "coluna no contrato é acoplamento ao esquema de um cliente",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update({"column": "rota"}),
        "pertence ao binding",
    ),

    # ------------------------------------------------------ índice x contrato
    Mutation(
        "indice-divergente",
        "índice anuncia versão diferente da do contrato",
        # Fixa a entrada do índice ANTES de mudar o contrato: nas fixtures o índice é
        # derivado do contrato, então sem fixar ele acompanharia a mudança e nada
        # divergiria — a mutação testaria o nada.
        lambda b: (b[PLANO].__setitem__("indexEntry", fixtures._index_entry(
                       b[PLANO]["contract"], PLANO)),
                   b[PLANO]["contract"]["metadata"].update({"version": "9.9.9"})),
        "diverge do contrato",
    ),

    # ---------------------------------------------------------------- regras
    Mutation(
        "regra-para-conjunto-inexistente",
        "regra apontando para conjunto que não existe nunca é aplicada",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update(
            {"appliesTo": "conjuntoFantasma"}),
        "que não é um conjunto do contrato",
    ),
    Mutation(
        "regra-duplicada",
        "duas regras com o mesmo id: uma silencia a outra",
        lambda b: b[PLANO]["contract"]["rules"].append(
            dict(rule(b[PLANO]["contract"], "sem-duplicata"))),
        "duplicada",
    ),

    # ------------------------------------- estrutura: hierarquia e referência
    Mutation(
        "childof-pai-inexistente",
        "conjunto filho de pai que não existe nunca é populado",
        lambda b: dataset(b[HIER]["contract"], "detalhes")["childOf"].update(
            {"dataset": "paiFantasma"}),
        "que não existe",
    ),
    Mutation(
        "refersto-campo-inexistente",
        "integridade referencial apontando para campo inexistente não confere nada",
        lambda b: field(b[HIER]["contract"], "resumos", "codTitular")["refersTo"].update(
            {"field": "campoErrado"}),
        "campo que não existe",
    ),
    Mutation(
        "equalssumof-nao-filho",
        "somar um conjunto que não é filho reconcilia coisa nenhuma",
        lambda b: field(b[HIER]["contract"], "resumos", "total")["equalsSumOf"].update(
            {"dataset": "titulares", "field": "codigo"}),
        "não é childOf",
    ),
    Mutation(
        "requiredwhen-campo-fantasma",
        "condicional sobre campo inexistente nunca dispara: o campo vira opcional de fato",
        lambda b: field(b[HIER]["contract"], "titulares", "cnpj")["requiredWhen"].update(
            {"field": "campoFantasma"}),
        "campo que este conjunto não declara",
    ),

    # -------------------------------------------- binding: origem dos campos
    Mutation(
        "binding-campo-sem-origem",
        "campo obrigatório sem origem faria toda geração falhar",
        lambda b: b[PLANO]["binding"]["datasets"]["saldos"]["fields"].pop("valor"),
        "obrigatório incondicional",
    ),
    Mutation(
        "binding-origem-invalida",
        "origem fora do vocabulário é campo que o motor não sabe resolver",
        lambda b: b[FECHADO]["binding"]["datasets"]["institution"]["fields"]["cnpj8"].update(
            {"from": "magica"}),
        "use query, constant, parameter, manual, rowSet ou byRowClass",
    ),
    Mutation(
        "binding-origem-instituicao-removida",
        "a origem `institution` saiu do motor: a raiz do CNPJ é um campo derivado do contrato",
        lambda b: b[FECHADO]["binding"]["datasets"]["institution"]["fields"]["cnpj8"].update(
            {"from": "institution", "institution": "cnpj8"}),
        "resolve por 'institution'",
    ),
    Mutation(
        "binding-consulta-inexistente",
        "conjunto vindo de consulta que não existe sai vazio",
        lambda b: b[PLANO]["binding"]["datasets"]["saldos"]["from"].update(
            {"query": "consultaFantasma"}),
        "que não está declarada em queries",
    ),

    # ------------------------------------------------------ binding: consultas
    Mutation(
        "consulta-composta-inexistente",
        "compor sobre consulta que não existe falha só na geração",
        lambda b: query(b[HIER]["binding"], "por_titular").update({"from": "consultaFantasma"}),
        "compõe sobre",
    ),
    Mutation(
        "consulta-sem-origem",
        "consulta sem dataSource nem from não extrai de lugar nenhum",
        lambda b: query(b[HIER]["binding"], "base_titulares").pop("dataSource"),
        "não tem nem dataSource nem from",
    ),
    Mutation(
        "join-chave-on-em-yaml",
        "YAML 1.1 lê `on` como booleano: a cláusula de join sumiria no parse",
        lambda b: query(b[HIER]["binding"], "base_titulares")["join"][0].update(
            {"on": query(b[HIER]["binding"], "base_titulares")["join"][0].pop("match")}),
        "que YAML 1.1 lê como booleano",
    ),
    Mutation(
        "join-sem-clausula",
        "join sem chave de correspondência não junta nada",
        lambda b: query(b[HIER]["binding"], "base_titulares")["join"][0].pop("match"),
        "sem cláusula match",
    ),
    Mutation(
        "consulta-sem-nome",
        "consulta sem nome é inalcançável por from, join ou conjunto",
        lambda b: query(b[HIER]["binding"], "base_titulares").pop("name"),
        "não declara name",
    ),
    Mutation(
        "consulta-nome-duplicado",
        "duas consultas com o mesmo nome tornam ambíguo o que uma referência resolve",
        lambda b: b[HIER]["binding"]["queries"].append(
            dict(query(b[HIER]["binding"], "movimento"))),
        "declarada duas vezes",
    ),
    Mutation(
        "ciclo-em-from",
        "cadeia circular de consultas não tem conjunto de colunas",
        lambda b: query(b[HIER]["binding"], "movimento").update({"from": "por_titular"}),
        "ciclo por `from`",
    ),

    # ----------------------------------------------------- binding: hierarquia
    Mutation(
        "childof-sem-parentmatch",
        "filha sem chave de aninhamento sai sob a linha errada do pai",
        lambda b: b[HIER]["binding"]["datasets"]["detalhes"].pop("parentMatch"),
        "não declara parentMatch",
    ),
    Mutation(
        "parentmatch-campo-inexistente-no-pai",
        "aninhar por campo que o pai não declara não aninha",
        lambda b: b[HIER]["binding"]["datasets"]["detalhes"].update(
            {"parentMatch": {"campoFantasma": "titular"}}),
        "que o conjunto pai",
    ),

    # --------------------------------- binding: sobrevivência de coluna
    Mutation(
        "having-coluna-descartada",
        "having sobre coluna que o groupBy descartou deixa o filtro sem discriminador",
        lambda b: query(b[HIER]["binding"], "por_titular")["aggregate"].update(
            {"groupBy": ["titular"]}),
        "que a própria consulta não entrega",
    ),
    Mutation(
        "having-field-malformado",
        "field que não é nome de coluna deve reprovar, não estourar a ferramenta",
        lambda b: query(b[HIER]["binding"], "por_titular")["having"][0]["anyOf"][0].update(
            {"field": ["tipo"]}),
        "não é nome de coluna",
    ),
    Mutation(
        "conjunto-coluna-nao-entregue",
        "mapear coluna que a consulta não entrega deixa a célula vazia",
        lambda b: b[HIER]["binding"]["datasets"]["resumos"]["fields"]["total"].update(
            {"column": "colunaSumida"}),
        "não entrega",
    ),
    Mutation(
        "parentmatch-coluna-nao-entregue",
        "aninhar por coluna que a consulta não entrega não aninha",
        lambda b: b[HIER]["binding"]["datasets"]["detalhes"].update(
            {"parentMatch": {"codTitular": "colunaSumida"}}),
        "não entrega",
    ),

    # ------------------------------------------------ conjunto fechado (rowSet)
    Mutation(
        "conta-fora-do-formato",
        "código do conjunto fora do formato do contrato é a deriva 8-vs-10 dígitos",
        lambda b: b[FECHADO]["contas"]["rows"][0].update({"codigo": "11000002"}),
        "não bate com o pattern",
    ),
    Mutation(
        "code-diverge-do-masked",
        "código transcrito à mão divergindo da forma oficial — aconteceu de verdade",
        lambda b: b[FECHADO]["contas"]["rows"][2].update({"codigo": "3097010009"}),
        "transcrição do código diverge",
    ),
    Mutation(
        "conta-sem-masked",
        "sem a forma oficial, o código não tem contra o que ser conferido",
        lambda b: b[FECHADO]["contas"]["rows"][0].pop("masked"),
        "não tem `masked`",
    ),
    Mutation(
        "conta-duplicada",
        "conta duplicada no conjunto emite a mesma linha duas vezes",
        lambda b: b[FECHADO]["contas"]["rows"].append(
            dict(b[FECHADO]["contas"]["rows"][0])),
        "duplicada",
    ),
    Mutation(
        "accountset-inexistente",
        "conjunto anunciado que não existe faz o documento sair vazio em silêncio",
        lambda b: b[FECHADO]["contract"]["metadata"]["sourceOfTruth"].update(
            {"accountSet": "contasFantasma.yaml"}),
        "que não existe",
    ),
    Mutation(
        "rowset-sem-accountset",
        "sem o conjunto anunciado, a conferência de consistência se apaga",
        lambda b: b[FECHADO]["contract"]["metadata"]["sourceOfTruth"].pop("accountSet"),
        "não declara metadata.sourceOfTruth.accountSet",
    ),
    Mutation(
        "accountset-diferente-do-rowset",
        "anunciar um conjunto e usar outro passa em cada conferência isolada",
        lambda b: dataset(b[FECHADO]["contract"], "linhas")["rowSet"].update(
            {"from": "outro.yaml"}),
        "têm de ser o mesmo arquivo",
    ),
    Mutation(
        "rows-nao-e-lista",
        "forma malformada deve reprovar, não estourar a ferramenta",
        lambda b: b[FECHADO].__setitem__("contas", {"kind": "DocumentRowSet", "rows": "naoEhLista"}),
        "não tem uma lista `rows`",
    ),
    Mutation(
        "conta-nao-e-mapa",
        "linha do conjunto que não é mapa deve reprovar, não estourar",
        lambda b: b[FECHADO]["contas"]["rows"].append(["1100000002"]),
        "que não é mapa",
    ),
    # ------------------------------------------------ duas janelas (fixture JANELAS)
    Mutation(
        "acumulacao-removida",
        "acumular saiu do motor: o período é um filtro na data-base",
        lambda b: b[JANELAS]["binding"]["queries"][0]["aggregate"].update(
            {"accumulate": {"on": "criado_em", "until": "system.dataBase"}}),
        "usa `accumulate`, que o motor não tem mais",
    ),
    Mutation(
        "sinal-removido",
        "o sinal da medida saiu do motor: é uma coluna calculada",
        lambda b: b[JANELAS]["binding"]["queries"][0]["aggregate"]["measures"][0].update(
            {"sign": {"column": "lado", "debit": "-", "credit": "+"}}),
        "usa `sign`, que o motor não tem mais",
    ),
    Mutation(
        "natureza-na-medida-removida",
        "a natureza saiu do binding: é regra do contrato",
        lambda b: b[JANELAS]["binding"]["queries"][0]["aggregate"]["measures"][0].update(
            {"statedIn": {"key": "rota"}}),
        "usa `statedIn`, que o motor não tem mais",
    ),
    Mutation(
        "fim-do-periodo-com-lte",
        "o fim do período é o primeiro instante depois dele: com lte, o período seguinte entraria",
        lambda b: b[JANELAS]["binding"]["queries"][0]["filters"][0].update({"operator": "lte"}),
        "use 'lt'",
    ),
    Mutation(
        "ponta-do-periodo-inexistente",
        "um período tem início e fim",
        lambda b: b[JANELAS]["binding"]["queries"][0]["filters"][0]["values"][0].update({"at": "meio"}),
        "um período tem start e end",
    ),
    Mutation(
        "ponta-do-periodo-que-nao-e-texto",
        "uma ponta escrita como lista reprova, nunca derruba a ferramenta",
        lambda b: b[JANELAS]["binding"]["queries"][0]["filters"][0]["values"][0].update({"at": ["end"]}),
        "um período tem start e end",
    ),
    Mutation(
        "periodo-sem-ponta",
        "um período descrito sem dizer qual ponta é lida não compara com nada",
        lambda b: b[JANELAS]["binding"]["queries"][0]["filters"][0]["values"][0].pop("at"),
        "sem dizer a ponta",
    ),
    Mutation(
        "parametro-e-literal",
        "um parâmetro ao lado de valores escritos não diz como os dois se combinam",
        lambda b: b[JANELAS]["binding"]["queries"][0]["filters"][0]["values"].append("2026-01-01"),
        "lê um parâmetro e outros valores",
    ),
    Mutation(
        "coluna-calculada-sem-otherwise",
        "um valor não listado precisa de uma decisão escrita, nunca de um NULL que some da soma",
        lambda b: query(b[PLANO]["binding"], "saldos_por_rubrica")["compute"][0]["case"].pop("otherwise"),
        "não tem otherwise",
    ),
    Mutation(
        "coluna-calculada-sem-nome-em-texto",
        "o nome de uma coluna calculada escrito como lista reprova, nunca derruba a ferramenta",
        lambda b: query(b[PLANO]["binding"], "saldos_por_rubrica")["compute"][0].update({"as": ["valor_no_razao"]}),
        "as é o nome da coluna",
    ),
    Mutation(
        "coluna-calculada-sem-caso",
        "sem caso nenhum, toda linha cai no otherwise",
        lambda b: query(b[PLANO]["binding"], "saldos_por_rubrica")["compute"][0]["case"].update({"when": {}}),
        "não lista caso nenhum",
    ),
    Mutation(
        "coluna-calculada-resposta-dupla",
        "uma resposta é uma coluna, a coluna negada ou uma constante — uma delas",
        lambda b: query(b[PLANO]["binding"], "saldos_por_rubrica")["compute"][0]["case"]["when"].update(
            {"+": {"column": "montante", "constant": "0"}}),
        "responde com exatamente um de column, negate ou constant",
    ),
    Mutation(
        "campo-le-consulta-inexistente",
        "campo que nomeia uma consulta não declarada lê de lugar nenhum",
        lambda b: b[JANELAS]["binding"]["datasets"]["linhas"]["fields"]["valor"]["byRowClass"][1]
        .update({"query": "naoExiste"}),
        "não está declarada em queries",
    ),
    Mutation(
        "campo-le-coluna-que-a-consulta-nomeada-nao-entrega",
        "a origem é conferida contra a consulta QUE ELA LÊ, não contra a do conjunto",
        lambda b: b[JANELAS]["binding"]["datasets"]["linhas"]["fields"]["valor"]["byRowClass"][1]
        .update({"column": "saldo"}),
        "que a consulta 'volume' não entrega",
    ),
    Mutation(
        "campo-sem-consulta-nomeada-le-coluna-da-outra",
        "sem nomear consulta, a origem lê a do CONJUNTO — e a coluna da outra não vale",
        lambda b: b[JANELAS]["binding"]["datasets"]["linhas"]["fields"]["valor"]["byRowClass"][0]
        .update({"column": "volumeMes"}),
        "que a consulta 'estoque' não entrega",
    ),

    Mutation(
        "conjunto-sem-marcador",
        "arquivo curado sem `kind` pode ser um contrato lido como conjunto de linhas",
        lambda b: b[FECHADO]["contas"].pop("kind"),
        "se anuncia como",
    ),
    Mutation(
        "conjunto-com-marcador-estrangeiro",
        "um conjunto que se diz outra coisa publicaria o que seu primeiro mapa tiver",
        lambda b: b[FECHADO]["contas"].__setitem__("kind", "DocumentContract"),
        "se anuncia como",
    ),
    Mutation(
        "linha-sem-coluna-de-identidade",
        "linha sem a coluna que o contrato nomeia em rowSet.key não é identificável",
        lambda b: b[FECHADO]["contas"]["rows"][0].pop("codigo"),
        "é a coluna que identifica",
    ),
    Mutation(
        "rowset-sem-key",
        "sem `key` declarada, nada diz qual coluna identifica a linha",
        lambda b: dataset(b[FECHADO]["contract"], "linhas")["rowSet"].pop("key"),
        "não declara `key`",
    ),
    Mutation(
        "chave-do-conjunto-nao-e-campo-do-documento",
        "chave com erro de digitação passa se as linhas a carregarem, e o pattern do "
        "campo deixa de ser conferido junto",
        lambda b: dataset(b[FECHADO]["contract"], "linhas")["rowSet"].update(
            {"key": "codigoErrado"}),
        "não é campo declarado do conjunto",
    ),
    Mutation(
        "chave-da-linha-casa-coluna-inexistente",
        "rowKey apontando coluna que a consulta não entrega não casa linha nenhuma",
        lambda b: b[JANELAS]["binding"]["datasets"]["linhas"].__setitem__(
            "rowKey", {"codigo": "colunaInexistente"}),
        "que a consulta 'estoque' não entrega",
    ),
    Mutation(
        "agregacao-que-nao-e-mapa",
        "forma malformada deve reprovar, não estourar em .get('accumulate')",
        lambda b: b[JANELAS]["binding"]["queries"][0].__setitem__("aggregate", "soma"),
        "não é um mapa",
    ),
    Mutation(
        "consulta-nomeada-que-nao-e-nome",
        "uma lista no lugar do nome da consulta estourava em `named not in queries`",
        lambda b: b[JANELAS]["binding"]["datasets"]["linhas"]["fields"]["valor"]["byRowClass"][1]
        .__setitem__("query", ["volume"]),
        "nomeia uma consulta que não é um nome",
    ),
    Mutation(
        "chave-da-linha-que-nao-e-mapa",
        "rowKey malformado estourava em .values() em vez de reprovar",
        lambda b: b[JANELAS]["binding"]["datasets"]["linhas"].__setitem__("rowKey", ["codigo"]),
        "o `rowKey` de 'linhas' não é um mapa",
    ),
    Mutation(
        "rowset-sem-declaracao-no-contrato",
        "campo from rowSet num conjunto sem rowSet aponta para linhas inexistentes",
        lambda b: dataset(b[FECHADO]["contract"], "linhas").pop("rowSet"),
        "não declara rowSet no conjunto",
    ),

    # ------------------------------- pendência manual: o bloqueio executável
    Mutation(
        "manual-pendente-sem-declarar-incompletude",
        "campo obrigatório manual sem valor geraria arquivo sem dado obrigatório",
        lambda b: b[FECHADO]["binding"].update({"generatable": True}),
        "NÃO gera documento válido",
    ),
    Mutation(
        "incompletude-sem-justificativa",
        "recusar-se a gerar sem dizer por quê é omissão, não declaração",
        lambda b: b[FECHADO]["binding"].pop("incompleteReason"),
        "sem `incompleteReason`",
    ),
    Mutation(
        "incompletefields-desatualizado",
        "lista de pendências que não corresponde às reais engana quem lê",
        lambda b: b[FECHADO]["binding"].update(
            {"incompleteFields": ["linhas.campoQueNaoEstaPendente"]}),
        "não é campo obrigatório pendente",
    ),
    Mutation(
        "incompletefields-forma-invalida",
        "aninhamento acidental na lista deve reprovar, não estourar",
        lambda b: b[FECHADO]["binding"].update({"incompleteFields": [["linhas.valor"]]}),
        "não é um nome de campo",
    ),
    Mutation(
        "override-sem-valor",
        "override sem valor não preenche o campo e não pode dispensar a pendência",
        lambda b: (b[FECHADO]["binding"].update({"generatable": True}),
                   b[FECHADO]["binding"].update(
                       {"manualOverrides": [{"field": "linhas.valor"}]})),
        "não traz `value`",
    ),
    Mutation(
        "override-sem-campo",
        "override que não nomeia campo não dispensa pendência nenhuma",
        lambda b: b[FECHADO]["binding"].update({"manualOverrides": [{"value": "10.00"}]}),
        "não nomeia um `field`",
    ),
    Mutation(
        "manual-sem-motivo",
        "manual sem motivo é indistinguível de esquecimento",
        lambda b: b[FECHADO]["binding"]["datasets"]["linhas"]["fields"]["valor"]["byRowClass"][1]
        .pop("pendingReason"),
        "sem `pendingReason`",
    ),
    Mutation(
        "byrowclass-origem-invalida",
        "caso sem origem válida deixa a classe de linha sem resolução",
        lambda b: b[FECHADO]["binding"]["datasets"]["linhas"]["fields"]["valor"]["byRowClass"][1]
        .update({"from": "magica"}),
        # Fragmento INDEXADO: o token `byRowClass` sozinho casa com diagnóstico de
        # outra conferência, e a prova passaria pelo motivo errado.
        "byRowClass[1] resolve por 'magica'",
    ),
    Mutation(
        "byrowclass-sem-when",
        "caso sem `when` não diz a que classe de linha se aplica",
        lambda b: b[FECHADO]["binding"]["datasets"]["linhas"]["fields"]["valor"]["byRowClass"][0]
        .pop("when"),
        "sem `when`",
    ),
    # ------------------- forma antes do uso: malformado reprova, não estoura
    Mutation(
        "queries-nao-e-lista",
        "queries que não é lista deve reprovar, não estourar a ferramenta",
        lambda b: b[PLANO]["binding"].update({"queries": "naoEhLista"}),
        "`queries` não é uma lista",
    ),
    Mutation(
        "query-nao-e-mapa",
        "item de queries que não é mapa deve reprovar, não estourar",
        lambda b: b[PLANO]["binding"]["queries"].append("naoEhMapa"),
        "não é um mapa",
    ),
    Mutation(
        "join-nao-e-mapa",
        "item de join que não é mapa deve reprovar, não estourar",
        lambda b: query(b[HIER]["binding"], "base_titulares")["join"].append("naoEhMapa"),
        "não é um mapa",
    ),
    Mutation(
        "join-item-malformado-em-consulta-consumida",
        "join malformado numa consulta que outra COMPÕE: o consumidor recebia o item cru",
        # `movimento` é base de `por_titular` (from), e é sem agregação — então
        # produced_columns percorre os joins dela para somar colunas. Um item escalar
        # ali estourava, porque a porta única garantia só que a CONSULTA é mapa.
        lambda b: query(b[HIER]["binding"], "movimento")["join"].append("naoEhMapa"),
        "não é um mapa",
    ),
    Mutation(
        "join-nao-e-lista",
        "join que não é lista deve reprovar, não ser normalizado em silêncio",
        lambda b: query(b[HIER]["binding"], "movimento").update({"join": "naoEhLista"}),
        "não é uma lista",
    ),
    Mutation(
        "from-do-conjunto-nao-e-mapa",
        "o `from` de um conjunto que não é mapa deve reprovar, não estourar",
        lambda b: b[PLANO]["binding"]["datasets"]["saldos"].update({"from": "naoEhMapa"}),
        "não é um mapa",
    ),

    Mutation(
        "byrowclass-rowset-sem-declaracao",
        "o caminho gêmeo: from rowSet dentro de byRowClass sem o conjunto declarar rowSet",
        lambda b: (dataset(b[FECHADO]["contract"], "linhas").pop("rowSet"),
                   b[FECHADO]["binding"]["datasets"]["linhas"]["fields"]["valor"]["byRowClass"][0]
                   .update({"from": "rowSet", "column": "code"})),
        "byRowClass[0] resolve por rowSet, mas o contrato não declara rowSet",
    ),

    # ------------------------------------- paridade com o motor (Reporter)
    # Estas nasceram do lado de LÁ: implementar o carregador de contratos do motor
    # (pkg/reporter/contract) levantou onze construções que este validador não lia e
    # o motor recusa. Cada uma é um contrato que passava no CI daqui e parava na
    # primeira geração — ou, pior, era aceito pelos dois e aplicado diferente.
    Mutation(
        "campo-tipo-desconhecido",
        "tipo que o motor não sabe aplicar passava aqui e parava na geração",
        lambda b: field(b[PLANO]["contract"], "saldos", "valor").update({"type": "money"}),
        "o motor aplica",
    ),
    Mutation(
        "campo-normalize-desconhecido",
        "a mais perigosa: o campo sairia SEM normalizar num arquivo dado como concluído",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update({"normalize": "uppercase"}),
        "não sabe aplicar",
    ),
    Mutation(
        "campo-escala-negativa",
        "escala negativa não é número de casas decimais de coisa nenhuma",
        lambda b: field(b[PLANO]["contract"], "saldos", "valor")["format"].update({"scale": -1}),
        "está entre 0 e",
    ),
    Mutation(
        "campo-escala-absurda",
        "o motor converte a escala para int32: acima do limite é wrap silencioso",
        lambda b: field(b[PLANO]["contract"], "saldos", "valor")["format"].update({"scale": 2**32}),
        "está entre 0 e",
    ),
    Mutation(
        "campo-length-zero",
        "campo de zero posições é campo que o arquivo não carrega",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update({"length": 0}),
        "ao menos 1",
    ),
    Mutation(
        "pattern-nao-compila",
        "expressão quebrada só seria descoberta na primeira linha conferida contra ela",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update({"pattern": "([0-9]"}),
        "não compila",
    ),
    Mutation(
        "pattern-lookahead",
        "lookahead compila no Python e a RE2 do Go não tem",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update(
            {"pattern": "^(?=[0-9])[0-9]{10}$"}),
        "RE2 do Go não tem",
    ),
    Mutation(
        "pattern-retrorreferencia",
        "retrorreferência compila no Python e a RE2 do Go não tem",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update(
            {"pattern": r"^([0-9])\1{9}$"}),
        "retrorreferência",
    ),
    Mutation(
        "conjunto-sem-campos",
        "conjunto sem campo é seção do arquivo que nada popula",
        lambda b: dataset(b[PLANO]["contract"], "saldos").update({"fields": []}),
        "não declara campo nenhum",
    ),
    Mutation(
        "conjunto-sem-nome",
        "sem nome, a ferramenta ESTOURAVA em vez de reprovar: declared_names lia name na fé",
        lambda b: dataset(b[PLANO]["contract"], "saldos").pop("name"),
        "o name de um conjunto",
    ),
    Mutation(
        "campo-duplicado",
        "dois campos de mesmo nome não podem ambos ser alcançados",
        lambda b: dataset(b[PLANO]["contract"], "saldos")["fields"].append(
            {"name": "codigo", "type": "string", "description": "Cópia."}),
        "declarado duas vezes",
    ),
    Mutation(
        "grao-sobre-campo-inexistente",
        "grão sobre campo fantasma é a exigência de uma linha por combinação que ninguém confere",
        lambda b: dataset(b[PLANO]["contract"], "saldos").update({"grain": ["naoDeclarado"]}),
        "campo que o conjunto não declara",
    ),
    Mutation(
        "childof-ciclo",
        "ciclo de childOf deixa os conjuntos sem raiz, e nenhum é publicado",
        lambda b: dataset(b[HIER]["contract"], "resumos").update(
            {"childOf": {"dataset": "detalhes"}}),
        "fecha um ciclo",
    ),
    Mutation(
        "parametro-tipo-desconhecido",
        "parâmetro de tipo desconhecido nunca poderia ser satisfeito por requisição nenhuma",
        lambda b: parameter(b[PLANO]["contract"], "dataBase").update({"type": "competencia"}),
        "o motor aceita",
    ),
    # --------------------------------------------------------- consolidation
    Mutation(
        "consolidacao-ausente-em-conjunto-de-varias-linhas",
        "um conjunto de várias linhas sem regra de consolidação não poderia ser lido de outra base por esquecimento",
        lambda b: dataset(b[PLANO]["contract"], "saldos").pop("consolidation"),
        "sem consolidation",
    ),
    Mutation(
        "consolidacao-chave-desconhecida",
        "uma chave que o motor não lê é regra que o curador acha que existe e não existe",
        lambda b: dataset(b[PLANO]["contract"], "saldos")["consolidation"].update({"ordem": ["codigo"]}),
        "que o motor não conhece",
    ),
    Mutation(
        "consolidacao-em-conjunto-de-uma-linha",
        "o cabeçalho é uma linha só; não há o que unificar",
        lambda b: dataset(b[PLANO]["contract"], "institution").update(
            {"consolidation": {"key": ["cnpj"], "columns": {}}}),
        "uma linha só",
    ),
    Mutation(
        "consolidacao-em-conjunto-aninhado",
        "o motor não consolida um conjunto que pende de outro",
        lambda b: dataset(b[HIER]["contract"], "detalhes").update(
            {"consolidation": {"key": ["id"], "columns": {"valor": "sum"}}}),
        "aninhado",
    ),
    Mutation(
        "consolidacao-sem-chave",
        "sem chave nada diz quais linhas são a mesma",
        lambda b: dataset(b[PLANO]["contract"], "saldos")["consolidation"].update({"key": []}),
        "não nomeia campo",
    ),
    Mutation(
        "consolidacao-chave-repetida",
        "um campo nomeado duas vezes na chave é erro de digitação que muda nada e engana o leitor",
        lambda b: dataset(b[PLANO]["contract"], "saldos")["consolidation"].update({"key": ["codigo", "codigo"]}),
        "duas vezes",
    ),
    Mutation(
        "consolidacao-chave-inexistente",
        "chave num campo que não existe unifica por nada",
        lambda b: dataset(b[PLANO]["contract"], "saldos")["consolidation"].update({"key": ["conta"]}),
        "não declara",
    ),
    Mutation(
        "consolidacao-chave-fora-da-identidade",
        "unificar por outra chave daria duas linhas da mesma rubrica",
        lambda b: dataset(b[PLANO]["contract"], "saldos")["consolidation"].update(
            {"key": ["naturezaRegistrada"], "columns": {"valor": "sum", "codigo": "first"}}),
        "identificada por",
    ),
    Mutation(
        "consolidacao-modo-desconhecido",
        "um modo que o motor não conhece seria aplicado como outro",
        lambda b: dataset(b[PLANO]["contract"], "saldos")["consolidation"].update({"whenKeyRepeats": "merge"}),
        "'combine' ou 'refuse'",
    ),
    Mutation(
        "consolidacao-recusar-no-conjunto-fechado",
        "toda fonte escreve todas as linhas do catálogo: recusar repetidas recusaria sempre",
        lambda b: dataset(b[FECHADO]["contract"], "linhas").update(
            {"consolidation": {"key": ["codigo"], "whenKeyRepeats": "refuse", "columns": {"valor": "sum"}}}),
        "achada duas vezes",
    ),
    Mutation(
        "consolidacao-coluna-inexistente",
        "regra num campo que não existe não se aplica a nada",
        lambda b: dataset(b[PLANO]["contract"], "saldos")["consolidation"]["columns"].update({"saldo": "sum"}),
        "não declara",
    ),
    Mutation(
        "consolidacao-regra-na-chave",
        "a chave unifica as linhas; combinar a chave não tem sentido",
        lambda b: dataset(b[PLANO]["contract"], "saldos")["consolidation"]["columns"].update({"codigo": "first"}),
        "é chave",
    ),
    Mutation(
        "consolidacao-campo-sem-regra",
        "um campo sem regra seria decidido pelo motor em silêncio",
        lambda b: dataset(b[PLANO]["contract"], "saldos")["consolidation"]["columns"].pop("naturezaRegistrada"),
        "não diz nada de 'naturezaRegistrada'",
    ),
    Mutation(
        "consolidacao-regra-desconhecida",
        "uma regra que o motor não conhece seria aplicada como outra",
        lambda b: dataset(b[PLANO]["contract"], "saldos")["consolidation"]["columns"].update({"valor": "media"}),
        "sum, equal ou first",
    ),
    Mutation(
        "consolidacao-soma-de-texto",
        "somar texto não é conta nenhuma",
        lambda b: dataset(b[PLANO]["contract"], "saldos")["consolidation"]["columns"].update(
            {"naturezaRegistrada": "sum"}),
        "só número se soma",
    ),
    # ---------------------------------------------------------------- filing
    Mutation(
        "filing-chave-desconhecida",
        "uma chave que o motor não lê é regra que o curador acha que existe e não existe",
        lambda b: b[PLANO]["contract"]["filing"].update({"periodo": ["dataBase"]}),
        "que o motor não conhece",
    ),
    Mutation(
        "filing-period-vazio",
        "período vazio faria toda geração ser a mesma entrega",
        lambda b: b[PLANO]["contract"]["filing"].update({"period": []}),
        "period está vazio",
    ),
    Mutation(
        "filing-period-parametro-inexistente",
        "período por um parâmetro que não existe nunca casa duas gerações",
        lambda b: b[PLANO]["contract"]["filing"].update({"period": ["competencia"]}),
        "que não é parâmetro deste contrato",
    ),
    Mutation(
        "filing-period-repetido",
        "o mesmo parâmetro duas vezes no período é erro de digitação",
        lambda b: b[PLANO]["contract"]["filing"].update({"period": ["dataBase", "dataBase"]}),
        "duas vezes",
    ),
    Mutation(
        "filing-remessa-parametro-inexistente",
        "remessa por parâmetro inexistente desliga a regra de original e substituição",
        lambda b: b[PLANO]["contract"]["filing"]["remittance"].update({"parameter": "tipo"}),
        "que não é parâmetro deste contrato",
    ),
    Mutation(
        "filing-remessa-no-periodo",
        "a remessa no período separaria a original da sua substituição",
        lambda b: b[PLANO]["contract"]["filing"].update({"period": ["dataBase", "tipoRemessa"]}),
        "também está em period",
    ),
    Mutation(
        "filing-remessa-fora-do-dominio",
        "um valor que o parâmetro não aceita nunca marca uma entrega",
        lambda b: b[PLANO]["contract"]["filing"]["remittance"].update({"replacement": "R"}),
        "fora do domain",
    ),
    Mutation(
        "filing-remessa-valores-iguais",
        "original e substituição com o mesmo valor não se distinguem",
        lambda b: b[PLANO]["contract"]["filing"]["remittance"].update({"replacement": "I"}),
        "precisam ser distintas",
    ),
    Mutation(
        "parametro-default-fora-do-dominio",
        "default que o próprio domínio recusa é declaração impossível",
        lambda b: parameter(b[PLANO]["contract"], "tipoRemessa").update({"default": "X"}),
        "fora do próprio domain",
    ),
    Mutation(
        "parametro-mes-inexistente",
        "allowedMonths com mês que não existe torna o documento ingerável e ninguém sabe por quê",
        lambda b: parameter(b[PLANO]["contract"], "dataBase").update({"allowedMonths": ["06", "13"]}),
        "um mês é de '01' a '12'",
    ),
    Mutation(
        "parametro-mes-em-tipo-errado",
        "allowedMonths fora de um parâmetro month é restrição que não se aplica a nada",
        lambda b: parameter(b[PLANO]["contract"], "tipoRemessa").update({"allowedMonths": ["06"]}),
        "não é do tipo month",
    ),
    Mutation(
        "parametro-fechado-em-tipo-errado",
        "closed num parâmetro que não é mês nem data não nomeia período que feche",
        lambda b: parameter(b[PLANO]["contract"], "tipoRemessa").update({"closed": True}),
        "não nomeia período que feche",
    ),
    Mutation(
        "parametro-fechado-nao-booleano",
        "closed escrito como texto passaria por verdadeiro sem ninguém ter decidido",
        lambda b: parameter(b[PLANO]["contract"], "dataBase").update({"closed": "sim"}),
        "é true ou false",
    ),
    Mutation(
        "nao-vazio-em-singleton",
        "nonEmpty num singleton não diz nada: é sempre uma linha",
        lambda b: dataset(b[PLANO]["contract"], "institution").update({"nonEmpty": True}),
        "declarado num singleton",
    ),
    Mutation(
        "derivado-de-campo-inexistente",
        "prefixOf apontando para campo que o conjunto não declara não tem de onde cortar",
        lambda b: field(b[PLANO]["contract"], "institution", "cnpj8").update({"prefixOf": "cnpj14"}),
        "que o conjunto não declara",
    ),
    Mutation(
        "derivado-sem-length",
        "prefixOf sem length não diz quantas posições cortar",
        lambda b: field(b[PLANO]["contract"], "institution", "cnpj8").pop("length"),
        "sem length",
    ),
    Mutation(
        "derivado-mapeado-no-binding",
        "o binding que mapeia o derivado daria duas respostas para uma posição",
        lambda b: b[PLANO]["binding"]["datasets"]["institution"]["fields"].update(
            {"cnpj8": {"from": "constant", "value": "12345678"}}),
        "mapeie a origem",
    ),
    Mutation(
        "derivado-mapeado-com-nulo",
        "`cnpj8:` sem valor ainda é um mapeamento do derivado no binding",
        lambda b: b[PLANO]["binding"]["datasets"]["institution"]["fields"].update({"cnpj8": None}),
        "mapeie a origem",
    ),
    Mutation(
        "derivado-nao-texto",
        "o corte produz texto; um derivado declarado como número não pode ser satisfeito",
        lambda b: field(b[PLANO]["contract"], "institution", "cnpj8").update({"type": "integer"}),
        "o derivado é string",
    ),
    Mutation(
        "digito-verificador-desconhecido",
        "um checkDigit que o motor não conhece não verifica nada",
        lambda b: field(b[PLANO]["contract"], "institution", "cnpj").update({"checkDigit": "cpf"}),
        "o motor conhece",
    ),
    Mutation(
        "instituicao-identificador-desconhecido",
        "um identificador de instituição que o motor não confere não confere nada",
        lambda b: field(b[PLANO]["contract"], "institution", "cnpj").update({"identifiesInstitution": "cnpj"}),
        "o campo identifica a instituição (`true`)",
    ),
    Mutation(
        "instituicao-marcada-no-derivado",
        "o derivado não é lido da origem; a identidade é conferida no campo de onde ele é cortado",
        lambda b: field(b[PLANO]["contract"], "institution", "cnpj8").update({"identifiesInstitution": True}),
        "num derivado",
    ),
    Mutation(
        "regra-sem-id",
        "regra sem id não pode ser citada nem pela mensagem que ela mesma produz",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").pop("id"),
        "regra sem id",
    ),
    Mutation(
        "regra-em-texto-livre",
        "uma regra em texto livre é lida em revisão como se protegesse algo e o motor não a executa",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update({"assert": "unique(codigo)"}),
        "texto livre (`assert`)",
    ),
    Mutation(
        "regra-sem-transformacao-nem-conferencia",
        "uma regra que não transforma nem confere não faz nada",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").pop("check"),
        "exatamente um de transform ou check",
    ),
    Mutation(
        "regra-com-transformacao-e-conferencia",
        "uma regra faz uma coisa",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update(
            {"transform": {"negateWhen": {"field": "valor", "table": "natureza", "key": "codigo", "equals": "debit"}}}),
        "exatamente um de transform ou check",
    ),
    Mutation(
        "regra-sem-severidade",
        "uma conferência sem severidade não diz se bloqueia a geração",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").pop("severity"),
        "o motor executa error",
    ),
    Mutation(
        "conferencia-que-so-avisa",
        "warning e info numa conferência estão definidos e não implementados",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update({"severity": "warning"}),
        "o motor executa error",
    ),
    Mutation(
        "transformacao-com-severidade",
        "uma transformação não falha",
        lambda b: rule(b[PLANO]["contract"], "saldo-na-natureza").update({"severity": "error"}),
        "uma transformação não falha",
    ),
    Mutation(
        "regra-definida-nao-implementada",
        "um tipo que o motor ainda não executa é recusado, não carregado como promessa",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update({"check": {"equalsSumOf": {"field": "valor"}}}),
        "definido e ainda não implementado",
    ),
    Mutation(
        "regra-tipo-desconhecido",
        "um tipo fora do vocabulário não é executado por ninguém",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update({"check": {"distinct": ["codigo"]}}),
        "é 'distinct'",
    ),
    Mutation(
        "regra-aponta-campo-inexistente",
        "regra sobre campo fantasma nunca dispara",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update({"check": {"unique": ["naoDeclarado"]}}),
        "campo 'naoDeclarado', que 'saldos' não declara",
    ),
    Mutation(
        "regra-tabela-nao-publicada",
        "uma regra que consulta tabela que o contrato não publica não responde nada",
        lambda b: rule(b[PLANO]["contract"], "natureza-registrada")["check"]["equalsLookup"].update({"table": "outra"}),
        "a tabela 'outra', que o contrato não publica",
    ),
    Mutation(
        "regra-aplica-a-conjunto-inexistente",
        "o alvo de uma regra é um conjunto do contrato",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update({"appliesTo": "fantasma"}),
        "que não é um conjunto do contrato",
    ),
    Mutation(
        "regra-where-sem-comparacao",
        "um where que não compara com nada não restringe linha nenhuma",
        lambda b: rule(b[JANELAS]["contract"], "estoque-sem-grupo-cinco")["where"].pop("equals"),
        "exatamente um de equals, in ou notIn",
    ),
    Mutation(
        "regra-existsin-de-outro-conjunto",
        "existsIn lê as linhas que o PRÓPRIO conjunto publica",
        lambda b: rule(b[FECHADO]["contract"], "conta-do-conjunto")["check"]["existsIn"].update({"rowSet": "outro.yaml"}),
        "e o conjunto publica",
    ),

    # ------------------ texto onde YAML pode entregar lista ou mapa
    # Achadas pelo CodeRabbit no PR e confirmadas uma a uma: TODAS faziam a
    # ferramenta ESTOURAR em vez de reprovar. `["a"] in {"string"}` levanta
    # unhashable type, e uma lista usada como chave de dicionário faz o mesmo — não
    # é um erro que Python reporte educadamente. Ferramenta que estoura com entrada
    # malformada não reprova nada, que é a lição que esta suíte já carrega em três
    # lugares.
    Mutation(
        "nome-de-conjunto-e-lista",
        "nome que é lista vira chave de dicionário e estoura antes de qualquer conferência",
        lambda b: dataset(b[PLANO]["contract"], "saldos").update({"name": ["saldos", "outro"]}),
        "o name de um conjunto",
    ),
    Mutation(
        "nome-de-campo-e-mapa",
        "idem para campo, um passo adiante no mesmo leitor",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update({"name": {"a": 1}}),
        "o name de um campo",
    ),
    Mutation(
        "tipo-de-campo-e-lista",
        "membership de lista em conjunto levanta unhashable, não reprova",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update({"type": ["string"]}),
        "o tipo de um campo é uma palavra",
    ),
    Mutation(
        "normalize-e-lista",
        "idem para normalize, o caminho gêmeo do tipo",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update({"normalize": ["digits"]}),
        "uma normalização é uma palavra",
    ),
    Mutation(
        "nome-de-parametro-e-lista",
        "o último leitor que ainda tomava nome na fé, e só a prova o encontrou",
        lambda b: parameter(b[PLANO]["contract"], "dataBase").update({"name": ["dataBase"]}),
        "o name de um parâmetro",
    ),
    Mutation(
        "tipo-de-parametro-e-lista",
        "idem para o tipo do parâmetro",
        lambda b: parameter(b[PLANO]["contract"], "dataBase").update({"type": ["month"]}),
        "o tipo de um parâmetro é uma palavra",
    ),
    Mutation(
        "mes-permitido-e-lista",
        "item de allowedMonths que não é texto",
        lambda b: parameter(b[PLANO]["contract"], "dataBase").update({"allowedMonths": [["06"]]}),
        "um mês é de '01' a '12'",
    ),
    Mutation(
        "regra-e-escalar",
        "uma regra escrita como texto solto não tem .get, e o leitor não perguntava",
        lambda b: b[PLANO]["contract"]["rules"].append("uma regra escrita errado"),
        "uma regra é um mapeamento",
    ),
    Mutation(
        "applies-to-e-lista",
        "appliesTo que não é texto não tem .partition",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update({"appliesTo": ["saldos"]}),
        "que não é um conjunto do contrato",
    ),


    # -------------------- coleção nula, valor aninhado, e dois silêncios
    # Segunda rodada de revisão. As quatro primeiras são a mesma classe das de cima
    # chegando um nível mais fundo; as duas últimas não estouravam — PASSAVAM, que é
    # a forma pior.
    Mutation(
        "datasets-nulo",
        "`datasets:` sem nada embaixo é null, e `for ds in None` estoura",
        lambda b: b[PLANO]["contract"].update({"datasets": None}),
        "datasets está vazio",
    ),
    Mutation(
        "datasets-nao-e-lista",
        "o curador escreveu algo ali; ignorar seria conferir outro contrato",
        lambda b: b[PLANO]["contract"].update({"datasets": "saldos"}),
        "datasets é a lista dos conjuntos",
    ),
    Mutation(
        "fields-nulo",
        "idem um nível abaixo",
        lambda b: dataset(b[PLANO]["contract"], "saldos").update({"fields": None}),
        "não declara campo nenhum",
    ),
    Mutation(
        "parameters-nulo",
        "e no outro ramo da mesma árvore",
        lambda b: b[PLANO]["contract"].update({"parameters": None}),
        "que o contrato não declara em parameters",
    ),
    Mutation(
        "grao-com-item-que-nao-e-texto",
        "item de grain que é lista levanta unhashable na conferência de pertinência",
        lambda b: dataset(b[PLANO]["contract"], "saldos").update({"grain": [["codigo"]]}),
        "campo que o conjunto não declara",
    ),
    Mutation(
        "childof-nao-e-mapa",
        "childOf lido em quatro lugares, e os quatro tomavam .get na fé",
        lambda b: dataset(b[HIER]["contract"], "detalhes").update({"childOf": []}),
        "childOf é um mapeamento",
    ),
    Mutation(
        "childof-dataset-nao-e-texto",
        "e o nome do pai dentro dele",
        lambda b: dataset(b[HIER]["contract"], "detalhes").update({"childOf": {"dataset": ["resumos"]}}),
        "childOf nomeia o conjunto pai por texto",
    ),
    Mutation(
        "regra-sobre-parametro",
        "uma regra executada lê as linhas de um conjunto; parâmetros não são conjunto",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update(
            {"appliesTo": "parameters.fantasma"}),
        "que não é um conjunto do contrato",
    ),
    Mutation(
        "retrorreferencia-apos-barra-escapada",
        "três barras: as duas primeiras são uma barra literal, a terceira abre a retrorreferência",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update(
            {"pattern": r"^([0-9])\\\1$"}),
        "retrorreferência",
    ),


    # ------------------- coleção que existe e NÃO é lista, nos quatro lugares
    # A rodada anterior cobriu `null` e cobriu `datasets` não-lista, e deixou as
    # outras três de fora. Uma coleção nula e uma coleção que é outra coisa passam
    # por ramos DIFERENTES de sequence_at, e só um deles estava afirmado.
    #
    # `rules: null` não entra: rules é opcional, então declarar nenhuma é legítimo e
    # não há reprovação para afirmar.
    Mutation(
        "rules-nao-e-lista",
        "o curador escreveu algo em rules; ignorar seria conferir outro contrato",
        lambda b: b[PLANO]["contract"].update({"rules": "sem-duplicata"}),
        "rules é a lista das conferências",
    ),
    Mutation(
        "parameters-nao-e-lista",
        "idem para os parâmetros de geração",
        lambda b: b[PLANO]["contract"].update({"parameters": "dataBase"}),
        "parameters é a lista dos parâmetros",
    ),
    Mutation(
        "fields-nao-e-lista",
        "idem um nível abaixo, onde a porta é chamada por oito leitores",
        lambda b: dataset(b[PLANO]["contract"], "saldos").update({"fields": "codigo"}),
        "fields é a lista dos campos",
    ),


    # ------------- construção que aponta e não nomeia para onde
    # Mapeamento VAZIO é falso em Python, então o chamador o lia como "não declarou"
    # e pulava a conferência inteira: o curador escrevia a integridade referencial e
    # ela não valia para nada. Vazio e incompleto passam pelo mesmo caminho.
    Mutation(
        "refers-to-vazio",
        "refersTo sem nada dentro era lido como refersTo ausente",
        lambda b: field(b[HIER]["contract"], "resumos", "codTitular").update({"refersTo": {}}),
        "refersTo.dataset",
    ),
    Mutation(
        "refers-to-sem-field",
        "metade da referência é referência nenhuma",
        lambda b: field(b[HIER]["contract"], "resumos", "codTitular").update(
            {"refersTo": {"dataset": "titulares"}}),
        "refersTo.field",
    ),
    Mutation(
        "equals-sum-of-vazio",
        "soma que não diz de onde reconcilia coisa nenhuma, e passava calada",
        lambda b: field(b[HIER]["contract"], "resumos", "total").update({"equalsSumOf": {}}),
        "equalsSumOf.dataset",
    ),
    Mutation(
        "condicao-sem-field",
        "condição que não nomeia o campo lido nunca dispara",
        lambda b: field(b[HIER]["contract"], "resumos", "inscricao").update(
            {"requiredWhen": {"equals": "PJ"}}),
        "requiredWhen.field",
    ),


    # ---------------- chave escrita e vazia, que não é chave ausente
    # `refersTo:` sem nada embaixo é `null` em YAML, e `.get()` devolve isso idêntico
    # a ausente. As duas vêm de pessoas diferentes: ausente é "este documento não tem
    # isso"; escrita e vazia é alguém que começou a declarar e parou. Nenhum contrato
    # curado usa null explícito para dizer "nenhum".
    #
    # Uma por construção opcional, porque foi tapando uma de cada vez que esta classe
    # voltou quatro vezes.
    Mutation(
        "refers-to-escrito-vazio",
        "integridade referencial declarada pela metade e ignorada",
        lambda b: field(b[HIER]["contract"], "resumos", "codTitular").update({"refersTo": None}),
        "refersTo foi escrita e está vazia",
    ),
    Mutation(
        "equals-sum-of-escrito-vazio",
        "reconciliação declarada pela metade e ignorada",
        lambda b: field(b[HIER]["contract"], "resumos", "total").update({"equalsSumOf": None}),
        "equalsSumOf foi escrita e está vazia",
    ),
    Mutation(
        "required-when-escrito-vazio",
        "condicional declarada pela metade: o campo vira opcional de fato",
        lambda b: field(b[HIER]["contract"], "resumos", "inscricao").update({"requiredWhen": None}),
        "requiredWhen foi escrita e está vazia",
    ),
    Mutation(
        "forbidden-when-escrito-vazio",
        "idem do outro lado",
        lambda b: field(b[HIER]["contract"], "titulares", "cnpj").update({"forbiddenWhen": None}),
        "forbiddenWhen foi escrita e está vazia",
    ),
    Mutation(
        "child-of-escrito-vazio",
        "hierarquia declarada pela metade: a seção nunca é populada",
        lambda b: dataset(b[HIER]["contract"], "detalhes").update({"childOf": None}),
        "childOf foi escrita e está vazia",
    ),
    Mutation(
        "format-escrito-vazio",
        "formato declarado pela metade: o valor sai como veio",
        lambda b: field(b[PLANO]["contract"], "saldos", "valor").update({"format": None}),
        "format foi escrita e está vazia",
    ),
    Mutation(
        "grain-escrito-vazio",
        "grão declarado pela metade: nada confere uma linha por rubrica",
        lambda b: dataset(b[PLANO]["contract"], "saldos").update({"grain": None}),
        "grain foi escrita e está vazia",
    ),
    Mutation(
        "row-set-escrito-vazio",
        "conjunto fechado declarado pela metade",
        lambda b: dataset(b[FECHADO]["contract"], "linhas").update({"rowSet": None}),
        "rowSet foi escrita e está vazia",
    ),
    Mutation(
        "pattern-escrito-vazio",
        "forma do valor declarada pela metade",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update({"pattern": None}),
        "pattern foi escrita e está vazia",
    ),
    Mutation(
        "normalize-escrito-vazio",
        "normalização declarada pela metade: o valor sai sem normalizar",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update({"normalize": None}),
        "normalize foi escrita e está vazia",
    ),
    Mutation(
        "length-escrito-vazio",
        "largura declarada pela metade",
        lambda b: field(b[PLANO]["contract"], "institution", "cnpj8").update({"length": None}),
        "length foi escrita e está vazia",
    ),
    Mutation(
        "domain-escrito-vazio",
        "domínio declarado pela metade: qualquer valor passa",
        lambda b: parameter(b[PLANO]["contract"], "tipoRemessa").update({"domain": None}),
        "domain foi escrita e está vazia",
    ),
    Mutation(
        "allowed-months-escrito-vazio",
        "restrição de mês declarada pela metade: o documento vira gerável em qualquer mês",
        lambda b: parameter(b[PLANO]["contract"], "dataBase").update({"allowedMonths": None}),
        "allowedMonths foi escrita e está vazia",
    ),


    # ------------------------------------------------------ join de tabela
    Mutation(
        "join-de-tabela-sem-colunas",
        "um join de tabela que não nomeia colunas não traz nada que a consulta leia",
        lambda b: query(b[PLANO]["binding"], "saldos_por_rubrica").update(
            {"join": [{"table": "saldo", "match": {"rota": "id"}}]}),
        "não diz que colunas traz",
    ),
    Mutation(
        "join-de-consulta-com-colunas",
        "as colunas de uma consulta já são dela; declarar `columns` num join dela não diz nada",
        lambda b: query(b[PLANO]["binding"], "saldos_por_rubrica").update(
            {"join": [{"query": "declarante", "match": {"rota": "id"}, "columns": {"x": "y"}}]}),
        "declara `columns`",
    ),

    # ------------------------------------------------- natureza das rubricas
    Mutation(
        "natureza-sem-arquivo",
        "contrato declara a tabela e ela não está ao lado: toda retificadora sairia com o sinal trocado",
        lambda b: b[PLANO].__setitem__("natureza", None),
        "que não existe",
    ),
    Mutation(
        "tabela-casada-de-outro-jeito",
        "o motor casa uma tabela pelo prefixo mais longo, e só assim",
        lambda b: b[PLANO]["contract"]["tables"][0].update({"match": "exact"}),
        "o motor casa por longestPrefix",
    ),
    Mutation(
        "natureza-em-diretorio",
        "a tabela é arquivo ao lado do contrato; um caminho sai da pasta do documento",
        lambda b: b[PLANO]["contract"]["tables"][0].update({"from": "../natureza.yaml"}),
        "nomeado sem diretório",
    ),
    Mutation(
        "natureza-prefixo-pontuado",
        "o razão carrega o código sem pontuação, e um prefixo pontuado nunca casa",
        lambda b: b[PLANO]["natureza"]["byPrefix"].update({"1.6.9": "credit"}),
        "não é texto de dígitos",
    ),
    Mutation(
        "natureza-lado-invalido",
        "uma natureza é devedora ou credora, e a regra compara com essas palavras",
        lambda b: b[PLANO]["natureza"]["byPrefix"].update({"4": "passivo"}),
        "a natureza é debit ou credit",
    ),
    Mutation(
        "natureza-lado-que-nao-e-texto",
        "uma natureza escrita como lista reprova, nunca derruba a ferramenta",
        lambda b: b[PLANO]["natureza"]["byPrefix"].update({"4": ["credit"]}),
        "a natureza é debit ou credit",
    ),
    Mutation(
        "natureza-de-elenco-nao-publicado",
        "a tabela foi gerada de um elenco que o catálogo não publica, então ninguém a reproduz",
        lambda b: b[PLANO]["natureza"].update({"sha256": "0" * 64}),
        "que o catálogo não publica",
    ),
    Mutation(
        "natureza-sem-sha",
        "uma tabela sem o sha256 do elenco foi escrita à mão",
        lambda b: b[PLANO]["natureza"].pop("sha256"),
        "não traz o sha256",
    ),
    Mutation(
        "natureza-solta",
        "uma tabela que nenhum contrato declara não é regra de documento nenhum",
        lambda b: (b[PLANO]["contract"].pop("tables"),
                   [b[PLANO]["contract"]["rules"].remove(r) for r in list(b[PLANO]["contract"]["rules"])
                    if r["id"] in ("saldo-na-natureza", "natureza-registrada")]),
        "que o contrato não declara em `tables`",
    ),
    Mutation(
        "natureza-copias-divergentes",
        "duas cópias diferentes dariam a uma rubrica um sinal em um documento e outro no seguinte",
        lambda b: (b[HIER]["contract"].update(
                       {"tables": [{"name": "natureza", "from": "natureza.yaml", "match": "longestPrefix"}]}),
                   b[HIER].__setitem__("natureza", {**copy.deepcopy(fixtures.PLANO_NATUREZA),
                                                     "byPrefix": {"1": "debit", "4": "credit"}})),
        "diferem",
    ),
]


# Chaves que o validador lê e que NÃO pertencem ao contrato, por isso não são
# cobradas das fixturas de contrato. Cada grupo tem sua própria fixture, que a
# varredura de formas não percorre porque ela é sobre o contrato.
_NOT_CONTRACT_KEYS = {
    # binding.example.yaml
    "queries", "query", "join", "match", "from", "having", "derive", "parentMatch",
    "byRowClass", "generatable", "incompleteReason", "incompleteFields",
    "manualOverrides", "columns", "aggregation", "aggregate", "dataSource", "column",
    "table", "source", "filters", "select", "groupBy", "lookup", "of", "as", "on",
    "accumulate", "rowKey", "compute", "case", "otherwise", "at", "calendar", "operator",
    "values", "parameter",
    # o texto livre que saiu da gramática: lido só para ser recusado
    "assert",
    "when", "value", "statedIn", "pendingReason", "measures", "contract", "institution",
    # catalog.yaml
    "documents", "path",
    # contas.yaml — o conjunto fechado
    "rows", "masked",
    # natureza.yaml — a tabela de naturezas do elenco
    "byPrefix", "sha256",
}


# Uma chave de contrato é lowerCamelCase. O filtro tira o que a varredura da árvore
# sintática também encontra e não é chave nenhuma: o "\n" de um join, o "." de um
# split, o CATALOG_ROOT do ambiente.
_CONTRACT_KEY = re.compile(r"^[a-z][a-zA-Z0-9]*$")


def _keys_the_validator_reads() -> set[str]:
    """Toda chave literal que o validador consulta, lida da ÁRVORE SINTÁTICA.

    Pela árvore e não por expressão regular porque a regular via uma forma só —
    `.get("x")` com aspas duplas. Um `.get('x')`, um `contract["x"]`, e a
    conferência passava a afirmar menos do que diz afirmar, em silêncio. A árvore vê
    as três formas e, ao contrário da regular, não confunde prosa com código: esta
    mesma suíte tem um `["a"] in {"string"}` dentro de um comentário.
    """
    tree = ast.parse((TOOLS / "validate.py").read_text(encoding="utf-8"))
    keys: set[str] = set()

    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and node.args):
            keys.add(_literal(node.args[0]))

        if isinstance(node, ast.Subscript):
            keys.add(_literal(node.slice))

        if isinstance(node, ast.Compare) and any(isinstance(o, (ast.In, ast.NotIn)) for o in node.ops):
            keys.add(_literal(node.left))

    return {key for key in keys if key and _CONTRACT_KEY.match(key)}


def _literal(node: ast.expr) -> str:
    """O texto de um nó constante, ou "" quando ele não é um."""
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""


def _collect_keys(node: object, out: set[str]) -> None:
    """Toda chave de mapeamento em qualquer profundidade."""
    if isinstance(node, dict):
        for key, value in node.items():
            out.add(str(key))
            _collect_keys(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_keys(value, out)


def _value_paths(node: object, prefix: str = "") -> Iterator[str]:
    """Todo caminho até um valor dentro do contrato, incluindo os aninhados."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{prefix}.{key}" if prefix else str(key)
            yield here
            yield from _value_paths(value, here)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            here = f"{prefix}[{index}]"
            yield here
            yield from _value_paths(value, here)


def _set_at(root: dict, path: str, value: object) -> bool:
    """Escreve o valor no caminho, respondendo se conseguiu."""
    steps: list[object] = []

    for segment in path.split("."):
        while "[" in segment:
            head, _, rest = segment.partition("[")
            if head:
                steps.append(head)
            index, _, segment = rest.partition("]")
            steps.append(int(index))
        if segment:
            steps.append(segment)

    cursor: object = root

    try:
        for step in steps[:-1]:
            cursor = cursor[step]  # type: ignore[index]
        cursor[steps[-1]] = value  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return False

    return True


def _rewrite_contract(root: Path, doc: str, data: dict) -> bool:
    """Reescreve só o contrato de um documento e o índice que deriva dele."""
    try:
        (root / doc / "contract.yaml").write_text(
            yaml.safe_dump(data[doc]["contract"], sort_keys=False, allow_unicode=True),
            encoding="utf-8")

        documents = [
            parts.get("indexEntry") or fixtures._index_entry(parts["contract"], path)
            for path, parts in data.items()
        ]
        (root / "catalog.yaml").write_text(
            yaml.safe_dump({"apiVersion": fixtures.APIV, "kind": "Catalog", "documents": documents},
                           sort_keys=False, allow_unicode=True),
            encoding="utf-8")
    except Exception:  # noqa: BLE001 — fixture não serializável não é o alvo da varredura
        return False

    return True


def _run_in_process(root: Path) -> str | None:
    """Roda o validador nesta mesma máquina virtual, devolvendo a exceção se houver.

    Aponta o ROOT do módulo para a árvore de fixtures — a mesma variável que
    CATALOG_ROOT define no executável — e chama main(). Devolve None quando a
    ferramenta terminou, tendo reprovado ou não; devolve o texto da exceção quando
    ela estourou.
    """
    previous = validate.ROOT
    validate.ROOT = root

    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            validate.main()
    except Exception as exc:  # noqa: BLE001 — apanhar QUALQUER estouro é o objetivo
        return f"{type(exc).__name__}: {exc}"
    finally:
        validate.ROOT = previous

    return None


def _run(root: Path) -> tuple[int, str]:
    env = dict(os.environ, CATALOG_ROOT=str(root))
    # Timeout porque a suíte roda no CI antes do validador e abre um processo por
    # mutação: sem ele, uma mudança que trave o validador prenderia o job até o
    # limite do runner, em vez de falhar nomeando a mutação culpada.
    try:
        proc = subprocess.run(
            [sys.executable, str(VALIDATE)], env=env, capture_output=True, text=True,
            check=False, timeout=60)
    except subprocess.TimeoutExpired:
        return 124, "a ferramenta não terminou em 60s"

    return proc.returncode, proc.stdout + proc.stderr


class ValidatorSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="catalog-fixtures-")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _write(self, data: dict) -> Path:
        root = Path(tempfile.mkdtemp(dir=self._tmp)) / "catalog"
        root.mkdir()
        fixtures.write(root, data)
        return root

    def test_fixtures_are_valid(self) -> None:
        """A base é válida — sem isso, toda mutação passaria por acidente."""
        code, out = _run(self._write(fixtures.bundle()))
        self.assertEqual(code, 0, f"as fixtures deveriam validar:\n{out}")

    def test_real_catalog_is_valid(self) -> None:
        """E o catálogo de verdade também: a suíte não substitui a conferência dele."""
        code, out = _run(TOOLS.parent)
        self.assertEqual(code, 0, f"o catálogo real deveria validar:\n{out}")

    def test_every_mutation_is_caught(self) -> None:
        """Cada conferência reprova a quebra que ela existe para pegar.

        Um caso que deixa de falhar aqui é uma conferência que ficou frouxa — foi
        assim que quatro frouxidões em cadeia entraram neste validador antes de a
        suíte existir.
        """
        seen: set[str] = set()

        for mutation in MUTATIONS:
            with self.subTest(mutation=str(mutation)):
                self.assertNotIn(mutation.ident, seen, "identificador de mutação duplicado")
                seen.add(mutation.ident)

                data = fixtures.bundle()
                mutation.apply(data)
                code, out = _run(self._write(data))

                # Um traceback também sai com código 1, e o texto dele ecoa a linha
                # ofensora — então `code == 1` mais um fragmento esperado aceitaria um
                # CRASH como se fosse reprovação. Quatro destas mutações existem
                # justamente para provar que entrada malformada reprova EM VEZ DE
                # estourar; sem esta asserção elas provariam o contrário do que dizem.
                self.assertNotIn(
                    "Traceback", out,
                    f"{mutation.ident}: a ferramenta ESTOUROU em vez de reprovar:\n{out}")

                self.assertEqual(code, 1, f"{mutation.ident}: deveria REPROVAR e passou:\n{out}")
                self.assertIn(
                    mutation.expect, out,
                    f"{mutation.ident}: reprovou, mas sem nomear o problema.\n"
                    f"esperado conter: {mutation.expect!r}\nsaiu:\n{out}")

    def test_no_shape_of_any_value_makes_the_tool_crash(self) -> None:
        """VARREDURA: troca cada valor do contrato por formas erradas e exige que
        nenhuma estoure.

        Existe porque a mesma classe de defeito voltou em TRÊS rodadas de revisão
        seguidas, e a terceira encontrou 84 combinações que estouravam. Corrigir uma
        por uma é o jogo que já se perdeu três vezes: guardei `declared_names` e
        esqueci o `by_name` ao lado; escrevi que `childOf` tinha dois leitores,
        corrigi para três, eram quatro; guardei um laço de `check_index` e o segundo
        laço DA MESMA FUNÇÃO tinha o mesmo defeito.

        A conferência não é sobre qual valor: é sobre a propriedade de que YAML
        entrega qualquer forma e a ferramenta REPROVA em vez de estourar. Uma
        construção nova acrescentada ao contrato entra nesta varredura sozinha, sem
        ninguém lembrar de escrever a mutação — que é o que ninguém lembrou três vezes.

        Não afirma que cada forma errada é RECUSADA: algumas são legitimamente
        ignoradas, como uma coleção opcional ausente. Afirma que nenhuma derruba a
        ferramenta.

        Roda EM PROCESSO, e é a única conferência daqui que não passa pelo executável:
        são milhares de combinações, e um subprocesso cada levaria a suíte de sete
        segundos para muitos minutos — uma suíte que ninguém espera é uma suíte que
        ninguém roda. A exceção é apanhada direto, o que também é uma asserção mais
        forte que procurar "Traceback" na saída.
        """
        shapes = {
            "lista": ["x"],
            "texto": "x",
            "inteiro": 7,
            "mapa": {"k": "v"},
            "nulo": None,
            "lista vazia": [],
        }

        crashes: list[str] = []

        for doc in (PLANO, FECHADO, HIER, JANELAS):
            # A árvore é escrita UMA vez e só o contrato mutado (e o índice, que
            # deriva dele) é reescrito por combinação. Escrever as cinco fixturas
            # inteiras mil e seiscentas vezes levava a suíte a mais de um minuto, e
            # suíte que ninguém espera é suíte que ninguém roda.
            root = self._write(fixtures.bundle())

            for path in sorted(_value_paths(fixtures.bundle()[doc]["contract"])):
                for name, shape in shapes.items():
                    data = fixtures.bundle()

                    if not _set_at(data[doc]["contract"], path, copy.deepcopy(shape)):
                        continue

                    if not _rewrite_contract(root, doc, data):
                        continue

                    crash = _run_in_process(root)

                    if crash is not None:
                        crashes.append(f"{doc} :: {path} = {name} -> {crash}")

            _rewrite_contract(root, doc, fixtures.bundle())

        self.assertEqual(
            [], crashes,
            "a ferramenta ESTOUROU em vez de reprovar para estes valores:\n  "
            + "\n  ".join(crashes))

    def test_fixtures_exercise_every_contract_construct_the_tool_reads(self) -> None:
        """A cobertura da varredura é a cobertura das FIXTURAS.

        A varredura acima só alcança valor que alguma fixture declara. Quando ela
        passou verde e ainda havia um estouro no ramo do `via`, o defeito não era
        dela: era que fixture nenhuma usava `via`, então aquele ramo do validador
        nunca era executado — e um leitor que ninguém executa é um leitor que ninguém
        confere.

        Esta conferência lê o CÓDIGO do validador procurando toda chave de contrato
        que ele consulta, e exige que as fixturas declarem cada uma. Falhar aqui não
        quer dizer que o validador está errado: quer dizer que a rede que o confere
        acabou de ficar com um buraco, e o conserto é acrescentar a construção a uma
        fixture.
        """
        read = _keys_the_validator_reads()

        declared: set[str] = set()
        for parts in fixtures.bundle().values():
            _collect_keys(parts["contract"], declared)

        missing = sorted((read - declared) - _NOT_CONTRACT_KEYS)

        self.assertEqual(
            [], missing,
            "o validador lê estas construções de contrato e nenhuma fixture as "
            "declara, então a varredura não alcança os leitores delas:\n  "
            + "\n  ".join(missing))

    def test_a_single_problem_is_reported_once(self) -> None:
        """Um problema, uma linha — por mais leitores que tropecem nele.

        Agora que as leituras passam por portas, uma porta chamada por oito leitores
        reprovava oito vezes o MESMO valor. As sete cópias não acrescentam nada e
        empurram para fora da tela as outras reprovações, que são o que o curador
        precisa ver: com `fields` malformado, a saída trazia oito linhas iguais e
        escondia as três que diziam quais posições do template ficaram órfãs.
        """
        data = fixtures.bundle()
        dataset(data[PLANO]["contract"], "saldos")["fields"] = "codigo"

        code, out = _run(self._write(data))
        self.assertEqual(1, code)

        repeated = "fields é a lista dos campos"
        self.assertEqual(
            1, out.count(repeated),
            f"a mesma reprovação saiu {out.count(repeated)} vezes:\n{out}")

        # E as outras continuam visíveis, que é o ponto.
        self.assertIn("não declara campo nenhum", out)
        self.assertIn("template usa saldos.codigo", out)

    def test_missing_catalog_fails_without_crashing(self) -> None:
        """Árvore sem catalog.yaml reprova em vez de estourar.

        Ferramenta que quebra com entrada malformada não reprova nada — foi a lição
        de três achados desta sessão.
        """
        empty = Path(tempfile.mkdtemp(dir=self._tmp))
        code, out = _run(empty)
        self.assertEqual(code, 1, f"deveria reprovar:\n{out}")
        self.assertNotIn("Traceback", out, f"estourou em vez de reprovar:\n{out}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
