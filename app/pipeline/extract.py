from __future__ import annotations

import json
from pathlib import Path

from app.config import LLMConfig
from app.models.paper import PaperRecord
from app.prompts import build_unit_extraction_messages, load_skill_text
from app.providers.base import LLMMessage
from app.providers.factory import build_provider

UNIT_GROUPS = {
    "semantic_core": [
        "research_question",
        "core_claim",
        "method",
        "formal_conclusion",
        "scope",
    ],
    "evidence_boundary": [
        "evidence",
        "assumption",
        "limitation",
        "resource",
    ],
}


def extract_paper_units(record: PaperRecord, output_dir: Path, llm_config: LLMConfig) -> Path:
    extraction_dir = output_dir / "extractions"
    extraction_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = output_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    extraction_path = extraction_dir / f"{record.normalized_id}.json"

    if not record.markdown_path:
        raise ValueError("record.markdown_path is required before extraction.")

    markdown_text = Path(record.markdown_path).read_text(encoding="utf-8")
    markdown_text = _shrink_markdown_for_extraction(markdown_text)
    skill_text = load_skill_text(Path("skills/paper-unit-extractor/SKILL.md"))
    full_schema = json.loads(Path("schemas/paper_units.schema.json").read_text(encoding="utf-8"))
    provider = build_provider(llm_config)
    merged_units: list[dict] = []
    prior_units: list[dict] = []
    paper_metadata = {
        "title": record.title,
        "authors": [],
        "year": None,
        "venue": None,
        "arxiv_id": record.arxiv_id,
        "doi": None,
        "source_url": record.source_url,
        "markdown_path": str(record.markdown_path),
    }

    for group_name, unit_types in UNIT_GROUPS.items():
        schema = _build_group_schema(full_schema, unit_types)
        raw_messages = build_unit_extraction_messages(
            record=record,
            markdown_text=markdown_text,
            skill_text=skill_text,
            schema=schema,
            unit_types=unit_types,
            group_name=group_name,
            prior_units=prior_units,
        )
        messages = [LLMMessage(**message) for message in raw_messages]
        payload = provider.create_json(messages, schema)
        (debug_dir / f"{record.normalized_id}_{group_name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        group_units = payload.get("units", [])
        metadata = payload.get("paper_metadata") or {}
        for key in ("title", "year", "venue", "arxiv_id", "doi", "source_url", "markdown_path"):
            if metadata.get(key) not in (None, "", []):
                paper_metadata[key] = metadata[key]
        if metadata.get("authors"):
            paper_metadata["authors"] = metadata["authors"]
        merged_units.extend(group_units)
        prior_units.extend(group_units)

    payload = {
        "paper_id": record.arxiv_id,
        "paper_metadata": paper_metadata,
        "status": "extracted",
        "unit_count": len(merged_units),
        "units": merged_units,
    }

    extraction_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return extraction_path


def ensure_placeholder_extraction(record: PaperRecord, output_dir: Path) -> Path:
    extraction_dir = output_dir / "extractions"
    extraction_dir.mkdir(parents=True, exist_ok=True)
    extraction_path = extraction_dir / f"{record.normalized_id}.json"

    if not extraction_path.exists():
        extraction = {
            "paper_id": record.arxiv_id,
            "paper_metadata": {
                "title": record.title,
                "authors": [],
                "year": None,
                "venue": None,
                "arxiv_id": record.arxiv_id,
                "doi": None,
                "source_url": record.source_url,
                "markdown_path": None,
            },
            "units": [],
            "status": "placeholder",
            "expected_unit_types": [
                "research_question",
                "core_claim",
                "method",
                "formal_conclusion",
                "evidence",
                "assumption",
                "limitation",
                "scope",
                "resource",
            ],
        }
        extraction_path.write_text(
            json.dumps(extraction, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return extraction_path


def _shrink_markdown_for_extraction(markdown_text: str, max_chars: int = 18000) -> str:
    if len(markdown_text) <= max_chars:
        return markdown_text

    parts = markdown_text.split("\n## ")
    kept: list[str] = []
    total = 0

    for index, part in enumerate(parts):
        rebuilt = part if index == 0 else "## " + part
        lower = rebuilt.lower()
        if any(
            key in lower
            for key in (
                "abstract",
                "introduction",
                "conclusion",
                "discussion",
                "result",
                "experiment",
                "evaluation",
                "case study",
                "[caption]",
                "[figure:",
            )
        ):
            kept.append(rebuilt)
            total += len(rebuilt)
        if total >= max_chars:
            break

    condensed = "\n\n".join(kept).strip()
    if condensed:
        return condensed[:max_chars]
    return markdown_text[:max_chars]


def _build_group_schema(full_schema: dict, unit_types: list[str]) -> dict:
    schema = json.loads(json.dumps(full_schema))
    schema["properties"]["units"]["items"]["properties"]["type"]["enum"] = unit_types
    return schema
