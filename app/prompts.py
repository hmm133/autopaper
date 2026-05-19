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
    prior_units: list[dict] | None = None,
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
            "- summary should be short and compressed.",
            "- text should be fuller, more explicit, and more informative than summary.",
            "- text may use 1-3 sentences when needed so the idea is preserved with enough detail.",
            "- Do not over-compress text into a short label, but do not let it become a long paragraph dump.",
            "- Prefer one stronger unit over many fragmented weak units.",
            "- A paper may contain multiple units of the same type.",
            "- If two units would support different future graph relations, keep them separate.",
            "- Do not output unit types outside this group's allowed list.",
            "- For this run, keep the output concise and relation-focused.",
            "- Usually extract at most 1-3 units per type unless the paper clearly requires more.",
            "- Every unit must include sources with section_hint and quote.",
            "- Use exact or near-exact quotations for source quotes.",
            "- Preserve stable IDs because later stages will reference them.",
            "- Ignore references and bibliography.",
            "- If extracting evidence units, use supports to point to concrete core_claim or formal_conclusion IDs when possible.",
            "- Omit optional fields when they are not needed. Do not emit null-filled filler fields.",
            "- For resource units, preserve the concrete benchmark, dataset, model, codebase, or tool name when it is explicitly given.",
            "- Output a single json object only.",
            "",
            "JSON schema:",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "",
            "Previously extracted units for this paper:",
            json.dumps(
                [
                    {
                        "id": unit.get("id"),
                        "type": unit.get("type"),
                        "summary": unit.get("summary"),
                        "text": unit.get("text"),
                    }
                    for unit in (prior_units or [])
                ],
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "Example JSON shape:",
            json.dumps(
                {
                    "paper_id": record.arxiv_id,
                    "paper_metadata": {
                        "title": record.title or "",
                        "authors": [],
                        "year": None,
                        "venue": None,
                        "arxiv_id": record.arxiv_id,
                        "doi": None,
                        "source_url": record.source_url,
                        "markdown_path": str(record.markdown_path),
                    },
                    "status": "extracted",
                    "unit_count": 2,
                    "units": [
                        {
                            "id": f"{record.normalized_id}_question_1",
                            "type": unit_types[0],
                            "text": "Example research question text with enough detail to preserve the actual objective, setting, and scope of the paper rather than reducing it to a short label.",
                            "summary": "Example problem summary",
                            "sources": [
                                {
                                    "section_hint": "Abstract",
                                    "quote": "Example quote"
                                }
                            ]
                        },
                        {
                            "id": f"{record.normalized_id}_claim_1",
                            "type": unit_types[min(1, len(unit_types) - 1)],
                            "text": "Example claim text with enough detail to preserve the substance of the contribution so later relation inference can compare meaning, not just labels.",
                            "summary": "Example claim summary",
                            "sources": [
                                {
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
            "- Determine micro relations first, then derive the macro relation from them.",
            "- Macro relation must be supported by the returned micro relations.",
            "- Use scope and assumption mainly as comparability constraints, not as high-volume edge sources.",
            "- Use evidence units to validate, strengthen, weaken, or block stronger claim-level or conclusion-level relations.",
            "- If only comparable_validation is justified, usually leave the macro relation empty.",
            "",
            "Skill:",
            skill_text,
        ]
    )

    user_prompt = "\n".join(
        [
            "Task:",
            "Compare the two papers below and infer whether a meaningful cross-paper relation exists.",
            "Work in this order:",
            "1. Identify only the strongest justified cross-paper micro relations.",
            "2. If and only if those micro relations support a paper-level summary, derive one macro relation.",
            "If no strong relation exists, output has_meaningful_relation=false and micro_relations=[].",
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
            "Preferred comparison priorities:",
            "1. research_question <-> research_question",
            "2. core_claim <-> core_claim",
            "3. method <-> method",
            "4. formal_conclusion <-> formal_conclusion",
            "5. evidence <-> evidence",
            "6. limitation <-> method/core_claim/formal_conclusion",
            "7. resource <-> resource",
            "",
            "Important interpretation rules:",
            "- Do not confuse topical overlap with support.",
            "- Do not emit conflict unless the compared units are genuinely comparable and materially disagree.",
            "- Prefer parallel or no edge when scope or assumptions differ too much.",
            "- Resource overlap alone is usually not enough for a strong macro relation.",
            "",
            "JSON schema:",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "",
            "Example no-relation JSON:",
            json.dumps(
                {
                    "paper_a": left.get("paper_id", ""),
                    "paper_b": right.get("paper_id", ""),
                    "micro_relations": [],
                    "decision": {
                        "has_meaningful_relation": False,
                        "macro_relation": None,
                        "confidence": 0.18,
                        "rationale": "The papers are broadly adjacent but the extracted units do not support a concrete cross-paper relation."
                    }
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
                    "micro_relations": [
                        {
                            "source_unit_id": "paper_b_method_1",
                            "target_unit_id": "paper_a_method_1",
                            "relation": "extend",
                            "confidence": 0.84,
                            "rationale": "The later method adopts the earlier framing and expands it into a stronger pipeline.",
                            "evidence_refs": ["paper_b:paper_b_method_1", "paper_a:paper_a_method_1"]
                        }
                    ],
                    "decision": {
                        "has_meaningful_relation": True,
                        "macro_relation": "extend",
                        "confidence": 0.81,
                        "rationale": "Paper B extends Paper A by building on a similar problem and adding a stronger method and validation structure."
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "Example validation-only JSON:",
            json.dumps(
                {
                    "paper_a": left.get("paper_id", ""),
                    "paper_b": right.get("paper_id", ""),
                    "micro_relations": [
                        {
                            "source_unit_id": "paper_a_evidence_1",
                            "target_unit_id": "paper_b_evidence_2",
                            "relation": "comparable_validation",
                            "confidence": 0.72,
                            "rationale": "Both papers validate related findings using strongly comparable benchmark structure and evaluation framing.",
                            "evidence_refs": ["paper_a:paper_a_evidence_1", "paper_b:paper_b_evidence_2"]
                        }
                    ],
                    "decision": {
                        "has_meaningful_relation": False,
                        "macro_relation": None,
                        "confidence": 0.41,
                        "rationale": "The papers have comparable validation structure, but this alone does not justify a stronger paper-level macro relation."
                    }
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
        source_refs = []
        for idx, source in enumerate(unit.get("sources", []), start=1):
            source_refs.append(
                {
                    "ref_id": f"{payload.get('paper_id', 'paper')}:{unit['id']}:e{idx}",
                    "section_hint": source.get("section_hint"),
                    "quote": source.get("quote"),
                }
            )
        units.append(
            {
                "id": unit["id"],
                "type": unit["type"],
                "summary": unit.get("summary"),
                "text": unit.get("text"),
                "supports": unit.get("supports", []),
                "evidence_type": unit.get("evidence_type"),
                "scope_data": unit.get("scope_data"),
                "resource_name": unit.get("resource_name"),
                "resource_type": unit.get("resource_type"),
                "resource_role": unit.get("resource_role"),
                "sources": source_refs,
            }
        )
    return {
        "paper_id": payload.get("paper_id"),
        "title": (payload.get("paper_metadata") or {}).get("title"),
        "paper_metadata": payload.get("paper_metadata"),
        "units": units,
    }
