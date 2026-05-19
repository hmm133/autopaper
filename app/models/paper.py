from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class PaperRecord:
    arxiv_id: str
    source_url: str
    normalized_id: str
    input_kind: str = "arxiv"
    original_input: str | None = None
    archive_path: Path | None = None
    source_dir: Path | None = None
    pdf_path: Path | None = None
    entrypoint_path: Path | None = None
    markdown_path: Path | None = None
    extraction_path: Path | None = None
    title: str | None = None
    status: str = "pending"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in (
            "archive_path",
            "source_dir",
            "pdf_path",
            "entrypoint_path",
            "markdown_path",
            "extraction_path",
        ):
            value = data[key]
            data[key] = str(value) if value else None
        return data
