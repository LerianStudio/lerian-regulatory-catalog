#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""Monta e confere o pacote .tar.gz de uma release do catálogo.

O Reporter baixa UM `.tar.gz` da release mais recente e o lê pelo manifesto que
viaja dentro dele — não por um checksum publicado ao lado, que um transporte
truncado levaria junto. O formato é o que `pkg/reporter/catalog/archive.go`
escreve: `.reporter/manifest.json` primeiro, cada arquivo depois em ordem, e o
SHA-256 de cada um no manifesto.

DETERMINÍSTICO DE PROPÓSITO: mesma árvore, mesmos bytes. Sem isso, "reconstruí a
release e deu outro arquivo" não distingue conteúdo alterado de ruído do
empacotador, e a conferência que o banco faz contra o que publicamos deixa de
significar alguma coisa. Por isso mtime fixo, entradas ordenadas e gzip sem
carimbo de hora.

Uso:
    python3 tools/release.py build --version 1.0.0 --out dist/catalog-1.0.0.tar.gz
    python3 tools/release.py verify dist/catalog-1.0.0.tar.gz --version 1.0.0
"""

import argparse
import gzip
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Fixados por pkg/reporter/catalog/archive.go, não são escolha nossa: o caminho do
# manifesto dentro do pacote e o teto de EXPANSÃO que o leitor impõe. Um .tar.gz de
# poucos kilobytes expande a gigabytes, e um import que esgota a memória do manager
# derruba a superfície de geração junto.
MANIFEST_NAME = ".reporter/manifest.json"
MAX_ARCHIVE_BYTES = 256 << 20

# Os arquivos que um documento publica. O Reporter os lê com EXATAMENTE estes
# nomes, então renomear um deles aqui é também uma mudança no Reporter — não uma
# escolha de organização deste repositório.
#
# O empacotamento nunca renomeia nada: um nome traduzido no build deixaria os dois
# lados discordando dentro de uma etapa que ninguém revisa.
DOCUMENT_FILES = ("contract.yaml", "template.tpl", "binding.example.yaml")


def checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_path(path: str) -> bool:
    """Mesma regra de catalog.SafePath: um caminho que só cai dentro da raiz.

    O caminho é o único campo do pacote que decide ONDE um byte é escrito, e
    `../../etc/cron.d/qualquer-coisa` é exatamente a entrada que um pacote
    carrega quando alguém o remonta.
    """
    if not path or path.startswith("/") or "\\" in path:
        return False

    return all(segment not in ("", ".", "..") for segment in path.split("/"))


def document_paths(index: bytes) -> list[str]:
    """Os diretórios que um catalog.yaml publica, na ordem do índice."""
    catalog = yaml.safe_load(index.decode("utf-8")) or {}

    return [entry["path"] for entry in catalog.get("documents", [])]


# `schema/` fica de fora do pacote. São os XSDs e os manuais em PDF publicados pelo
# regulador, e o README já diz o que eles são: fonte para ESCREVER e revisar o
# contrato, não algo que o Reporter execute. Hoje são 1,3 MB contra 30 KB de
# catálogo — cada cliente baixaria quarenta vezes o conteúdo que usa, e a conta
# cresce a cada documento novo. Ficam no repositório, onde a curadoria os lê.
EXCLUDED_DIR = "schema"


def collect() -> dict[str, bytes]:
    """O conteúdo da release: o índice e cada documento publicado.

    O que NÃO entra: README, CONTRIBUTING, LICENSE, `tools/` e o `schema/` de cada
    documento. São o processo de curadoria, não o catálogo — e o Reporter recusa
    um pacote que carregue arquivo que o manifesto não publica, então a linha
    precisa ser explícita em vez de emergir de um glob.
    """
    index = (ROOT / "catalog.yaml").read_bytes()
    files = {"catalog.yaml": index}

    for path in document_paths(index):
        directory = ROOT / path

        if not directory.is_dir():
            raise Refusal(f"catalog.yaml publica '{path}', que não é um diretório deste repositório")

        for item in sorted(directory.rglob("*")):
            if item.is_file() and EXCLUDED_DIR not in item.relative_to(directory).parts:
                files[item.relative_to(ROOT).as_posix()] = item.read_bytes()

    return files


class Refusal(Exception):
    """Uma recusa com mensagem já escrita para quem lê o log do CI."""


def add_entry(archive: tarfile.TarFile, path: str, content: bytes) -> None:
    """Uma entrada, com os mesmos campos que o exportador do Reporter escreve.

    mtime 0, dono 0, modo 0600: o horário e o usuário do empacotamento não são
    propriedade do catálogo, e guardá-los faria a mesma árvore render bytes
    diferentes a cada execução do CI.
    """
    info = tarfile.TarInfo(path)
    info.size = len(content)
    info.mode = 0o600
    info.mtime = 0
    info.type = tarfile.REGTYPE

    archive.addfile(info, io.BytesIO(content))


def build(version: str, out: Path) -> None:
    files = collect()
    manifest = {
        "version": version,
        "checksums": {path: checksum(content) for path, content in files.items()},
    }

    raw = io.BytesIO()

    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as archive:
        # O MANIFESTO PRIMEIRO, como o exportador do Reporter escreve: quem lê o
        # encontra antes de qualquer conteúdo, e um pacote truncado é recusado
        # pelo conteúdo que falta em vez de pelo manifesto que nunca chegou.
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        add_entry(archive, MANIFEST_NAME, encoded)

        for path in sorted(files):
            add_entry(archive, path, files[path])

    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "wb") as handle:
        # mtime=0 e filename='' porque o cabeçalho gzip guarda os dois: com eles,
        # a mesma árvore sai com bytes diferentes e o pacote deixa de ser
        # reproduzível por quem quiser conferir o que publicamos.
        with gzip.GzipFile(fileobj=handle, mode="wb", compresslevel=9, mtime=0, filename="") as compressed:
            compressed.write(raw.getvalue())

    print(f"{out}: {len(files)} arquivo(s), release '{version}', {out.stat().st_size} bytes")


def read_archive(blob: bytes) -> tuple[dict[str, bytes], dict]:
    """Lê o pacote como o Reporter lê: limitado, e recusando caminho inseguro."""
    try:
        expanded = bounded_decompress(blob)
    except OSError as exc:
        raise Refusal(f"o pacote não abre: {exc}. Um transporte que chegou pela metade é assim") from exc

    files: dict[str, bytes] = {}
    manifest: dict | None = None

    try:
        entries = tarfile.open(fileobj=io.BytesIO(expanded), mode="r:")
    except tarfile.TarError as exc:
        raise Refusal(
            f"o pacote termina no meio: {exc}. O que chegou é PARTE de uma release, e instalar "
            f"parte de uma release é a única coisa que este desenho não faz"
        ) from exc

    with entries as archive:
        for member in archive:
            if not member.isfile():
                continue

            handle = archive.extractfile(member)
            content = handle.read() if handle else b""

            if member.name == MANIFEST_NAME:
                try:
                    manifest = json.loads(content.decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    raise Refusal(f"o manifesto do pacote não pode ser lido: {exc}") from exc

                if not isinstance(manifest, dict):
                    raise Refusal("o manifesto do pacote não é um mapeamento, então não descreve release nenhuma")

                continue

            # Conferido ANTES de o conteúdo ser guardado: o caminho decide onde o
            # byte cai, e essa é a checagem que o Reporter faz no mesmo ponto.
            if not safe_path(member.name):
                raise Refusal(f"o pacote carrega uma entrada em '{member.name}', que não é caminho de catálogo")

            files[member.name] = content

    if manifest is None:
        raise Refusal(
            "o pacote não carrega manifesto, então não há contra o que conferir o conteúdo. "
            "Um pacote que se descreve como nada confere como qualquer coisa"
        )

    return files, manifest


def bounded_decompress(blob: bytes) -> bytes:
    """Expande recusando passar do teto que o Reporter impõe."""
    out = io.BytesIO()

    with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as compressed:
        while chunk := compressed.read(1 << 20):
            if out.tell() + len(chunk) > MAX_ARCHIVE_BYTES:
                raise Refusal(
                    f"o pacote expande além de {MAX_ARCHIVE_BYTES} bytes. O catálogo curado tem "
                    f"poucos megabytes de YAML; acima disso é engano ou bomba de descompressão"
                )

            out.write(chunk)

    return out.getvalue()


def verify(archive_path: Path, version: str | None, require_document_layout: bool) -> int:
    files, manifest = read_archive(archive_path.read_bytes())
    published = manifest.get("checksums") or {}
    problems: list[str] = []

    if not isinstance(published, dict):
        raise Refusal("os checksums do manifesto não são um mapeamento de caminho para SHA-256")

    if not published:
        raise Refusal(
            f"a release '{manifest.get('version')}' não publica checksum nenhum, então nada do "
            f"conteúdo pode ser conferido. Um manifesto que lista nada confere tudo"
        )

    if version is not None and manifest.get("version") != version:
        problems.append(f"o manifesto diz release '{manifest.get('version')}' e a tag diz '{version}'")

    # NOS DOIS SENTIDOS. Arquivo que não bate é o caso óbvio; arquivo que chegou
    # sem ter sido publicado é o que vale nomear — conteúdo que ninguém curou
    # seria servido como se tivesse sido revisado.
    for path in sorted(published):
        if path not in files:
            problems.append(f"o manifesto publica '{path}' e o pacote não o carrega")
        elif checksum(files[path]) != published[path]:
            problems.append(f"'{path}' não bate com o que o manifesto publica para ele")

    for path in sorted(files):
        if path not in published:
            problems.append(f"'{path}' chegou no pacote e o manifesto não o publica")

    missing = document_layout_gaps(files)

    for failure in problems:
        print(f"erro: {failure}", file=sys.stderr)

    if problems:
        print(f"\n{len(problems)} problema(s) de integridade.", file=sys.stderr)
        return 1

    print(f"{len(files)} arquivo(s) conferido(s) contra o manifesto da release '{manifest.get('version')}'.")

    if missing:
        label = "erro" if require_document_layout else "aviso"

        for gap in missing:
            print(f"{label}: {gap}", file=sys.stderr)

        print(
            f"{label}: um documento publica {', '.join(DOCUMENT_FILES)}, e o Reporter lê exatamente "
            f"esses nomes. Publicar um documento incompleto instala no cliente um documento que ele "
            f"assina e que não gera.",
            file=sys.stderr,
        )

        if require_document_layout:
            return 1

    return 0


def document_layout_gaps(files: dict[str, bytes]) -> list[str]:
    """Os documentos que este pacote publica pela metade.

    Integridade e completude são coisas diferentes: um pacote pode estar
    perfeitamente íntegro — cada byte batendo com o manifesto — e ainda assim
    carregar um documento sem template, que o cliente assina e que nunca gera.
    Conferir só a primeira publicaria exatamente isso.
    """
    # Lido do PACOTE, nunca da árvore: a conferência tem de valer para um arquivo
    # que chegou de fora, sem o repositório ao lado.
    if "catalog.yaml" not in files:
        return ["o pacote não carrega catalog.yaml, então nada diz quais documentos ele publica"]

    gaps = []

    for path in document_paths(files["catalog.yaml"]):
        for name in DOCUMENT_FILES:
            if f"{path}/{name}" not in files:
                gaps.append(f"o índice publica '{path}' e o pacote não carrega seu '{name}'")

    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    builder = commands.add_parser("build", help="monta o pacote da release")
    builder.add_argument("--version", required=True, help="a versão da release (a tag, sem o 'v')")
    builder.add_argument("--out", required=True, type=Path, help="onde escrever o .tar.gz")

    checker = commands.add_parser("verify", help="confere o pacote como o Reporter o leria")
    checker.add_argument("archive", type=Path)
    checker.add_argument("--version", help="a versão que a tag promete; confere contra o manifesto")
    checker.add_argument(
        "--require-document-layout",
        action="store_true",
        help="reprova se algum documento do índice está incompleto (usado ao publicar)",
    )

    args = parser.parse_args()

    try:
        if args.command == "build":
            build(args.version, args.out)
            return 0

        return verify(args.archive, args.version, args.require_document_layout)
    except Refusal as refusal:
        print(f"erro: {refusal}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
