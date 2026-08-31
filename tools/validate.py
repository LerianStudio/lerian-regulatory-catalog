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

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FAILURES: list[str] = []
WARNINGS: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)


def warn(msg: str) -> None:
    WARNINGS.append(msg)


def load(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
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
    loops = dict(re.findall(r"\{%-?\s*for\s+(\w+)\s+in\s+(\w+)", body))
    refs = set(re.findall(r"\{\{\s*([A-Za-z_]\w*)\.(\w+)", body))

    placed: set[tuple[str, str]] = set()
    for head, field in sorted(refs):
        dataset = loops.get(head, head)

        if dataset == "system":
            if field not in parameters:
                fail(
                    f"{doc_dir.relative_to(ROOT)}: template usa system.{field}, "
                    f"que o contrato não declara em parameters"
                )
            continue

        if dataset not in datasets:
            fail(
                f"{doc_dir.relative_to(ROOT)}: template itera sobre '{dataset}', "
                f"que o contrato não declara em datasets"
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


def check_references(doc_dir: Path, contract: dict) -> None:
    """Todo arquivo que o contrato cita tem de existir."""
    schema = contract.get("metadata", {}).get("sourceOfTruth", {}).get("schema")
    if schema and not (doc_dir / schema).exists():
        fail(f"{doc_dir.relative_to(ROOT)}: contrato cita {schema}, que não existe")

    for dataset in contract.get("datasets", []):
        for field in dataset.get("fields", []):
            table = (
                field.get("measure", {})
                .get("statedIn", {})
                .get("accountNature", {})
                .get("table")
            )
            if table and not (doc_dir / table).exists():
                fail(
                    f"{doc_dir.relative_to(ROOT)}: {dataset['name']}.{field['name']} "
                    f"cita {table}, que não existe"
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
