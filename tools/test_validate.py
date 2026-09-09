#!/usr/bin/env python3
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

import contextlib
import copy
import io
import os
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
        "regra-sem-severidade",
        "regra sem severidade não diz se bloqueia a geração ou apenas avisa",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").pop("severity"),
        "use error, warning ou info",
    ),
    Mutation(
        "regra-para-conjunto-inexistente",
        "regra apontando para conjunto que não existe nunca é aplicada",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update(
            {"appliesTo": "conjuntoFantasma"}),
        "que o contrato não declara",
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
        lambda b: b[PLANO]["binding"]["datasets"]["institution"]["fields"]["cnpj8"].update(
            {"from": "magica"}),
        "use query, constant, parameter, manual, rowSet ou byRowClass",
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
        lambda b: b[FECHADO]["contas"]["accounts"][0].update({"code": "11000002"}),
        "não bate com o pattern",
    ),
    Mutation(
        "code-diverge-do-masked",
        "código transcrito à mão divergindo da forma oficial — aconteceu de verdade",
        lambda b: b[FECHADO]["contas"]["accounts"][2].update({"code": "3097010009"}),
        "transcrição do código diverge",
    ),
    Mutation(
        "conta-sem-masked",
        "sem a forma oficial, o código não tem contra o que ser conferido",
        lambda b: b[FECHADO]["contas"]["accounts"][0].pop("masked"),
        "não tem `masked`",
    ),
    Mutation(
        "conta-duplicada",
        "conta duplicada no conjunto emite a mesma linha duas vezes",
        lambda b: b[FECHADO]["contas"]["accounts"].append(
            dict(b[FECHADO]["contas"]["accounts"][0])),
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
        "accounts-nao-e-lista",
        "forma malformada deve reprovar, não estourar a ferramenta",
        lambda b: b[FECHADO].__setitem__("contas", {"accounts": "naoEhLista"}),
        "não tem uma lista `accounts`",
    ),
    Mutation(
        "conta-nao-e-mapa",
        "linha do conjunto que não é mapa deve reprovar, não estourar",
        lambda b: b[FECHADO]["contas"]["accounts"].append(["1100000002"]),
        "que não é mapa",
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
        "regra-sem-id",
        "regra sem id não pode ser citada nem pela mensagem que ela mesma produz",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").pop("id"),
        "regra sem id",
    ),
    Mutation(
        "regra-sem-assert",
        "regra sem assert é lida em revisão como se protegesse algo e não confere nada",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").pop("assert"),
        "não tem assert",
    ),
    Mutation(
        "regra-aponta-campo-inexistente",
        "a cabeça de appliesTo era conferida e a CAUDA não: regra sobre campo fantasma nunca dispara",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update(
            {"appliesTo": "saldos.naoDeclarado"}),
        "campo que 'saldos' não declara",
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
        "é o nome do que ela lê",
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
        "regra-sobre-parametro-fantasma",
        "a cauda de appliesTo era conferida para conjunto e NÃO para parameters: regra que nunca dispara",
        lambda b: rule(b[PLANO]["contract"], "sem-duplicata").update(
            {"appliesTo": "parameters.fantasma"}),
        "parâmetro que o contrato não declara",
    ),
    Mutation(
        "retrorreferencia-apos-barra-escapada",
        "três barras: as duas primeiras são uma barra literal, a terceira abre a retrorreferência",
        lambda b: field(b[PLANO]["contract"], "saldos", "codigo").update(
            {"pattern": r"^([0-9])\\\1$"}),
        "retrorreferência",
    ),

]


def _value_paths(node: object, prefix: str = "") -> "Iterator[str]":
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

        for doc in (PLANO, FECHADO, HIER):
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
