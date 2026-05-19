from __future__ import annotations

from pathlib import Path
import gzip
import re
import shutil
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

from app.models.paper import PaperRecord

ARXIV_ID_RE = re.compile(r"(?P<id>\d{4}\.\d{4,5})(v\d+)?")
DOWNLOAD_TIMEOUT_SECONDS = 90
DOWNLOAD_RETRIES = 4
DOWNLOAD_BACKOFF_SECONDS = 2.0
DOWNLOAD_THROTTLE_SECONDS = 1.25
_LAST_DOWNLOAD_AT = 0.0


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
        records.append(_parse_input_entry(stripped, input_txt.parent))
    return records


def prepare_source_tree(record: PaperRecord, cache_dir: Path) -> PaperRecord:
    if record.input_kind == "local_pdf":
        if not record.pdf_path or not record.pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {record.pdf_path}")
        record.status = "pdf-ready"
        record.notes.append("Using local PDF input.")
        return record

    archives_dir = cache_dir / "archives"
    pdf_dir = cache_dir / "pdfs"
    sources_dir = cache_dir / "sources"
    archives_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.mkdir(parents=True, exist_ok=True)

    archive_path = archives_dir / f"{record.normalized_id}.src"
    cached_pdf_path = pdf_dir / f"{record.normalized_id}.pdf"
    source_dir = sources_dir / record.normalized_id

    record.archive_path = archive_path
    record.source_dir = source_dir

    if cached_pdf_path.exists() and cached_pdf_path.stat().st_size > 0:
        record.pdf_path = cached_pdf_path
        record.status = "pdf-ready"
        record.notes.append("Reused cached PDF fallback.")
        return record

    if source_dir.exists() and any(source_dir.iterdir()):
        legacy_pdf = _detect_legacy_pdf_source_dir(source_dir)
        if legacy_pdf is not None:
            cached_pdf_path.write_bytes(legacy_pdf.read_bytes())
            record.pdf_path = cached_pdf_path
            record.status = "pdf-ready"
            record.notes.append("Detected legacy cached PDF that had been stored as TeX; repaired cache and switched to PDF fallback.")
            return record
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

    extracted_kind, extracted_note = _extract_source_archive(archive_path, source_dir, cached_pdf_path)
    if extracted_kind == "pdf":
        record.pdf_path = cached_pdf_path
        record.status = "pdf-ready"
    else:
        record.status = "source-ready"
    record.notes.append(extracted_note)
    return record


def _download_source_archive(source_url: str, archive_path: Path) -> None:
    _throttle_downloads()
    request = urllib.request.Request(
        source_url,
        headers={
            "User-Agent": "autopaper/0.1 (+https://arxiv.org)",
            "Accept": "*/*",
            "Connection": "close",
        },
    )
    last_error: Exception | None = None

    for attempt in range(DOWNLOAD_RETRIES):
        temp_path: Path | None = None
        try:
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
                with tempfile.NamedTemporaryFile(delete=False, dir=str(archive_path.parent), suffix=".part") as temp_file:
                    temp_path = Path(temp_file.name)
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        temp_file.write(chunk)
            if temp_path is None or temp_path.stat().st_size == 0:
                raise ValueError(f"Downloaded empty archive from {source_url}")
            temp_path.replace(archive_path)
            return
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            if isinstance(exc, urllib.error.HTTPError) and exc.code in {403, 404}:
                break
            if attempt + 1 >= DOWNLOAD_RETRIES:
                break
            time.sleep(DOWNLOAD_BACKOFF_SECONDS * (attempt + 1))

    raise RuntimeError(f"Failed to download arXiv source after {DOWNLOAD_RETRIES} attempts: {last_error}") from last_error


def _extract_source_archive(archive_path: Path, target_dir: Path, pdf_path: Path) -> tuple[str, str]:
    data = archive_path.read_bytes()
    if _is_pdf_bytes(data):
        pdf_path.write_bytes(data)
        return "pdf", "arXiv src endpoint returned a PDF; switched to PDF fallback."

    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as tar:
            tar.extractall(target_dir)
        return "latex", "Extracted tar archive."

    if data[:2] == b"\x1f\x8b":
        decompressed = gzip.decompress(data)
        if _is_pdf_bytes(decompressed):
            pdf_path.write_bytes(decompressed)
            return "pdf", "arXiv src endpoint returned a gzip-wrapped PDF; switched to PDF fallback."
        tex_path = target_dir / "main.tex"
        tex_path.write_bytes(decompressed)
        return "latex", "Decompressed gzip-wrapped TeX source."

    text_path = target_dir / "main.tex"
    text_path.write_bytes(data)
    return "latex", "Stored plain TeX source."


def _parse_input_entry(raw: str, base_dir: Path) -> PaperRecord:
    candidate = raw.strip().strip("\"'")
    path = Path(candidate)
    if path.suffix.lower() == ".pdf":
        resolved = _resolve_pdf_input_path(path, base_dir)
        if resolved is None:
            raise FileNotFoundError(f"PDF file not found: {candidate}")
        paper_id = _build_local_pdf_id(resolved)
        return PaperRecord(
            arxiv_id=paper_id,
            normalized_id=_normalize_identifier(paper_id),
            source_url=str(resolved),
            input_kind="local_pdf",
            original_input=raw,
            pdf_path=resolved,
        )

    arxiv_id, source_url = normalize_arxiv_entry(candidate)
    return PaperRecord(
        arxiv_id=arxiv_id,
        normalized_id=arxiv_id.replace(".", "_"),
        source_url=source_url,
        original_input=raw,
    )


def _build_local_pdf_id(pdf_path: Path) -> str:
    match = ARXIV_ID_RE.search(pdf_path.stem)
    if match:
        return match.group("id")
    return f"pdf_{_normalize_identifier(pdf_path.stem)}"


def _normalize_identifier(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip())
    normalized = normalized.strip("._-")
    return normalized or "paper"


def _is_pdf_bytes(data: bytes) -> bool:
    return data.lstrip().startswith(b"%PDF-")


def _resolve_pdf_input_path(path: Path, base_dir: Path) -> Path | None:
    candidates = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.append(path)
        candidates.append(base_dir / path)

    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


def _detect_legacy_pdf_source_dir(source_dir: Path) -> Path | None:
    tex_files = sorted(source_dir.glob("*.tex"))
    if len(tex_files) != 1:
        return None
    candidate = tex_files[0]
    try:
        prefix = candidate.read_bytes()[:32]
    except OSError:
        return None
    if _is_pdf_bytes(prefix):
        return candidate
    return None


def _throttle_downloads() -> None:
    global _LAST_DOWNLOAD_AT
    now = time.time()
    wait_for = DOWNLOAD_THROTTLE_SECONDS - (now - _LAST_DOWNLOAD_AT)
    if wait_for > 0:
        time.sleep(wait_for)
    _LAST_DOWNLOAD_AT = time.time()
