#!/usr/bin/env python3
"""Confere que a conferência morde.

Um verificador que aprova tudo é pior que nenhum: ele transforma "o CI passou" em
uma frase sem conteúdo, e é assim que uma release corrompida chega ao cliente com
carimbo de conferida. Cada caso abaixo é uma corrupção que o transporte ou o
empacotador produzem de verdade.

Uso: python3 tools/test_release.py
"""

import gzip
import io
import json
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import release


def pack(files: dict[str, bytes], manifest: dict) -> bytes:
    raw = io.BytesIO()

    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as archive:
        release.add_entry(archive, release.MANIFEST_NAME, json.dumps(manifest).encode("utf-8"))

        for path in sorted(files):
            release.add_entry(archive, path, files[path])

    out = io.BytesIO()

    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="") as compressed:
        compressed.write(raw.getvalue())

    return out.getvalue()


def gzipped(payload: bytes) -> bytes:
    out = io.BytesIO()

    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="") as compressed:
        compressed.write(payload)

    return out.getvalue()


def refused_blob(blob: bytes, why: str) -> None:
    """Um pacote malformado recusa com mensagem, nunca com traceback."""
    archive = Path(WORKSPACE) / "catalog-selftest.tar.gz"
    archive.write_bytes(blob)

    try:
        code = release.verify(archive, None, False)
    except release.Refusal:
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"estourou em vez de recusar ({why}): {exc!r}") from exc

    assert code != 0, f"passou e não devia: {why}"


def refused(files: dict[str, bytes], manifest: dict, why: str) -> None:
    """A conferência tem de recusar — por exceção ou por código de saída."""
    archive = Path(WORKSPACE) / "catalog-selftest.tar.gz"
    archive.write_bytes(pack(files, manifest))

    try:
        code = release.verify(archive, None, False)
    except release.Refusal:
        return

    assert code != 0, f"passou e não devia: {why}"


WORKSPACE = tempfile.mkdtemp(prefix="catalog-selftest-")


def main() -> int:
    files = {"a/contract.yaml": b"um\n", "a/template.tpl": b"dois\n"}
    good = {path: release.checksum(content) for path, content in files.items()}

    # Sanidade: o pacote íntegro passa. Sem isto os casos abaixo não provam nada,
    # porque um verificador que recusa tudo também os recusaria.
    archive = Path(WORKSPACE) / "catalog-selftest.tar.gz"
    archive.write_bytes(pack(files, {"version": "1.0.0", "checksums": good}))
    assert release.verify(archive, "1.0.0", False) == 0, "o pacote íntegro devia passar"

    # Conteúdo alterado entre a curadoria e a chegada.
    refused({**files, "a/contract.yaml": b"outro\n"}, {"version": "1.0.0", "checksums": good}, "checksum diferente")

    # Arquivo que o manifesto promete e o pacote não traz — o transporte truncado.
    refused({"a/template.tpl": files["a/template.tpl"]}, {"version": "1.0.0", "checksums": good}, "arquivo ausente")

    # Arquivo que chegou sem ninguém ter publicado: conteúdo que ninguém curou.
    extra = {**files, "a/intruso.yaml": b"tres\n"}
    refused(extra, {"version": "1.0.0", "checksums": good}, "arquivo não publicado")

    # Manifesto vazio: lista nada, confere tudo.
    refused(files, {"version": "1.0.0", "checksums": {}}, "manifesto sem checksums")

    # Caminho que escapa da raiz do catálogo.
    escaped = {"../../etc/cron.d/qualquer": b"quatro\n"}
    refused(escaped, {"version": "1.0.0", "checksums": {p: release.checksum(c) for p, c in escaped.items()}}, "caminho inseguro")

    # Manifesto que não é JSON: entra pelo mesmo caminho que o conteúdo bom, e
    # precisa sair como recusa escrita, não como traceback.
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as archive_out:
        release.add_entry(archive_out, release.MANIFEST_NAME, b"nao sou json{")
    refused_blob(gzipped(raw.getvalue()), "manifesto ilegível")

    # Gzip válido carregando algo que não é tar — o pacote que chegou pela metade.
    refused_blob(gzipped(b"isto nao e um tar" * 100), "tar corrompido")

    # A tag promete uma versão e o manifesto descreve outra.
    archive.write_bytes(pack(files, {"version": "1.0.0", "checksums": good}))
    assert release.verify(archive, "2.0.0", False) != 0, "versão divergente devia reprovar"

    # E a legibilidade pelo Reporter reprova quando exigida.
    assert release.verify(archive, "1.0.0", True) != 0, "layout ilegível pelo Reporter devia reprovar ao publicar"

    print("9 corrupção(ões) recusada(s), pacote íntegro aprovado.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
