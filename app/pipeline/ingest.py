from __future__ import annotations

from pathlib import Path
import gzip
import re
import shutil
import tarfile
import urllib.error
import urllib.request

from app.models.paper import PaperRecord

ARXIV_ID_RE = re.compile(r"(?P<id>\d{4}\.\d{4,5})(v\d+)?")


def normalize_arxiv_entry(raw: str) -> tuple[str, str]:
    value = raw.strip()
    if not value:
        raise ValueError("Empty arXiv entry.")

    match = ARXIV_ID_RE.search(value)
    if not match:
        raise ValueError(f"Cannot parse arXiv id from entry: {raw}")

    arxiv_id = match.group("id")
    source_url = f"https://arxiv.org/src/{arxiv_id}"
    return arxiv_id, source_url


def read_input_list(input_txt: Path) -> list[PaperRecord]:
    if not input_txt.exists():
        raise FileNotFoundError(f"Input file not found: {input_txt}")

    records: list[PaperRecord] = []
    for line in input_txt.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        arxiv_id, source_url = normalize_arxiv_entry(stripped)
        records.append(
            PaperRecord(
                arxiv_id=arxiv_id,
                normalized_id=arxiv_id.replace(".", "_"),
                source_url=source_url,
                original_input=stripped,
            )
        )
    return records


def prepare_source_tree(record: PaperRecord, cache_dir: Path) -> PaperRecord:
    archives_dir = cache_dir / "archives"
    sources_dir = cache_dir / "sources"
    archives_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.mkdir(parents=True, exist_ok=True)

    archive_path = archives_dir / f"{record.normalized_id}.src"
    source_dir = sources_dir / record.normalized_id

    record.archive_path = archive_path
    record.source_dir = source_dir

    if source_dir.exists() and any(source_dir.iterdir()):
        record.status = "source-ready"
        record.notes.append("Reused cached source tree.")
        return record

    if archive_path.exists() and archive_path.stat().st_size > 0:
        record.notes.append("Reused cached source archive.")
    else:
        _download_source_archive(record.source_url, archive_path)
        record.notes.append("Downloaded source archive from arXiv.")

    if source_dir.exists():
        shutil.rmtree(source_dir)
    source_dir.mkdir(parents=True, exist_ok=True)

    extracted = _extract_source_archive(archive_path, source_dir)
    record.status = "source-ready"
    record.notes.append(extracted)
    return record


def _download_source_archive(source_url: str, archive_path: Path) -> None:
    request = urllib.request.Request(
        source_url,
        headers={
            "User-Agent": "autopaper/0.1 (+https://arxiv.org)",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        archive_path.write_bytes(response.read())


def _extract_source_archive(archive_path: Path, target_dir: Path) -> str:
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as tar:
            tar.extractall(target_dir)
        return "Extracted tar archive."

    data = archive_path.read_bytes()
    if data[:2] == b"\x1f\x8b":
        decompressed = gzip.decompress(data)
        tex_path = target_dir / "main.tex"
        tex_path.write_bytes(decompressed)
        return "Decompressed gzip-wrapped TeX source."

    text_path = target_dir / "main.tex"
    text_path.write_bytes(data)
    return "Stored plain TeX source."
