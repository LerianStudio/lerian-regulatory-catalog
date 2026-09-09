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
    """Registra uma reprovação, uma vez.

    Repetição é descartada porque toda mensagem daqui NOMEIA seu ponto — o arquivo, o
    conjunto, o campo —, então duas mensagens idênticas são o mesmo problema contado
    duas vezes, nunca dois problemas. E contar duas vezes acontece o tempo todo agora
    que as leituras passam por portas: uma porta chamada por oito leitores reprova
    oito vezes, e as sete cópias empurram para fora da tela as outras reprovações,
    que são justamente o que o curador precisa ver.
    """
    if msg not in FAILURES:
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


def sequence_at(where: str, value: object, requirement: str) -> list:
    """Lê um valor que TEM de ser uma lista, reprovando em vez de estourar.

    A terceira porta, e ela fecha o último jeito de YAML surpreender um leitor:
    `datasets:` sem nada embaixo não é lista vazia, é `null` — e `for ds in None`
    estoura. Vale para os quatro lugares onde um contrato tem coleção: datasets,
    fields, parameters e rules.

    Ausente e nulo são a mesma resposta, LISTA VAZIA, porque é o que
    `.get(k, [])` já queria dizer: quem exige que a coleção exista é a conferência
    de conteúdo, não o leitor. Já um valor que existe e não é lista é recusa: o
    curador escreveu alguma coisa ali, e ignorá-la seria conferir um contrato
    diferente do que ele escreveu.
    """
    if value is None:
        return []

    if isinstance(value, list):
        return value

    fail(f"{where} é {value!r}; {requirement}")

    return []


def parameters_of(contract: dict) -> list:
    """Os parâmetros de geração declarados, como lista."""
    return sequence_at("parameters", contract.get("parameters"),
                       "parameters é a lista dos parâmetros com que o documento é gerado")


def rules_of(contract: dict) -> list:
    """As regras declaradas, como lista."""
    return sequence_at("rules", contract.get("rules"),
                       "rules é a lista das conferências sobre o arquivo pronto")


def source_of_truth(contract: dict, key: str) -> str | None:
    """O arquivo que o contrato ANUNCIA sob metadata.sourceOfTruth.

    Porta porque `metadata` e `sourceOfTruth` eram encadeados com `.get({}).get()`
    em dois lugares, e esse encadeamento só funciona quando cada degrau é mapeamento:
    `sourceOfTruth: []` levantava AttributeError, e um caminho que não é texto
    chegava inteiro ao operador `/` de Path.
    """
    metadata = contract.get("metadata")
    if not isinstance(metadata, dict):
        return None

    declared = metadata.get("sourceOfTruth")
    if not isinstance(declared, dict):
        return None

    value = declared.get(key)

    return value if isinstance(value, str) and value else None


def child_parent(ds: dict) -> str | None:
    """O conjunto de que este pende, quando ele pende de algum.

    Uma porta, e deliberadamente sem dizer quantos leitores ela serve. Escrevi
    "dois" aqui e estava errado; corrigi para "três" e estava errado de novo; eram
    quatro. Todos tomavam `.get("dataset")` na fé de que `childOf` fosse um
    mapeamento, e `childOf: []` estourava em todos.

    Contar de cabeça é o que falha. Um número no comentário envelhece no primeiro
    leitor novo e ainda dá a quem lê a impressão de que alguém conferiu — a porta
    existe para que ninguém precise contar.
    """
    childof = ds.get("childOf")
    if childof is None:
        return None

    if not isinstance(childof, dict):
        return None

    parent = childof.get("dataset")

    return parent if isinstance(parent, str) and parent else None


def required_text(where: str, value: object, requirement: str) -> str | None:
    """Lê um valor que TEM de ser texto, reprovando em vez de estourar.

    A segunda porta guardada deste arquivo, e ela existe pelo mesmo motivo da
    primeira: YAML entrega listas e mapas onde o leitor esperava uma palavra, e
    Python NÃO reclama disso educadamente — `["a"] in {"string"}` levanta
    `unhashable type`, e uma lista usada como chave de dicionário faz o mesmo. O
    resultado é traceback, e ferramenta que estoura com entrada malformada não
    reprova nada.

    Nove lugares deste arquivo assumiam texto: nome de conjunto, nome de campo,
    `type` e `normalize` de campo, nome e `type` de parâmetro, item de
    `allowedMonths`, a própria regra e o `appliesTo` dela. Guardar um por um seria
    escrever a mesma conferência nove vezes e esquecê-la na décima — que é
    literalmente o que aconteceu quando guardei `declared_names` e esqueci o
    `by_name` ao lado.

    Devolve None quando não é texto, e a recusa já foi registrada.
    """
    if isinstance(value, str) and value:
        return value

    fail(f"{where} é {value!r}; {requirement}")

    return None


def mapping_at(where: str, value: object, requirement: str) -> dict | None:
    """Idem para um valor que TEM de ser um mapeamento."""
    if isinstance(value, dict):
        return value

    fail(f"{where} é {value!r}; {requirement}")

    return None


def datasets_of(contract: dict) -> list[dict]:
    """A única porta por onde os conjuntos de um contrato são LIDOS.

    Existe como porta e não como conveniência porque o mesmo defeito entrou duas
    vezes: um leitor que toma `ds["name"]` na fé ESTOURA num contrato que não o tem,
    e uma ferramenta que estoura com entrada malformada não reprova nada. Guardei
    declared_names, esqueci o `by_name` de check_structure, e a suíte de mutação
    encontrou o gêmeo — que é exatamente o que ela existe para fazer.

    Quem DENUNCIA a ausência é check_dataset_shapes, que lê a forma crua e roda
    primeiro. Todo o resto lê por aqui.
    """
    datasets = sequence_at("datasets", contract.get("datasets"),
                           "datasets é a lista dos conjuntos de que o documento é escrito")

    return [ds for ds in datasets if isinstance(ds, dict) and isinstance(ds.get("name"), str) and ds["name"]]


def fields_of(ds: dict) -> list[dict]:
    """Idem para os campos de um conjunto."""
    fields = sequence_at(f"os fields de {ds.get('name', '<sem nome>')!r}", ds.get("fields"),
                         "fields é a lista dos campos do conjunto")

    return [f for f in fields if isinstance(f, dict) and isinstance(f.get("name"), str) and f["name"]]

def declared_names(contract: dict) -> tuple[dict[str, set[str]], set[str]]:
    """Conjuntos e seus campos, mais os parâmetros de geração.

    O que não tem nome é OMITIDO, e não tomado na fé de que exista: quase toda
    conferência abaixo lê por aqui, então um conjunto sem `name` fazia a ferramenta
    ESTOURAR — e uma ferramenta que estoura com entrada malformada não reprova nada.
    Quem denuncia a ausência é check_dataset_shapes, que roda primeiro.
    """
    datasets = {
        ds["name"]: {f["name"] for f in fields_of(ds) if isinstance(f, dict) and f.get("name")}
        for ds in datasets_of(contract)
        if isinstance(ds, dict) and ds.get("name")
    }
    parameters = {
        p["name"]
        for p in parameters_of(contract)
        if isinstance(p, dict) and isinstance(p.get("name"), str) and p["name"]
    }
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

    usable = []
    for q in raw:
        if not isinstance(q, dict):
            continue

        # Não basta a CONSULTA ser mapa: um `join` malformado dentro dela chega
        # intacto a quem consome a lista, e produced_columns percorre os joins de uma
        # consulta composta sem agregação. A porta só entrega o que é utilizável de
        # ponta a ponta; quem REPROVA a forma é check_binding_queries, num lugar só.
        join = q.get("join")
        if join is not None and (
            not isinstance(join, list) or any(not isinstance(j, dict) for j in join)
        ):
            continue

        usable.append(q)

    return usable


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
        ds["name"]: child_parent(ds)
        for ds in datasets_of(contract)
        if child_parent(ds) is not None
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
        ds["name"]: {f["name"] for f in fields_of(ds) if f.get("required") is True}
        for ds in datasets_of(contract)
    }
    contract_row_sets = {ds["name"]: ds.get("rowSet") for ds in datasets_of(contract)}
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
    set_path = source_of_truth(contract, "accountSet")

    row_datasets = [ds for ds in datasets_of(contract) if isinstance(ds.get("rowSet"), dict)]

    if not set_path and not row_datasets:
        return

    if set_path and not (doc_dir / set_path).exists():
        fail(f"{doc_dir.relative_to(ROOT)}: metadata.accountSet cita {set_path}, que não existe")

    for ds in row_datasets:
        ref = ds["rowSet"].get("from")
        if not isinstance(ref, str) or not ref:
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
        key_field = next((f for f in fields_of(ds) if f["name"] == key), None)
        pattern = key_field.get("pattern") if key_field else None
        if pattern is not None and not isinstance(pattern, str):
            # _check_field_shape já recusa isto nomeando o campo; aqui só não se
            # pode ENTREGÁ-LO ao motor de expressões regulares.
            pattern = None

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


# O que cada construção que aponta para outro lugar TEM de nomear. `via` é opcional
# em toda condição e por isso não está aqui.
REFERENCE_MEMBERS = {
    "refersTo": ("dataset", "field"),
    "equalsSumOf": ("dataset", "field"),
    "requiredWhen": ("field",),
    "forbiddenWhen": ("field",),
}


def reference_at(doc_dir: Path, where: str, field: dict, key: str) -> dict | None:
    """Lê uma construção que aponta para outro lugar: refersTo, equalsSumOf, uma
    condição.

    Todas são mapeamentos e todas eram lidas com `.get()` direto. Ausente responde
    None, que é "não declarou"; presente e malformado é RECUSA, porque o curador
    escreveu a construção e engoli-la é a seção sumir do arquivo sem nada acusar.
    """
    declared = field.get(key)
    if declared is None:
        return None

    at = f"{doc_dir.relative_to(ROOT)}: {where}.{key}"

    reference = mapping_at(at, declared, f"{key} é um mapeamento")
    if reference is None:
        return None

    # O MIOLO também, e aqui e não em cada uso: `dataset`, `field` e `via` são
    # nomes, e cada um vira busca em conjunto ou chave de dicionário logo adiante.
    # Conferir no uso seria a mesma conferência escrita seis vezes.
    #
    # Os OBRIGATÓRIOS são exigidos, e não apenas conferidos quando presentes. Um
    # `refersTo: {}` respondia mapeamento vazio, que é falso em Python, e o chamador
    # lia isso como "não declarou" e pulava a conferência inteira — o curador escreveu
    # a integridade referencial e ela não valia para nada.
    for inner in REFERENCE_MEMBERS[key]:
        if required_text(f"{at}.{inner}", reference.get(inner),
                         "aponta para um nome, escrito como texto") is None:
            return None

    for inner in ("via",):
        if inner in reference and required_text(f"{at}.{inner}", reference.get(inner),
                                                "aponta para um nome, escrito como texto") is None:
            return None

    return reference


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
    by_name = {ds["name"]: ds for ds in datasets_of(contract)}

    for ds in datasets_of(contract):
        name = ds["name"]

        parent = child_parent(ds)
        if parent is not None and parent not in datasets:
            fail(f"{doc_dir.relative_to(ROOT)}: {name} é childOf de '{parent}', que não existe")

        for field in fields_of(ds):
            fname = field["name"]

            ref = reference_at(doc_dir, f"{name}.{fname}", field, "refersTo")
            if ref:
                target = ref.get("dataset")
                if target not in datasets:
                    fail(f"{doc_dir.relative_to(ROOT)}: {name}.{fname} refersTo conjunto '{target}', que não existe")
                elif ref.get("field") not in datasets[target]:
                    fail(
                        f"{doc_dir.relative_to(ROOT)}: {name}.{fname} refersTo "
                        f"{target}.{ref.get('field')}, campo que não existe"
                    )

            sum_of = reference_at(doc_dir, f"{name}.{fname}", field, "equalsSumOf")
            if sum_of:
                target = sum_of.get("dataset")
                target_ds = by_name.get(target)
                if target_ds is None:
                    fail(f"{doc_dir.relative_to(ROOT)}: {name}.{fname} equalsSumOf conjunto '{target}', que não existe")
                else:
                    if child_parent(target_ds) != name:
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
                cond = reference_at(doc_dir, f"{name}.{fname}", field, kind)
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
                    via_field = next((f for f in fields_of(ds) if f["name"] == via), None)
                    # Pela mesma porta que as outras duas leituras de refersTo. Esta
                    # ficou de fora quando a porta foi criada, e a varredura não a
                    # denunciou porque fixture nenhuma usava `via` — o ramo inteiro
                    # nunca era executado por ela. A cobertura da varredura é a
                    # cobertura das fixturas.
                    ref = reference_at(doc_dir, f"{name}.{via}", via_field or {}, "refersTo")
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

    # Este laço lê a lista CRUA de propósito: query_list() já exclui a consulta com
    # join malformado, e quem tem de DENUNCIAR essa forma não pode recebê-la
    # filtrada. A porta serve aos consumidores; o guardião olha o que entra.
    for query in raw_queries:
        if not isinstance(query, dict):
            continue

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

        raw_join = query.get("join")
        if raw_join is not None and not isinstance(raw_join, list):
            fail(
                f"{doc_dir.relative_to(ROOT)}: o `join` de '{qname}' não é uma lista: "
                f"{raw_join!r}"
            )
            raw_join = []

        for join_index, join in enumerate(raw_join or []):
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

    for ds in datasets_of(contract):
        parent = child_parent(ds)
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
    schema = source_of_truth(contract, "schema")
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



# O vocabulário que o MOTOR aceita. Cada nome aqui é um nome que
# pkg/reporter/contract sabe aplicar; um contrato que use outro é aceito por este
# validador e recusado lá, que é a divergência que estas conferências existem para
# fechar — ver check_engine_parity abaixo.
FIELD_TYPES = {"string", "integer", "decimal", "boolean", "date", "month"}
NORMALIZATIONS = {"digits"}
MAX_SCALE = 34
MONTHS_OF_YEAR = {f"{m:02d}" for m in range(1, 13)}

# Construções que a biblioteca `re` do Python aceita e a RE2 do Go não tem. Um
# `pattern` que use qualquer uma delas compila aqui e é recusado pelo motor, então o
# contrato passa no CI do catálogo e para na primeira geração.
#
# É uma lista das construções que faltam na RE2, e não um parser dela: a alternativa
# seria reimplementar a RE2 em Python para conferir contratos que ninguém escreveu
# ainda. Estas quatro mais as retrorreferências cobrem tudo que um curador
# plausivelmente escreveria sem saber.
RE2_MISSING = (
    ("(?=", "lookahead"),
    ("(?!", "lookahead negativo"),
    ("(?<=", "lookbehind"),
    ("(?<!", "lookbehind negativo"),
)
# Uma barra que NÃO é ela mesma escapada, seguida de dígito: `\1` é
# retrorreferência e `\\1` é uma barra literal seguida do algarismo um.
#
# O `(?:\\\\)*` no meio é o que faz a conta com barras EMPILHADAS. Em `\\\\\\1` são três
# barras: as duas primeiras são uma barra literal escapada, e a terceira abre a
# retrorreferência — ela é retrorreferência e a RE2 a recusa. Sem esse trecho, o
# olhar-para-trás via a barra anterior e desistia, e o padrão passava.
BACKREFERENCE = re.compile(r"(?<!\\)(?:\\\\)*\\[1-9]")


def check_engine_parity(doc_dir: Path, contract: dict) -> None:
    """O contrato usa apenas o vocabulário que o MOTOR sabe aplicar.

    Por que existe: este validador e o carregador do Reporter
    (pkg/reporter/contract) leem o mesmo arquivo, e onde um lê menos que o outro
    nasce a pior categoria de defeito de catálogo — um contrato que passa no CI
    daqui e é recusado na primeira geração, ou pior, aceito pelos dois e aplicado
    diferente.

    A mais perigosa das divergências que fecharam aqui era `normalize`: este
    validador aceitava qualquer string e o motor só sabe aplicar `digits`. Uma
    normalização desconhecida escreveria o campo SEM normalizar num arquivo dado
    como concluído.
    """
    for ds in datasets_of(contract):
        name = ds.get("name", "<sem nome>")
        for field in fields_of(ds):
            _check_field_shape(doc_dir, name, field)


def _check_field_shape(doc_dir: Path, dataset: str, field: dict) -> None:
    where = f"{doc_dir.relative_to(ROOT)}: {dataset}.{field.get('name', '<sem nome>')}"

    ftype = required_text(f"{where} type", field.get("type"),
                          f"o tipo de um campo é uma palavra: {sorted(FIELD_TYPES)}")
    if ftype is not None and ftype not in FIELD_TYPES:
        fail(f"{where} tem type {ftype!r}; o motor aplica {sorted(FIELD_TYPES)}")

    if field.get("normalize") is not None:
        normalize = required_text(f"{where} normalize", field.get("normalize"),
                                  f"uma normalização é uma palavra: {sorted(NORMALIZATIONS)}")
        if normalize is not None and normalize not in NORMALIZATIONS:
            fail(
                f"{where} tem normalize {normalize!r}, que o motor não sabe aplicar "
                f"({sorted(NORMALIZATIONS)}) — o campo sairia SEM normalizar num arquivo "
                f"dado como concluído"
            )

    length = field.get("length")
    if length is not None and (not isinstance(length, int) or isinstance(length, bool) or length < 1):
        fail(f"{where} tem length {length!r}; é o número de posições que o arquivo dá ao campo, então é ao menos 1")

    _check_pattern(f"{where}.pattern", field.get("pattern"))

    fmt = field.get("format")
    if not isinstance(fmt, dict):
        return

    scale = fmt.get("scale")
    if scale is not None and (not isinstance(scale, int) or isinstance(scale, bool) or not 0 <= scale <= MAX_SCALE):
        fail(
            f"{where}.format.scale é {scale!r}; uma escala é quantas casas decimais o "
            f"arquivo carrega, então está entre 0 e {MAX_SCALE} — acima disso é um "
            f"número que fonte nenhuma responde, e o motor a converte para int32"
        )

    _check_pattern(f"{where}.format.pattern", fmt.get("pattern"))


def _check_pattern(where: str, pattern) -> None:
    """Um pattern compila, e compila também na RE2 que o motor usa."""
    if pattern is None:
        return

    if not isinstance(pattern, str):
        fail(f"{where} é {pattern!r}; um pattern é uma expressão regular escrita como texto")
        return

    try:
        re.compile(pattern)
    except re.error as exc:
        fail(f"{where} não compila: {exc}")
        return

    for construct, spelled in RE2_MISSING:
        if construct in pattern:
            fail(
                f"{where} usa {spelled} ({construct}), que a RE2 do Go não tem — "
                f"compila aqui e é recusado pelo motor"
            )

    if BACKREFERENCE.search(pattern):
        fail(f"{where} usa retrorreferência, que a RE2 do Go não tem — compila aqui e é recusado pelo motor")


def check_dataset_shapes(doc_dir: Path, contract: dict) -> None:
    """Cada conjunto tem nome, tem campos, não repete nome de campo e não gira.

    Um conjunto sem nome fazia esta ferramenta ESTOURAR em vez de reprovar, que é o
    modo de falha que a suíte de mutação existe para não deixar voltar. Um conjunto
    sem campos é uma seção do arquivo que nada popula. Dois campos de mesmo nome não
    podem ambos ser alcançados, e uma referência a ele resolve para o que foi lido
    por último. E um childOf que fecha ciclo trava a montagem do contexto de render.
    """
    declared = sequence_at("datasets", contract.get("datasets"),
                           "datasets é a lista dos conjuntos de que o documento é escrito")

    # O motor recusa isto diretamente, e aqui só era pego de lado — pela conferência
    # do template, que reclamava de cada leitura solta em vez de dizer a coisa óbvia.
    if not declared:
        fail(
            f"{doc_dir.relative_to(ROOT)}: datasets está vazio; um contrato que não "
            f"declara conjunto nenhum não declara nada de que o arquivo possa ser escrito"
        )

    seen_datasets: set[str] = set()

    for ds in declared:
        if not isinstance(ds, dict):
            fail(f"{doc_dir.relative_to(ROOT)}: um conjunto é um mapeamento de name, grain e fields")
            continue

        name = required_text(f"{doc_dir.relative_to(ROOT)}: o name de um conjunto", ds.get("name"),
                             "um conjunto é nomeado por texto, para que template e binding possam referi-lo")
        if name is None:
            continue

        if name in seen_datasets:
            fail(f"{doc_dir.relative_to(ROOT)}: conjunto '{name}' declarado duas vezes")
        seen_datasets.add(name)

        fields = ds.get("fields")
        if not isinstance(fields, list) or not fields:
            fail(f"{doc_dir.relative_to(ROOT)}: conjunto '{name}' não declara campo nenhum, então nada o popula")
            continue

        seen_fields: set[str] = set()
        for field in fields:
            if mapping_at(f"{doc_dir.relative_to(ROOT)}: um campo de '{name}'", field,
                          "um campo é um mapeamento de name, type e o que mais o declara") is None:
                continue

            fname = required_text(f"{doc_dir.relative_to(ROOT)}: o name de um campo de '{name}'",
                                  field.get("name"), "um campo é nomeado por texto")
            if fname is None:
                continue

            if fname in seen_fields:
                fail(
                    f"{doc_dir.relative_to(ROOT)}: {name}.{fname} declarado duas "
                    f"vezes; os dois não podem ser alcançados e uma referência resolve "
                    f"para o último lido"
                )
            seen_fields.add(fname)

        _check_grain(doc_dir, ds, name, seen_fields)
        _check_childof_shape(doc_dir, ds, name)

    _check_childof_cycles(doc_dir, contract)


def _check_grain(doc_dir: Path, ds: dict, name: str, fields: set[str]) -> None:
    """As chaves do grão são campos que o conjunto declara.

    Um grão sobre campo inexistente é a exigência de uma linha por combinação que
    nunca é conferida: o arquivo sai com a mesma rubrica duas vezes e nada acusa.
    """
    grain = ds.get("grain")

    if grain is None or grain == "singleton":
        return

    if not isinstance(grain, list):
        fail(f"{doc_dir.relative_to(ROOT)}: {name}.grain é {grain!r}; é 'singleton' ou uma lista de campos")
        return

    for key in grain:
        if not isinstance(key, str) or key not in fields:
            fail(f"{doc_dir.relative_to(ROOT)}: {name}.grain nomeia {key!r}, campo que o conjunto não declara")


def _check_childof_shape(doc_dir: Path, ds: dict, name: str) -> None:
    """A declaração de childOf tem a forma que os leitores esperam.

    Denunciado AQUI, no leitor cru, porque `child_parent` responde None para uma
    declaração malformada — o que os leitores precisam para não estourar, e que
    sozinho leria como "este conjunto não pende de ninguém". Um curador que escreveu
    `childOf` e teve a linha ignorada em silêncio é a falha que este arquivo inteiro
    existe para não ter: a seção sai do arquivo e nada acusa.
    """
    if "childOf" not in ds:
        return

    childof = mapping_at(f"{doc_dir.relative_to(ROOT)}: {name}.childOf", ds.get("childOf"),
                         "childOf é um mapeamento que nomeia o conjunto de que este pende")
    if childof is None:
        return

    required_text(f"{doc_dir.relative_to(ROOT)}: {name}.childOf.dataset", childof.get("dataset"),
                  "childOf nomeia o conjunto pai por texto")


def _check_childof_cycles(doc_dir: Path, contract: dict) -> None:
    parents = {ds["name"]: child_parent(ds) for ds in datasets_of(contract)}

    for start in parents:
        seen = {start}
        current = parents.get(start)

        while current is not None:
            if current in seen:
                fail(
                    f"{doc_dir.relative_to(ROOT)}: childOf fecha um ciclo em '{current}' — "
                    f"nenhum desses conjuntos tem raiz, então nenhum é publicado"
                )
                break

            seen.add(current)
            current = parents.get(current)


def check_parameters(doc_dir: Path, contract: dict) -> None:
    """Os parâmetros de geração são declarações que o motor consegue satisfazer.

    Um parâmetro é respondido pela requisição, então uma declaração impossível — tipo
    desconhecido, default que o próprio domínio recusa, mês que não existe — só é
    descoberta quando alguém tenta gerar o documento, na véspera do prazo.
    """
    seen: set[str] = set()

    for param in parameters_of(contract):
        if mapping_at(f"{doc_dir.relative_to(ROOT)}: um parâmetro", param,
                      "um parâmetro é um mapeamento de name, type e o que mais o declara") is None:
            continue

        name = required_text(f"{doc_dir.relative_to(ROOT)}: o name de um parâmetro", param.get("name"),
                             "um parâmetro é nomeado por texto, que é como a requisição o responde")
        if name is None:
            continue

        where = f"{doc_dir.relative_to(ROOT)}: parâmetro '{name}'"

        if name in seen:
            fail(f"{where} declarado duas vezes")
        seen.add(name)

        ptype = required_text(f"{where} type", param.get("type"),
                              f"o tipo de um parâmetro é uma palavra: {sorted(FIELD_TYPES)}")
        if ptype is not None and ptype not in FIELD_TYPES:
            fail(f"{where} tem type {ptype!r}; o motor aceita {sorted(FIELD_TYPES)}")

        domain = param.get("domain")
        default = param.get("default")

        if domain is not None and not isinstance(domain, list):
            fail(f"{where} tem domain {domain!r}; um domínio é a lista fechada de valores aceitos")
            domain = None

        if default is not None and domain and default not in domain:
            fail(f"{where} tem default {default!r} fora do próprio domain {domain!r} — nunca poderia ser satisfeito")

        months = param.get("allowedMonths")
        if months is None:
            continue

        if ptype != "month":
            fail(f"{where} declara allowedMonths e não é do tipo month, então a restrição não se aplica a nada")

        if not isinstance(months, list) or not months:
            fail(f"{where} tem allowedMonths {months!r}; é a lista dos meses aceitos, como ['06', '12']")
            continue

        for month in months:
            if not isinstance(month, str) or month not in MONTHS_OF_YEAR:
                fail(f"{where} tem allowedMonths com {month!r}; um mês é de '01' a '12', com dois dígitos")


def check_rules(doc_dir: Path, contract: dict) -> None:
    """Severidade é obrigatória e o alvo tem de existir.

    Uma regra sem severidade não diz se bloqueia a geração ou apenas avisa, e essa
    é a diferença entre travar a operação do cliente numa véspera de prazo e
    entregar arquivo errado.
    """
    datasets, parameters = declared_names(contract)
    seen: set[str] = set()

    for rule in rules_of(contract):
        if mapping_at(f"{doc_dir.relative_to(ROOT)}: uma regra", rule,
                      "uma regra é um mapeamento de id, severity, appliesTo e assert") is None:
            continue

        rule_id = rule.get("id")

        # Sem id, a regra não pode ser citada por nada — nem pela mensagem que ela
        # mesma produz quando reprova, que é onde alguém a procuraria. E duas regras
        # sem id são indistinguíveis, então a conferência de duplicidade abaixo
        # também deixaria de valer.
        if not isinstance(rule_id, str) or not rule_id:
            fail(f"{doc_dir.relative_to(ROOT)}: há regra sem id, que nada pode citar")
            rule_id = "<sem id>"

        if rule_id in seen:
            fail(f"{doc_dir.relative_to(ROOT)}: regra '{rule_id}' duplicada")
        seen.add(rule_id)

        # Sem assert, a regra não confere nada: ela aparece no contrato, é lida em
        # revisão como se protegesse alguma coisa, e o arquivo sai sem a conferência
        # que o leiaute pede.
        if not rule.get("assert"):
            fail(f"{doc_dir.relative_to(ROOT)}: regra '{rule_id}' não tem assert, então não confere nada")

        severity = rule.get("severity")
        if not isinstance(severity, str) or severity not in {"error", "warning", "info"}:
            fail(
                f"{doc_dir.relative_to(ROOT)}: regra '{rule_id}' tem severity "
                f"{severity!r}; use error, warning ou info"
            )

        target = rule.get("appliesTo", "")
        if not isinstance(target, str):
            fail(f"{doc_dir.relative_to(ROOT)}: regra '{rule_id}' tem appliesTo {target!r}; é o nome do que ela lê, escrito como texto")
            continue

        head, _, tail = target.partition(".")
        if head and head not in datasets and head != "parameters":
            fail(
                f"{doc_dir.relative_to(ROOT)}: regra '{rule_id}' aponta para "
                f"'{target}', que o contrato não declara"
            )
        # A CAUDA também: `appliesTo: cosif_balances.natureza` tinha a cabeça certa e
        # o campo inexistente, e passava — uma regra sobre campo que não existe é uma
        # conferência que nunca dispara, o mesmo modo de falha silencioso do
        # requiredWhen sobre campo fantasma.
        elif tail and head == "parameters" and tail not in parameters:
            fail(
                f"{doc_dir.relative_to(ROOT)}: regra '{rule_id}' aponta para "
                f"'{target}', parâmetro que o contrato não declara"
            )
        elif tail and head in datasets and tail not in datasets[head]:
            fail(
                f"{doc_dir.relative_to(ROOT)}: regra '{rule_id}' aponta para "
                f"'{target}', campo que '{head}' não declara"
            )


def check_index(catalog: dict, contracts: dict[str, dict]) -> None:
    """O índice repete o metadata do contrato, então pode divergir dele.

    A duplicação é deliberada — o índice existe para filtrar sem baixar tudo — mas
    divergir significa mostrar ao cliente um documento que não é o que ele recebe.
    """
    mirrored = ("country", "regulator", "document", "title", "version", "periodicity")

    documents = sequence_at("catalog.yaml: documents", catalog.get("documents"),
                            "documents é a lista dos documentos do catálogo")

    for entry in documents:
        if mapping_at("catalog.yaml: uma entrada de documents", entry,
                      "cada entrada é um mapeamento de id, path e o que mais o índice anuncia") is None:
            continue

        doc_id = required_text("catalog.yaml: o id de uma entrada", entry.get("id"),
                               "o id de um documento é texto")
        if doc_id is None:
            continue

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

    indexed = {e["id"] for e in documents if isinstance(e, dict) and isinstance(e.get("id"), str)}
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
        metadata = contract.get("metadata")
        doc_id = metadata.get("id") if isinstance(metadata, dict) else None

        # Texto, e não apenas presente: o id vira CHAVE de dicionário uma linha
        # abaixo, e uma lista ali levanta unhashable antes de qualquer conferência.
        if not isinstance(doc_id, str) or not doc_id:
            fail(f"{path.relative_to(ROOT)}: metadata.id é {doc_id!r}; é o identificador do documento, escrito como texto")
            continue

        contracts[doc_id] = contract
        check_dataset_shapes(doc_dir, contract)
        check_template(doc_dir, contract)
        check_formatting_not_duplicated(doc_dir)
        check_no_extraction_in_contract(doc_dir, contract)
        check_closed_account_set(doc_dir, contract)
        check_engine_parity(doc_dir, contract)
        check_parameters(doc_dir, contract)
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
