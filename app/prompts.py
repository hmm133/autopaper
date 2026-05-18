from __future__ import annotations

import json
from pathlib import Path

from app.models.paper import PaperRecord


def load_skill_text(skill_path: Path) -> str:
    return skill_path.read_text(encoding="utf-8")


def build_unit_extraction_messages(
    record: PaperRecord,
    markdown_text: str,
    skill_text: str,
    schema: dict,
    unit_types: list[str],
    group_name: str,
) -> list[dict[str, str]]:
    unit_type_lines = [f"{idx + 1}. {unit_type}" for idx, unit_type in enumerate(unit_types)]
    system_prompt = "\n".join(
        [
            "You are an academic paper analysis engine.",
            "Follow the provided skill instructions strictly.",
            "Extract only mid-granularity academic units.",
            "Do not produce sentence-level fragments or vague full-paper summaries.",
            "Return valid json that matches the schema exactly.",
            "Return json only. Do not wrap the json in markdown fences.",
            "Your output must be a single json object.",
            f"You are currently extracting the unit group: {group_name}.",
            "",
            "Skill:",
            skill_text,
        ]
    )

    user_prompt = "\n".join(
        [
            f"Paper ID: {record.arxiv_id}",
            f"Title: {record.title or ''}",
            f"Source URL: {record.source_url}",
            f"Entrypoint: {record.entrypoint_path.name if record.entrypoint_path else ''}",
            "",
            "Task:",
            f"Extract structured academic units for this group only: {group_name}",
            *unit_type_lines,
            "",
            "Rules:",
            "- Keep a middle granularity.",
            "- Prefer one stronger unit over many fragmented weak units.",
            "- A paper may contain multiple units of the same type.",
            "- If two units would support different future graph relations, keep them separate.",
            "- Do not output unit types outside this group's allowed list.",
            "- For this run, keep the output concise and relation-focused.",
            "- Usually extract at most 1-3 units per type unless the paper clearly requires more.",
            "- Every unit must include evidence with source_file, section_hint, and quote.",
            "- source_file should be the LaTeX entrypoint filename unless a better local source is obvious.",
            "- Use exact or near-exact quotations for evidence quotes.",
            "- Ignore references and bibliography.",
            "- Output a single json object only.",
            "",
            "JSON schema:",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "",
            "Example JSON shape:",
            json.dumps(
                {
                    "paper_id": record.arxiv_id,
                    "title": record.title or "",
                    "source_url": record.source_url,
                    "markdown_path": str(record.markdown_path),
                    "status": "extracted",
                    "unit_count": 2,
                    "units": [
                        {
                            "id": f"{record.normalized_id}_problem_1",
                            "type": unit_types[0],
                            "text": "Example research problem text",
                            "summary": "Example problem summary",
                            "evidence": [
                                {
                                    "source_file": record.entrypoint_path.name if record.entrypoint_path else "main.tex",
                                    "section_hint": "Abstract",
                                    "quote": "Example quote"
                                }
                            ]
                        },
                        {
                            "id": f"{record.normalized_id}_claim_1",
                            "type": unit_types[min(1, len(unit_types) - 1)],
                            "text": "Example claim text",
                            "summary": "Example claim summary",
                            "evidence": [
                                {
                                    "source_file": record.entrypoint_path.name if record.entrypoint_path else "main.tex",
                                    "section_hint": "Introduction",
                                    "quote": "Another example quote"
                                }
                            ]
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "Markdown:",
            markdown_text,
        ]
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_source_analysis_messages(
    record: PaperRecord,
    tree_listing: list[str],
    ingest_skill_text: str,
    markdown_skill_text: str,
    schema: dict,
) -> list[dict[str, str]]:
    system_prompt = "\n".join(
        [
            "You are helping a paper-ingestion tool understand an unpacked arXiv LaTeX source tree.",
            "Use the skill instructions as operating constraints.",
            "Choose the most likely LaTeX entrypoint for the paper body.",
            "Prefer the main paper source, not style files, bibliography files, or appendix-only files.",
            "Return valid json that matches the schema exactly.",
            "Return json only. Do not wrap the json in markdown fences.",
            "",
            "ArXiv ingest skill:",
            ingest_skill_text,
            "",
            "LaTeX to markdown skill:",
            markdown_skill_text,
        ]
    )

    user_prompt = "\n".join(
        [
            f"Paper ID: {record.arxiv_id}",
            f"Original input: {record.original_input or ''}",
            f"Source URL: {record.source_url}",
            "",
            "Task:",
            "Inspect the file tree and choose the best entrypoint tex file for reading the paper.",
            "Also provide a short reason and a few supporting files if they look relevant.",
            "Return json only. Do not add explanations outside the json object.",
            "",
            "JSON schema:",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "",
            "Example JSON output:",
            json.dumps(
                {
                    "entrypoint": "main.tex",
                    "reason": "This file declares the title, abstract, and main sections.",
                    "supporting_files": ["sections/introduction.tex", "sections/results.tex"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "File tree:",
            "\n".join(tree_listing),
        ]
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_relationship_inference_messages(
    left: dict,
    right: dict,
    skill_text: str,
    schema: dict,
) -> list[dict[str, str]]:
    left_brief = _compact_units_for_relation(left)
    right_brief = _compact_units_for_relation(right)
    system_prompt = "\n".join(
        [
            "You are an academic cross-paper relationship inference engine.",
            "Follow the provided skill instructions strictly.",
            "Infer relations only when the evidence is meaningful.",
            "If there is no strong cross-paper relation, return has_meaningful_relation=false and an empty micro_relations list.",
            "Return valid json that matches the schema exactly.",
            "Return json only. Do not wrap the json in markdown fences.",
            "Your output must be a single json object.",
            "",
            "Important rules:",
            "- Do not force links between papers.",
            "- Prefer no relation over a speculative relation.",
            "- Use only cross-paper relations.",
            "- Macro relation must be supported by the returned micro relations.",
            "",
            "Skill:",
            skill_text,
        ]
    )

    user_prompt = "\n".join(
        [
            "Task:",
            "Compare the two papers below and infer whether a meaningful cross-paper relation exists.",
            "If yes, output the supported micro relations and one macro relation summary.",
            "If not, output has_meaningful_relation=false and micro_relations=[].",
            "",
            "Macro relation choices:",
            "- support",
            "- conflict",
            "- extend",
            "- parallel",
            "- basis",
            "- complement",
            "- apply",
            "",
            "Micro relation choices:",
            "- support",
            "- conflict",
            "- extend",
            "- parallel",
            "- basis",
            "- complement",
            "- apply",
            "- addresses_limitation_of",
            "- comparable_validation",
            "",
            "JSON schema:",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "",
            "Example no-relation JSON:",
            json.dumps(
                {
                    "paper_a": left.get("paper_id", ""),
                    "paper_b": right.get("paper_id", ""),
                    "decision": {
                        "has_meaningful_relation": False,
                        "macro_relation": None,
                        "confidence": 0.18,
                        "rationale": "The papers are broadly adjacent but the extracted units do not support a concrete cross-paper relation."
                    },
                    "micro_relations": []
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "Example relation JSON:",
            json.dumps(
                {
                    "paper_a": left.get("paper_id", ""),
                    "paper_b": right.get("paper_id", ""),
                    "decision": {
                        "has_meaningful_relation": True,
                        "macro_relation": "extend",
                        "confidence": 0.81,
                        "rationale": "Paper B extends Paper A by building on a similar problem and adding a stronger method and validation structure."
                    },
                    "micro_relations": [
                        {
                            "source_unit_id": "paper_b_method_1",
                            "target_unit_id": "paper_a_method_1",
                            "relation": "extend",
                            "confidence": 0.84,
                            "rationale": "The later method adopts the earlier framing and expands it into a stronger pipeline.",
                            "evidence_refs": ["paper_b:paper_b_method_1", "paper_a:paper_a_method_1"]
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "Paper A:",
            json.dumps(left_brief, ensure_ascii=False, indent=2),
            "",
            "Paper B:",
            json.dumps(right_brief, ensure_ascii=False, indent=2),
        ]
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _compact_units_for_relation(payload: dict) -> dict:
    units = []
    for unit in payload.get("units", []):
        evidence_refs = []
        for idx, evidence in enumerate(unit.get("evidence", []), start=1):
            evidence_refs.append(
                {
                    "ref_id": f"{payload.get('paper_id', 'paper')}:{unit['id']}:e{idx}",
                    "source_file": evidence.get("source_file"),
                    "section_hint": evidence.get("section_hint"),
                    "quote": evidence.get("quote"),
                }
            )
        units.append(
            {
                "id": unit["id"],
                "type": unit["type"],
                "summary": unit.get("summary"),
                "text": unit.get("text"),
                "evidence": evidence_refs,
            }
        )
    return {
        "paper_id": payload.get("paper_id"),
        "title": payload.get("title"),
        "units": units,
    }
