#!/usr/bin/env python3
"""Confere a integridade do catálogo.

Existe porque a disciplina que o CONTRIBUTING descreve não se sustenta só na
revisão humana: as verificações abaixo são justamente as que passam despercebidas
numa leitura, e cada uma corresponde a um erro que produz arquivo regulatório
errado com aparência de certo.

Não confere o CONTEÚDO regulatório — se a rubrica está no elenco, se a regra
reflete o manual. Isso é revisão humana contra a fonte primária, e nenhum script
substitui.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml

# A raiz do catálogo. Sobrescrevível por CATALOG_ROOT para a suíte de teste poder
# apontar a ferramenta para uma árvore de fixtures — sem isso, as provas de mutação
# só existiriam como comandos digitados à mão, que é como elas nasceram.
ROOT = Path(os.environ.get("CATALOG_ROOT", Path(__file__).resolve().parent.parent)).resolve()
FAILURES: list[str] = []
WARNINGS: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)


def warn(msg: str) -> None:
    WARNINGS.append(msg)


def load(path: Path):
    """Lê um YAML do catálogo, reprovando em vez de estourar.

    Arquivo ausente é reprovação e não exceção: a ferramenta é a rede que impede um
    contrato errado de entrar, e uma rede que quebra não reprova nada.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        try:
            shown = path.relative_to(ROOT)
        except ValueError:
            shown = path
        fail(f"{shown}: não foi possível ler — {exc.strerror}")
        return None

    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        fail(f"{path.relative_to(ROOT)}: YAML inválido — {exc}")
        return None


def declared_names(contract: dict) -> tuple[dict[str, set[str]], set[str]]:
    """Conjuntos e seus campos, mais os parâmetros de geração."""
    datasets = {
        ds["name"]: {f["name"] for f in ds.get("fields", [])}
        for ds in contract.get("datasets", [])
    }
    parameters = {p["name"] for p in contract.get("parameters", [])}
    return datasets, parameters


def query_list(binding: dict) -> list[dict]:
    """As consultas de um binding, só as bem formadas.

    UMA porta de leitura, e não uma guarda repetida em cada leitor: três funções
    diferentes liam `binding["queries"]` e eu blindei duas, deixando a terceira
    estourar. Caminho gêmeo esquecido é o defeito que mais se repetiu neste
    validador — a resposta estrutural é não ter caminhos gêmeos.

    Quem precisa REPROVAR a forma malformada faz isso explicitamente
    (check_binding_queries); os demais leitores só querem a lista utilizável.
    """
    raw = binding.get("queries")
    if not isinstance(raw, list):
        return []

    return [q for q in raw if isinstance(q, dict)]


def check_template(doc_dir: Path, contract: dict) -> None:
    """A salvaguarda: template e contrato não podem divergir.

    Um campo que o template posiciona e o contrato não declara pede um dado que
    ninguém definiu, e o cliente não tem onde amarrá-lo — a célula sai vazia num
    arquivo que parece completo. O caminho inverso é mais brando: um campo
    declarado que nenhum template usa é provavelmente contrato adiantado, então
    avisa em vez de reprovar.
    """
    template = doc_dir / "template.tpl"
    if not template.exists():
        fail(f"{doc_dir.relative_to(ROOT)}: falta template.tpl")
        return

    body = template.read_text(encoding="utf-8")
    body = re.sub(r"\{#.*?#\}", "", body, flags=re.DOTALL)  # comentários não contam

    datasets, parameters = declared_names(contract)
    children = {
        ds["name"]: ds.get("childOf", {}).get("dataset")
        for ds in contract.get("datasets", [])
        if ds.get("childOf")
    }
    # Multimapa, não dict: `dict(findall(...))` guardaria só a ÚLTIMA ocorrência de
    # cada nome de iterador, e dois `for r in ...` em blocos irmãos — comum — passariam
    # a resolver ambos pelo último iterável, aprovando ou reprovando a referência
    # errada em silêncio.
    loops: dict[str, list[str]] = {}
    for head, iterable in re.findall(r"\{%-?\s*for\s+(\w+)\s+in\s+([\w.]+)", body):
        loops.setdefault(head, []).append(iterable)

    def dataset_of(head: str, depth: int = 0) -> str | None:
        """Resolve um iterador até o conjunto que ele percorre.

        Um conjunto childOf é alcançado como lista aninhada na linha do pai
        (`{% for d in r.operacoesDiarias %}`), então o iterável pode ser
        `<iterador-pai>.<conjunto-filho>` — e o filho só é legítimo se o contrato
        declara exatamente essa filiação. Um `.filho` sobre o pai errado é um
        conjunto que o render nunca vai popular, e a seção sai vazia num arquivo
        que parece completo.
        """
        if depth > 8 or head not in loops:
            return head if head in datasets else None

        # Um nome de iterador pode ser reusado; aceita se QUALQUER um dos iteráveis
        # resolver, para não reprovar um template legítimo por homonímia.
        for iterable in loops[head]:
            if "." not in iterable:
                if iterable in datasets:
                    return iterable
                continue

            parent_iter, child = iterable.split(".", 1)
            parent_ds = dataset_of(parent_iter, depth + 1)

            if child in children and children[child] == parent_ds:
                return child

        return None

    refs = set(re.findall(r"\{\{\s*([A-Za-z_]\w*)\.(\w+)", body))

    placed: set[tuple[str, str]] = set()
    for head, field in sorted(refs):
        if head == "system":
            if field not in parameters:
                fail(
                    f"{doc_dir.relative_to(ROOT)}: template usa system.{field}, "
                    f"que o contrato não declara em parameters"
                )
            continue

        dataset = dataset_of(head)
        if dataset is None:
            fail(
                f"{doc_dir.relative_to(ROOT)}: template lê {head}.{field}, e "
                f"'{head}' não resolve para nenhum conjunto do contrato "
                f"(loop aninhado só alcança um conjunto childOf do pai certo)"
            )
            continue

        if field not in datasets[dataset]:
            fail(
                f"{doc_dir.relative_to(ROOT)}: template usa {dataset}.{field}, "
                f"que o contrato não declara"
            )
            continue

        placed.add((dataset, field))

    for dataset, fields in datasets.items():
        for field in sorted(fields):
            if (dataset, field) not in placed:
                warn(
                    f"{doc_dir.relative_to(ROOT)}: {dataset}.{field} é declarado no "
                    f"contrato e nenhum template o posiciona"
                )


def check_formatting_not_duplicated(doc_dir: Path) -> None:
    """Formato é propriedade do campo, então mora no contrato — nunca nos dois.

    A mesma decisão em dois lugares pode divergir, e não existe árbitro para dizer
    qual vence: o arquivo sai errado com as duas conferências passando.
    """
    template = doc_dir / "template.tpl"
    if not template.exists():
        return

    body = re.sub(r"\{#.*?#\}", "", template.read_text(encoding="utf-8"), flags=re.DOTALL)

    for filter_name in ("decimal", "cosif_signed", "strip_zeros", "floatformat"):
        if re.search(rf"\|\s*{filter_name}\b", body):
            fail(
                f"{doc_dir.relative_to(ROOT)}: template aplica |{filter_name}. "
                f"Formato e sinal são propriedades do campo e pertencem ao "
                f"contrato; o template apenas posiciona"
            )


EXTRACTION_KEYS = {
    "aggregation": "agregação depende da forma da origem",
    "aggregate": "agregação depende da forma da origem",
    "measure": "medida é cálculo sobre a origem",
    "accumulation": "acumulação depende do que a origem entrega",
    "accumulate": "acumulação depende do que a origem entrega",
    "statedIn": "reexpressão é transformação sobre a origem",
    "dataSource": "fonte de dados é do cliente",
    "table": "tabela é do cliente",
    "column": "coluna é do cliente",
    "signColumn": "a coluna de sinal é do cliente",
}


def check_no_extraction_in_contract(doc_dir: Path, contract: dict) -> None:
    """Regra de EXTRAÇÃO não pode voltar para o contrato.

    O teste que separa as duas: a resposta muda de cliente para cliente? Se muda,
    é binding. Um cliente que já mantém tabela de saldos por rubrica não acumula
    nada — lê — e o contrato dos dois é o mesmo. Uma regra de extração aqui
    congelaria a forma da origem de UM cliente dentro de um arquivo que serve
    todos, e o próximo cliente com origem diferente não teria como usar o
    documento.
    """

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in EXTRACTION_KEYS:
                    fail(
                        f"{doc_dir.relative_to(ROOT)}: contrato usa '{key}' em "
                        f"{path or '<raiz>'} — {EXTRACTION_KEYS[key]}, então "
                        f"pertence ao binding"
                    )
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")

    walk(contract, "")


def check_binding_example(doc_dir: Path, contract: dict) -> None:
    """O exemplo de binding tem de resolver todo campo que o contrato declara.

    Ele orienta o cliente, então um exemplo incompleto ensina errado. Também
    confere que campo resolvido por consulta nomeia uma consulta que existe: um
    nome trocado renderiza célula vazia num arquivo que parece completo.
    """
    example = doc_dir / "binding.example.yaml"
    if not example.exists():
        warn(f"{doc_dir.relative_to(ROOT)}: sem binding.example.yaml para orientar o cliente")
        return

    binding = load(example)
    if binding is None:
        return

    if binding.get("contract") != contract.get("metadata", {}).get("id"):
        fail(
            f"{doc_dir.relative_to(ROOT)}: binding.example aponta para "
            f"'{binding.get('contract')}', não para este contrato"
        )

    check_binding_queries(doc_dir, binding)
    check_parent_match(doc_dir, contract, binding)
    check_column_survival(doc_dir, binding)

    queries = {q.get("name") for q in query_list(binding)}
    declared, _ = declared_names(contract)
    bound = binding.get("datasets", {})

    # Um campo OBRIGATÓRIO resolvido por `manual` sem valor é um regulatório saindo a
    # que faltam dados obrigatórios. A regra tem de ser EXECUTÁVEL: dizer em
    # comentário que "o motor deve bloquear" não bloqueia nada — era o que este
    # repositório fazia.
    #
    # Um binding pode declarar-se `generatable: false` — o caso de um exemplo que
    # exercita o formato antes de a fonte existir. Aí a incompletude tem de ser
    # ENUMERADA (incompleteFields) e justificada (incompleteReason). Sem essa
    # declaração, manual pendente em campo obrigatório REPROVA.
    required_by_dataset = {
        ds["name"]: {f["name"] for f in ds.get("fields", []) if f.get("required") is True}
        for ds in contract.get("datasets", [])
    }
    contract_row_sets = {ds["name"]: ds.get("rowSet") for ds in contract.get("datasets", [])}
    generatable = binding.get("generatable", True)

    # Um override só LIMPA a pendência se trouxer VALOR. Aceitar
    # `manualOverrides: [{field: x}]` sem valor reabria exatamente o furo que a regra
    # de manual pendente fechou, uma camada abaixo: o campo saía de `blocking` e o
    # arquivo seguia sem o dado obrigatório.
    overrides: set[str] = set()
    for i, override in enumerate(binding.get("manualOverrides") or []):
        if not isinstance(override, dict):
            fail(f"{doc_dir.relative_to(ROOT)}: manualOverrides[{i}] não é um mapa")
            continue

        field_ref = override.get("field")
        if not isinstance(field_ref, str) or not field_ref.strip():
            fail(f"{doc_dir.relative_to(ROOT)}: manualOverrides[{i}] não nomeia um `field`")
            continue

        value = override.get("value")
        if value is None or (isinstance(value, str) and not value.strip()):
            fail(
                f"{doc_dir.relative_to(ROOT)}: manualOverrides de '{field_ref}' não traz "
                f"`value` — um override sem valor não preenche o campo e não pode "
                f"dispensar a pendência"
            )
            continue

        overrides.add(field_ref)

    # incompleteFields tem de ser lista de nomes: um aninhamento acidental
    # (`[[campo]]`) fazia set() estourar em vez de reprovar.
    raw_incomplete = binding.get("incompleteFields") or []
    declared_incomplete: set[str] = set()
    if not isinstance(raw_incomplete, list):
        fail(f"{doc_dir.relative_to(ROOT)}: `incompleteFields` não é uma lista")
    else:
        for i, item in enumerate(raw_incomplete):
            if not isinstance(item, str) or not item.strip():
                fail(
                    f"{doc_dir.relative_to(ROOT)}: incompleteFields[{i}] não é um nome de "
                    f"campo: {item!r}"
                )
                continue
            declared_incomplete.add(item)

    pending: set[str] = set()

    if generatable is False and not binding.get("incompleteReason"):
        fail(
            f"{doc_dir.relative_to(ROOT)}: binding declara generatable: false sem "
            f"`incompleteReason` — a incompletude precisa ser justificada"
        )

    for dataset, fields in declared.items():
        entry = bound.get(dataset)
        if entry is None:
            fail(f"{doc_dir.relative_to(ROOT)}: binding.example não resolve o conjunto '{dataset}'")
            continue

        raw_from = entry.get("from")
        if raw_from is not None and not isinstance(raw_from, dict):
            fail(
                f"{doc_dir.relative_to(ROOT)}: o `from` do conjunto '{dataset}' não é um "
                f"mapa: {raw_from!r}"
            )
            raw_from = None

        source = (raw_from or {}).get("query")
        if source is not None and source not in queries:
            fail(
                f"{doc_dir.relative_to(ROOT)}: conjunto '{dataset}' vem da consulta "
                f"'{source}', que não está declarada em queries"
            )

        resolved = entry.get("fields", {})
        for field in sorted(fields):
            spec = resolved.get(field)
            if spec is None:
                # Um campo INCONDICIONALMENTE obrigatório sem origem é erro: toda
                # geração falharia. Um condicional/opcional pode legitimamente não se
                # resolver quando o binding torna a condição impossível (marca com
                # terminalProprio fixo em 0) — mas fica em aviso, para o exemplo ser
                # omisso por decisão e não por esquecimento.
                if field in required_by_dataset.get(dataset, set()):
                    fail(f"{doc_dir.relative_to(ROOT)}: binding.example não resolve {dataset}.{field}, que é obrigatório incondicional")
                else:
                    warn(f"{doc_dir.relative_to(ROOT)}: binding.example não resolve o condicional {dataset}.{field} — confirme que a condição nunca vale neste binding")
                continue

            valid = {"query", "constant", "parameter", "manual", "rowSet"}

            # byRowClass: um campo cuja origem depende da CLASSE da linha (no 4111, o
            # saldoDia vem da consulta para estoque e é manual para fluxo). Cada caso
            # é uma origem própria, e todo caso precisa declarar `when` e um `from`
            # válido — assim nenhuma linha fica sem origem em silêncio, que é
            # justamente como um regulatório sai a que faltam contas obrigatórias.
            cases = spec.get("byRowClass")
            if isinstance(cases, list):
                if not cases:
                    fail(f"{doc_dir.relative_to(ROOT)}: {dataset}.{field}.byRowClass está vazio")
                for i, case in enumerate(cases):
                    if not case.get("when"):
                        fail(f"{doc_dir.relative_to(ROOT)}: {dataset}.{field}.byRowClass[{i}] sem `when`")
                    if case.get("from") not in valid:
                        fail(
                            f"{doc_dir.relative_to(ROOT)}: {dataset}.{field}.byRowClass[{i}] "
                            f"resolve por {case.get('from')!r}; use {', '.join(sorted(valid))}"
                        )
                    # A MESMA precondição do caminho direto: `rowSet` só significa
                    # algo se o conjunto declarar rowSet no contrato. Aplicá-la num
                    # caminho e não no outro é o furo de sempre — a origem existe em
                    # dois lugares, a conferência tem de existir nos dois.
                    if case.get("from") == "rowSet" and not contract_row_sets.get(dataset):
                        fail(
                            f"{doc_dir.relative_to(ROOT)}: {dataset}.{field}.byRowClass[{i}] "
                            f"resolve por rowSet, mas o contrato não declara rowSet no "
                            f"conjunto '{dataset}'"
                        )

                    if case.get("from") == "manual" and case.get("value") is None:
                        if not case.get("pendingReason"):
                            fail(
                                f"{doc_dir.relative_to(ROOT)}: {dataset}.{field}.byRowClass[{i}] "
                                f"é manual sem valor e sem `pendingReason`"
                            )
                        if field in required_by_dataset.get(dataset, set()):
                            pending.add(f"{dataset}.{field}")
                continue

            how = spec.get("from")
            # rowSet: o valor da linha vem do conjunto fechado que o catálogo
            # declara (contas.yaml), não da consulta — é a origem própria de um
            # documento cujo conjunto de linhas é do catálogo e não do cliente.
            if how not in valid:
                fail(
                    f"{doc_dir.relative_to(ROOT)}: {dataset}.{field} resolve por "
                    f"{how!r}; use query, constant, parameter, manual, rowSet ou byRowClass"
                )

            # `rowSet` só significa algo se o CONJUNTO declarar rowSet no contrato:
            # aceitar o nome da origem sem conferir a precondição deixa o campo
            # apontando para um conjunto de linhas que não existe.
            if how == "rowSet" and not contract_row_sets.get(dataset):
                fail(
                    f"{doc_dir.relative_to(ROOT)}: {dataset}.{field} resolve por rowSet, "
                    f"mas o contrato não declara rowSet no conjunto '{dataset}'"
                )

            if how == "manual" and spec.get("value") is None:
                if not spec.get("pendingReason"):
                    fail(
                        f"{doc_dir.relative_to(ROOT)}: {dataset}.{field} é manual sem "
                        f"valor e sem `pendingReason`"
                    )
                if field in required_by_dataset.get(dataset, set()):
                    pending.add(f"{dataset}.{field}")

    _verdict_on_pending(doc_dir, generatable, declared_incomplete, overrides, pending)


def check_closed_account_set(doc_dir: Path, contract: dict) -> None:
    """Um documento de conjunto FECHADO declara suas linhas num arquivo do catálogo,
    e esse arquivo tem de existir e bater com o contrato.

    Diferente do balancete, onde as linhas são do cliente, aqui elas são do catálogo
    (contas.yaml). Um arquivo ausente é um documento que sai VAZIO em silêncio; um
    código no conjunto que não bate com o pattern do campo é a deriva 8-vs-10 dígitos
    entrando pela porta dos fundos.
    """
    set_path = contract.get("metadata", {}).get("sourceOfTruth", {}).get("accountSet")

    row_datasets = [ds for ds in contract.get("datasets", []) if ds.get("rowSet")]

    if not set_path and not row_datasets:
        return

    if set_path and not (doc_dir / set_path).exists():
        fail(f"{doc_dir.relative_to(ROOT)}: metadata.accountSet cita {set_path}, que não existe")

    for ds in row_datasets:
        ref = ds["rowSet"].get("from")
        if not ref:
            fail(f"{doc_dir.relative_to(ROOT)}: {ds['name']}.rowSet não declara `from`")
            continue

        # rowSet sem accountSet: a consistência abaixo só roda quando o contrato
        # ANUNCIA o conjunto em metadata; sem isso a conferência se apaga e o
        # conjunto usado nunca é confrontado com o declarado. Um rowSet obriga o
        # accountSet.
        if not set_path:
            fail(
                f"{doc_dir.relative_to(ROOT)}: {ds['name']} tem rowSet mas o contrato "
                f"não declara metadata.sourceOfTruth.accountSet — o conjunto usado "
                f"precisa ser o anunciado"
            )

        # accountSet e rowSet.from têm de ser o MESMO conjunto: dois arquivos válidos
        # mas diferentes passariam cada um em sua conferência isolada enquanto o
        # binding resolve um conjunto e o contrato anuncia outro.
        if set_path and ref != set_path:
            fail(
                f"{doc_dir.relative_to(ROOT)}: {ds['name']}.rowSet.from é '{ref}' e "
                f"metadata.accountSet é '{set_path}' — o conjunto anunciado e o usado "
                f"têm de ser o mesmo arquivo"
            )

        ref_file = doc_dir / ref
        if not ref_file.exists():
            fail(f"{doc_dir.relative_to(ROOT)}: {ds['name']}.rowSet.from cita {ref}, que não existe")
            continue

        # Robustez de forma: um conjunto com raiz que não é mapa, `accounts` que não é
        # lista, ou uma linha que não é mapa faria os .get() abaixo estourarem em vez
        # de reprovar. Um validador que quebra com entrada malformada é pior que um
        # que reprova.
        loaded = load(ref_file)
        if not isinstance(loaded, dict):
            fail(f"{doc_dir.relative_to(ROOT)}: {ref} não é um mapa YAML na raiz")
            continue

        rows = loaded.get("accounts")
        if not isinstance(rows, list):
            fail(f"{doc_dir.relative_to(ROOT)}: {ref} não tem uma lista `accounts`")
            continue

        malformed = [r for r in rows if not isinstance(r, dict)]
        for r in malformed:
            fail(f"{doc_dir.relative_to(ROOT)}: {ref} tem uma conta que não é mapa: {r!r}")
        rows = [r for r in rows if isinstance(r, dict)]

        key = ds["rowSet"].get("key")
        key_field = next((f for f in ds.get("fields", []) if f["name"] == key), None)
        pattern = key_field.get("pattern") if key_field else None

        for r in rows:
            code = str(r.get("code", ""))

            # O código de dez dígitos é o mascarado sem pontuação. Conferir isso é o
            # que pega a transcrição manual errada — que já aconteceu (um código de
            # controle e os cinco de fluxo saíram trocados na primeira versão). Por
            # isso `masked` é OBRIGATÓRIO: sem ele o code não tem contra o que ser
            # conferido e a conta escapa exatamente da checagem que mais importa.
            masked = r.get("masked")
            if not masked:
                fail(
                    f"{doc_dir.relative_to(ROOT)}: em {ref}, a conta '{code}' não tem "
                    f"`masked` — o code fica sem a forma oficial contra a qual conferir"
                )
            elif code != re.sub(r"[.\-]", "", str(masked)):
                fail(
                    f"{doc_dir.relative_to(ROOT)}: em {ref}, code '{code}' não é o "
                    f"masked '{masked}' sem pontuação — transcrição do código diverge"
                )

            if pattern and not re.fullmatch(pattern, code):
                fail(
                    f"{doc_dir.relative_to(ROOT)}: conta '{code}' em {ref} não bate com o "
                    f"pattern de {ds['name']}.{key} — deriva de formato do código"
                )

        codes = [str(r.get("code")) for r in rows]
        for dup in {c for c in codes if codes.count(c) > 1}:
            fail(f"{doc_dir.relative_to(ROOT)}: conta '{dup}' duplicada em {ref}")



def _verdict_on_pending(doc_dir: Path, generatable, declared_incomplete, overrides, pending) -> None:
    """O veredito de gerabilidade: campo obrigatório manual sem valor bloqueia.

    É a regra que a prosa do binding descrevia e nada impunha.
    """
    blocking = {f for f in pending if f not in overrides}

    if generatable is False:
        for field in sorted(blocking - declared_incomplete):
            fail(
                f"{doc_dir.relative_to(ROOT)}: {field} é obrigatório e está manual sem "
                f"valor, mas não consta em `incompleteFields` — a incompletude precisa "
                f"ser enumerada, não vaga"
            )
        for field in sorted(declared_incomplete - blocking):
            fail(
                f"{doc_dir.relative_to(ROOT)}: `incompleteFields` lista {field}, que não "
                f"é campo obrigatório pendente — lista desatualizada"
            )
        return

    for field in sorted(blocking):
        fail(
            f"{doc_dir.relative_to(ROOT)}: {field} é obrigatório e resolve por manual sem "
            f"valor: este binding NÃO gera documento válido. Forneça o valor em "
            f"`manualOverrides`, ou declare `generatable: false` com `incompleteReason` e "
            f"`incompleteFields`"
        )


CONDITION_OPS = {"equals", "in", "notIn", "is"}


def check_structure(doc_dir: Path, contract: dict) -> None:
    """As construções estruturais do contrato apontam para coisas que existem.

    Cada uma nasceu de uma exigência real e cada referência quebrada tem um modo de
    falha silencioso próprio: um childOf para pai errado é uma seção que o render
    nunca popula; um refersTo para campo inexistente é integridade referencial que
    ninguém confere; um equalsSumOf órfão é uma reconciliação que diz sempre sim; e
    um requiredWhen sobre campo fantasma é uma condicional que nunca dispara — o
    campo vira opcional de fato num arquivo em que era obrigatório.
    """
    datasets, _ = declared_names(contract)
    by_name = {ds["name"]: ds for ds in contract.get("datasets", [])}

    for ds in contract.get("datasets", []):
        name = ds["name"]

        parent = ds.get("childOf", {}).get("dataset")
        if parent is not None and parent not in datasets:
            fail(f"{doc_dir.relative_to(ROOT)}: {name} é childOf de '{parent}', que não existe")

        for field in ds.get("fields", []):
            fname = field["name"]

            ref = field.get("refersTo")
            if ref:
                target = ref.get("dataset")
                if target not in datasets:
                    fail(f"{doc_dir.relative_to(ROOT)}: {name}.{fname} refersTo conjunto '{target}', que não existe")
                elif ref.get("field") not in datasets[target]:
                    fail(
                        f"{doc_dir.relative_to(ROOT)}: {name}.{fname} refersTo "
                        f"{target}.{ref.get('field')}, campo que não existe"
                    )

            sum_of = field.get("equalsSumOf")
            if sum_of:
                target = sum_of.get("dataset")
                target_ds = by_name.get(target)
                if target_ds is None:
                    fail(f"{doc_dir.relative_to(ROOT)}: {name}.{fname} equalsSumOf conjunto '{target}', que não existe")
                else:
                    if target_ds.get("childOf", {}).get("dataset") != name:
                        fail(
                            f"{doc_dir.relative_to(ROOT)}: {name}.{fname} equalsSumOf "
                            f"'{target}', que não é childOf de {name} — uma soma de "
                            f"não-filhos reconcilia coisa nenhuma"
                        )
                    if sum_of.get("field") not in datasets.get(target, set()):
                        fail(
                            f"{doc_dir.relative_to(ROOT)}: {name}.{fname} equalsSumOf "
                            f"{target}.{sum_of.get('field')}, campo que não existe"
                        )

            for kind in ("requiredWhen", "forbiddenWhen"):
                cond = field.get(kind)
                if not cond:
                    continue

                ops = set(cond) & CONDITION_OPS
                if len(ops) != 1:
                    fail(
                        f"{doc_dir.relative_to(ROOT)}: {name}.{fname} {kind} precisa de "
                        f"exatamente uma condição dentre {sorted(CONDITION_OPS)}"
                    )

                via = cond.get("via")
                if via is not None:
                    via_field = next((f for f in ds.get("fields", []) if f["name"] == via), None)
                    ref = (via_field or {}).get("refersTo")
                    if ref is None:
                        fail(
                            f"{doc_dir.relative_to(ROOT)}: {name}.{fname} {kind} usa "
                            f"via '{via}', que não é um campo com refersTo deste conjunto"
                        )
                    elif cond.get("field") not in datasets.get(ref.get("dataset"), set()):
                        fail(
                            f"{doc_dir.relative_to(ROOT)}: {name}.{fname} {kind} via "
                            f"{via} aponta para {ref.get('dataset')}.{cond.get('field')}, "
                            f"campo que não existe"
                        )
                elif cond.get("field") not in datasets[name]:
                    fail(
                        f"{doc_dir.relative_to(ROOT)}: {name}.{fname} {kind} condiciona "
                        f"em '{cond.get('field')}', campo que este conjunto não declara"
                    )


def check_binding_queries(doc_dir: Path, binding: dict) -> None:
    """Consultas compostas e joins apontam para consultas que existem.

    Um `from` para consulta inexistente, ou um join por nome trocado, não falha na
    escrita — falha na geração, do jeito silencioso: conjunto vazio, arquivo
    completo na aparência.
    """
    # Forma antes do uso: `queries` que não é lista, ou item que não é mapa, faria
    # todo `.get` abaixo estourar. A ferramenta é a rede que impede um contrato errado
    # de entrar; rede que quebra não reprova nada.
    raw_queries = binding.get("queries") or []
    if not isinstance(raw_queries, list):
        fail(f"{doc_dir.relative_to(ROOT)}: `queries` não é uma lista")
        return

    for index, query in enumerate(raw_queries):
        if not isinstance(query, dict):
            fail(f"{doc_dir.relative_to(ROOT)}: queries[{index}] não é um mapa")
            continue
        if not query.get("name"):
            fail(f"{doc_dir.relative_to(ROOT)}: consulta #{index + 1} não declara name")

    names = [q["name"] for q in query_list(binding) if q.get("name")]

    for duplicate in {n for n in names if names.count(n) > 1}:
        fail(f"{doc_dir.relative_to(ROOT)}: consulta '{duplicate}' declarada duas vezes")

    known = set(names)

    # Ciclo em `from`: produced_columns o detecta e responde "não sei", que
    # esconderia um binding quebrado atrás de uma conferência que se cala. Uma
    # varredura só, FORA do laço: dentro dele o mapa era reconstruído por consulta e
    # um ciclo de k consultas saía reportado k vezes, uma por rotação da cadeia.
    by_name = {q["name"]: q for q in query_list(binding) if q.get("name")}
    reported: set[frozenset[str]] = set()

    for start in by_name:
        chain: list[str] = []
        cursor = start

        while cursor in by_name:
            if cursor in chain:
                cycle = frozenset(chain[chain.index(cursor):])
                if cycle not in reported:
                    reported.add(cycle)
                    fail(
                        f"{doc_dir.relative_to(ROOT)}: consultas em ciclo por `from`: "
                        f"{' -> '.join([*chain, cursor])}"
                    )
                break

            chain.append(cursor)
            cursor = by_name[cursor].get("from")

    for query in query_list(binding):
        qname = query.get("name", "<sem nome>")

        base = query.get("from")
        if base is not None and base not in known:
            fail(f"{doc_dir.relative_to(ROOT)}: consulta '{qname}' compõe sobre '{base}', que não existe")

        # Toda consulta precisa de ANCORAGEM: ou uma fonte de dados própria, ou outra
        # consulta sobre a qual compor. Sem nenhuma das duas, ela não extrai de lugar
        # nenhum e o conjunto que dela depende sai vazio.
        if base is None and not query.get("dataSource"):
            fail(
                f"{doc_dir.relative_to(ROOT)}: consulta '{qname}' não tem nem dataSource "
                f"nem from — não extrai de lugar nenhum"
            )

        for join_index, join in enumerate(query.get("join") or []):
            if not isinstance(join, dict):
                fail(f"{doc_dir.relative_to(ROOT)}: join[{join_index}] de '{qname}' não é um mapa")
                continue

            target_query = join.get("query")
            if target_query is not None and target_query not in known:
                fail(f"{doc_dir.relative_to(ROOT)}: consulta '{qname}' junta com '{target_query}', que não existe")

            if target_query is None and not join.get("table"):
                fail(f"{doc_dir.relative_to(ROOT)}: join de '{qname}' não nomeia nem table nem query")

            # `match`, não `on`: YAML 1.1 lê `on` como booleano — inclusive como
            # CHAVE — e a cláusula sumiria no parse sem erro nenhum.
            if not join.get("match"):
                fail(f"{doc_dir.relative_to(ROOT)}: join de '{qname}' sem cláusula match")
            # YAML 1.1 converte a chave `on` no booleano True, então `"on" in join`
            # nunca é verdadeiro. Testar a PRESENÇA da chave True e não o valor: um
            # `on:` sem valor produziria True->None e escaparia de um teste por valor.
            if True in join or "on" in join:
                fail(
                    f"{doc_dir.relative_to(ROOT)}: join de '{qname}' usa a chave 'on', "
                    f"que YAML 1.1 lê como booleano — use 'match'"
                )


def check_template_parses(doc_dir: Path) -> None:
    """Regras do MOTOR de template que uma leitura por regex não pega.

    Existe porque um template pode passar em toda conferência desta ferramenta e
    ser irreceptível pelo motor. Aconteceu: o pongo2 não aceita salto de linha
    dentro de `{# ... #}`, e os dois primeiros templates deste repositório foram
    commitados com cabeçalho multi-linha — ilegíveis pelo renderer, com o CI verde,
    porque a conferência apenas REMOVIA os comentários por regex sem nunca parsear.

    Não é um parser: é a lista das regras do motor que já nos morderam. Cada nova
    entra aqui quando morder.
    """
    template = doc_dir / "template.tpl"
    if not template.exists():
        return

    body = template.read_text(encoding="utf-8")

    for match in re.finditer(r"\{#.*?#\}", body, flags=re.DOTALL):
        if "\n" in match.group(0):
            line = body[: match.start()].count("\n") + 1
            fail(
                f"{doc_dir.relative_to(ROOT)}: comentário multi-linha na linha {line} — "
                f"o pongo2 recusa salto de linha dentro de {{# #}} "
                f'("Newline not permitted in a single-line comment"). '
                f"Use um comentário por linha."
            )

    # Um `{#` sem fechamento leva o resto do arquivo embora, silenciosamente.
    if body.count("{#") != body.count("#}"):
        fail(
            f"{doc_dir.relative_to(ROOT)}: comentários desbalanceados "
            f"({body.count('{#')} aberturas, {body.count('#}')} fechamentos)"
        )


def check_parent_match(doc_dir: Path, contract: dict, binding: dict) -> None:
    """Todo conjunto childOf declara COM QUE COLUNA se aninha sob o pai.

    Sem isso o motor tem linhas filhas soltas e nenhum critério para colocá-las sob
    a linha certa do pai: o arquivo sai com a hierarquia embaralhada, cada bloco
    somando o que não é dele — e a adjacência que o leiaute exige é impossível de
    produzir. O exemplo original tinha três consultas planas sem chave de ligação,
    e nenhuma conferência daqui reclamou.
    """
    declared, _ = declared_names(contract)
    bound = binding.get("datasets", {})

    for ds in contract.get("datasets", []):
        parent = ds.get("childOf", {}).get("dataset")
        if parent is None:
            continue

        name = ds["name"]
        entry = bound.get(name)
        if entry is None:
            continue

        parent_match = entry.get("parentMatch")
        if not parent_match:
            fail(
                f"{doc_dir.relative_to(ROOT)}: {name} é childOf de {parent} e o "
                f"binding não declara parentMatch — as linhas filhas não têm como "
                f"ser aninhadas sob a linha certa do pai"
            )
            continue

        for parent_field in parent_match:
            if parent_field not in declared.get(parent, set()):
                fail(
                    f"{doc_dir.relative_to(ROOT)}: {name}.parentMatch aninha por "
                    f"'{parent_field}', que o conjunto pai {parent} não declara"
                )


def produced_columns(
    query: dict,
    queries: dict[str, dict],
    seen: frozenset[str] = frozenset(),
) -> set[str] | None:
    """As colunas que uma consulta ENTREGA a quem se apoia nela.

    Resolve a cadeia de `from` inteira, e não um nível. Uma consulta SEM agregação
    no meio do caminho repassa a origem: parar nela devolvia None e apagava a
    conferência de tudo o que viesse depois — uma coluna descartada três consultas
    atrás passava sem sinal.

    Uma consulta AGREGADA entrega exatamente o groupBy mais as medidas nomeadas
    mais as derivadas, independentemente do que a base entregue: agregar é projetar,
    então o conjunto é conhecido mesmo sobre origem desconhecida.

    Responde None — "não sei, não confira" — quando a raiz é uma tabela crua, cujo
    esquema este repositório não conhece, ou quando um join reintroduz esquema cru.
    Conservador de propósito: um None a mais deixa passar um erro, um falso positivo
    reprova um binding correto e ensina a ignorar a ferramenta.
    """
    name = query.get("name")

    # Proteção de ciclo: um `from` circular não tem conjunto de colunas.
    if name and name in seen:
        return None

    if name:
        seen = seen | {name}

    derived = {d["as"] for d in query.get("derive") or [] if d.get("as")}

    aggregate = query.get("aggregate")
    if aggregate:
        columns = set(aggregate.get("groupBy") or [])
        columns |= {m["as"] for m in aggregate.get("measures") or [] if m.get("as")}

        return columns | derived

    base_name = query.get("from")
    if base_name is None or base_name not in queries:
        return None

    base = produced_columns(queries[base_name], queries, seen)
    if base is None:
        return None

    # Um join que traz TABELA crua reintroduz esquema desconhecido; um que traz
    # outra consulta soma o que ela entrega.
    for join in query.get("join") or []:
        if join.get("table"):
            return None

        joined = queries.get(join.get("query"))
        if joined is None:
            return None

        joined_columns = produced_columns(joined, queries, seen)
        if joined_columns is None:
            return None

        base = base | joined_columns

    return base | derived


def condition_fields(node: object) -> tuple[set[str], list[object]]:
    """Todo `field` de uma árvore de condições, mais o que não é nome de campo.

    Devolve os malformados em vez de estourar: `field: [valor]` fazia `set.add`
    levantar TypeError e a ferramenta MORRIA no meio da conferência, em vez de
    reprovar a condição e seguir. Um validador que quebra com entrada malformada é
    pior que um que reprova — quem escreveu não descobre o que estava errado.
    """
    fields: set[str] = set()
    malformed: list[object] = []

    if isinstance(node, dict):
        if "field" in node:
            if isinstance(node["field"], str):
                fields.add(node["field"])
            else:
                malformed.append(node["field"])

        for value in node.values():
            nested_fields, nested_malformed = condition_fields(value)
            fields |= nested_fields
            malformed += nested_malformed
    elif isinstance(node, list):
        for value in node:
            nested_fields, nested_malformed = condition_fields(value)
            fields |= nested_fields
            malformed += nested_malformed

    return fields, malformed


def check_column_survival(doc_dir: Path, binding: dict) -> None:
    """Uma coluna referenciada tem de sobreviver até o ponto onde é usada.

    Esta é a conferência que faltava, e a ausência dela custou duas rodadas de
    revisão na MESMA classe de erro: primeiro o having comparava uma coluna com
    outro nome, depois comparava o nome certo de uma coluna que duas agregações já
    haviam descartado. Nos dois casos o modo de falha é o mesmo e é silencioso — sem
    discriminador, ou a consulta quebra, ou todas as linhas passam e o arquivo sai
    com recebedor que devia estar fora.

    Uma coluna só sobrevive a um groupBy se entrar nele. A regra estava escrita em
    comentário no exemplo e violada duas linhas abaixo; agora é executável.
    """
    # Mesma guarda de forma de check_binding_queries: esta função lê as MESMAS
    # estruturas, e blindar um leitor e não o outro é o caminho gêmeo esquecido —
    # o padrão que mais me pegou neste validador.
    queries = {q["name"]: q for q in query_list(binding) if q.get("name")}

    for name, query in queries.items():
        base_name = query.get("from")
        available = (
            produced_columns(queries[base_name], queries)
            if base_name in queries
            else None
        )

        if available is not None:
            aggregate = query.get("aggregate", {}) or {}
            used = set(aggregate.get("groupBy", []) or [])
            used |= {m["of"] for m in aggregate.get("measures", []) or [] if m.get("of")}

            for column in sorted(used - available):
                fail(
                    f"{doc_dir.relative_to(ROOT)}: consulta '{name}' usa a coluna "
                    f"'{column}', que '{base_name}' não entrega — uma coluna só "
                    f"sobrevive ao groupBy se entrar nele"
                )

        having_fields, malformed = condition_fields(query.get("having", []))

        for value in malformed:
            fail(
                f"{doc_dir.relative_to(ROOT)}: o having de '{name}' tem um `field` "
                f"que não é nome de coluna: {value!r}"
            )

        own = produced_columns(query, queries)
        if own is not None:
            for column in sorted(having_fields - own):
                fail(
                    f"{doc_dir.relative_to(ROOT)}: o having de '{name}' compara "
                    f"'{column}', que a própria consulta não entrega após agregar"
                )

    for name, entry in (binding.get("datasets") or {}).items():
        if not isinstance(entry, dict):
            continue

        raw_from = entry.get("from")
        if not isinstance(raw_from, dict):
            continue

        source = raw_from.get("query")
        if source not in queries:
            continue

        available = produced_columns(queries[source], queries)
        if available is None:
            continue

        # Só as colunas que a CONSULTA deve entregar. Um campo resolvido por
        # `rowSet` vem do conjunto fechado do catálogo, e um `byRowClass` tem a
        # origem por caso — conferir esses contra o que a consulta entrega acusaria
        # falso positivo e ensinaria a ignorar a ferramenta.
        used = {
            f["column"]
            for f in (entry.get("fields") or {}).values()
            if isinstance(f, dict) and f.get("column") and f.get("from") == "query"
        }
        for f in (entry.get("fields") or {}).values():
            if not isinstance(f, dict):
                continue
            for case in f.get("byRowClass") or []:
                if isinstance(case, dict) and case.get("from") == "query" and case.get("column"):
                    used.add(case["column"])
        used |= set((entry.get("parentMatch") or {}).values())

        for column in sorted(used - available):
            fail(
                f"{doc_dir.relative_to(ROOT)}: conjunto '{name}' mapeia a coluna "
                f"'{column}', que a consulta '{source}' não entrega"
            )


def check_references(doc_dir: Path, contract: dict) -> None:
    """Todo arquivo que o contrato cita tem de existir."""
    schema = contract.get("metadata", {}).get("sourceOfTruth", {}).get("schema")
    if schema and not (doc_dir / schema).exists():
        fail(f"{doc_dir.relative_to(ROOT)}: contrato cita {schema}, que não existe")

    example = doc_dir / "binding.example.yaml"
    if example.exists():
        binding = load(example) or {}
        for query in query_list(binding):
            for measure in (query.get("aggregate") or {}).get("measures") or []:
                lookup = measure.get("statedIn", {}).get("lookup")
                if lookup and not (doc_dir / lookup).exists():
                    fail(
                        f"{doc_dir.relative_to(ROOT)}: consulta '{query.get('name')}' "
                        f"cita {lookup}, que não existe"
                    )

    # O catálogo publica contrato, template e — quando o documento precisa —
    # tabela de código do REGULADOR. Não publica tabela sobre o plano de contas
    # do cliente: a natureza contábil é propriedade do plano de contas dele, e
    # uma tabela nossa seria uma segunda fonte de verdade que ninguém reconcilia.
    for stray in doc_dir.glob("*nature*.yaml"):
        fail(
            f"{doc_dir.relative_to(ROOT)}: {stray.name} descreve o plano de contas "
            f"do cliente, que é dado dele — declare no binding, não no catálogo"
        )


def check_rules(doc_dir: Path, contract: dict) -> None:
    """Severidade é obrigatória e o alvo tem de existir.

    Uma regra sem severidade não diz se bloqueia a geração ou apenas avisa, e essa
    é a diferença entre travar a operação do cliente numa véspera de prazo e
    entregar arquivo errado.
    """
    datasets, parameters = declared_names(contract)
    seen: set[str] = set()

    for rule in contract.get("rules", []):
        rule_id = rule.get("id", "<sem id>")

        if rule_id in seen:
            fail(f"{doc_dir.relative_to(ROOT)}: regra '{rule_id}' duplicada")
        seen.add(rule_id)

        if rule.get("severity") not in {"error", "warning", "info"}:
            fail(
                f"{doc_dir.relative_to(ROOT)}: regra '{rule_id}' tem severity "
                f"{rule.get('severity')!r}; use error, warning ou info"
            )

        target = rule.get("appliesTo", "")
        head = target.split(".", 1)[0]
        if head and head not in datasets and head != "parameters":
            fail(
                f"{doc_dir.relative_to(ROOT)}: regra '{rule_id}' aponta para "
                f"'{target}', que o contrato não declara"
            )


def check_index(catalog: dict, contracts: dict[str, dict]) -> None:
    """O índice repete o metadata do contrato, então pode divergir dele.

    A duplicação é deliberada — o índice existe para filtrar sem baixar tudo — mas
    divergir significa mostrar ao cliente um documento que não é o que ele recebe.
    """
    mirrored = ("country", "regulator", "document", "title", "version", "periodicity")

    for entry in catalog.get("documents", []):
        doc_id = entry.get("id")
        contract = contracts.get(doc_id)

        if contract is None:
            fail(f"catalog.yaml: '{doc_id}' não tem contrato em {entry.get('path')}")
            continue

        metadata = contract.get("metadata", {})
        for key in mirrored:
            if entry.get(key) != metadata.get(key):
                fail(
                    f"catalog.yaml: '{doc_id}'.{key} = {entry.get(key)!r} diverge do "
                    f"contrato ({metadata.get(key)!r}); o contrato é a fonte"
                )

        if entry.get("appliesTo") != metadata.get("appliesTo"):
            fail(f"catalog.yaml: '{doc_id}'.appliesTo diverge do contrato")

    indexed = {e.get("id") for e in catalog.get("documents", [])}
    for doc_id in contracts:
        if doc_id not in indexed:
            fail(f"catalog.yaml: contrato '{doc_id}' existe e não está no índice")


def main() -> int:
    FAILURES.clear()
    WARNINGS.clear()

    catalog = load(ROOT / "catalog.yaml")
    if catalog is None:
        print("\n".join(FAILURES), file=sys.stderr)
        return 1

    contracts: dict[str, dict] = {}

    for path in sorted(ROOT.glob("*/*/*/contract.yaml")):
        contract = load(path)
        if contract is None:
            continue

        doc_dir = path.parent
        doc_id = contract.get("metadata", {}).get("id")

        if not doc_id:
            fail(f"{path.relative_to(ROOT)}: metadata.id ausente")
            continue

        contracts[doc_id] = contract
        check_template(doc_dir, contract)
        check_formatting_not_duplicated(doc_dir)
        check_no_extraction_in_contract(doc_dir, contract)
        check_closed_account_set(doc_dir, contract)
        check_structure(doc_dir, contract)
        check_template_parses(doc_dir)
        check_binding_example(doc_dir, contract)
        check_references(doc_dir, contract)
        check_rules(doc_dir, contract)

    check_index(catalog, contracts)

    for warning in WARNINGS:
        print(f"aviso: {warning}")

    if FAILURES:
        print()
        for failure in FAILURES:
            print(f"erro: {failure}", file=sys.stderr)
        print(f"\n{len(FAILURES)} problema(s).", file=sys.stderr)
        return 1

    print(f"{len(contracts)} documento(s) conferido(s), nenhum problema.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
