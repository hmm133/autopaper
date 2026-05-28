from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from app.config import LLMConfig
from app.prompts import load_skill_text
from app.providers.base import LLMMessage
from app.providers.factory import build_provider
from app.search.schemas import QueryPlan, SearchRequest


def build_query_plan(
    request: SearchRequest,
    llm_config: LLMConfig | None,
    output_dir: Path,
) -> QueryPlan:
    planner_dir = output_dir / "query_plan"
    planner_dir.mkdir(parents=True, exist_ok=True)

    if llm_config is None:
        plan = _fallback_plan(request)
        _write_plan(plan, planner_dir)
        return plan

    schema = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "literature_query_plan.schema.json").read_text(encoding="utf-8"))
    skill_text = load_skill_text(Path("skills/research-question-query-builder/SKILL.md"))
    provider = build_provider(llm_config)
    fallback = _fallback_plan(request)
    try:
        messages = _build_messages(request, skill_text, schema)
        payload = provider.create_json([LLMMessage(**message) for message in messages], schema)
        plan = _parse_plan(request, payload)
        if not plan.query.strip():
            plan.query = fallback.query
        if not plan.rationale.strip():
            plan.rationale = fallback.rationale
        if not plan.date_end:
            plan.date_end = fallback.date_end
        if not plan.abstract_topic:
            plan.abstract_topic = fallback.abstract_topic
        if not plan.author_filters:
            plan.author_filters = fallback.author_filters
        _write_plan(plan, planner_dir)
        return plan
    except Exception:
        fallback.fallback_used = True
        _write_plan(fallback, planner_dir)
        return fallback


def _build_messages(request: SearchRequest, skill_text: str, schema: dict) -> list[dict[str, str]]:
    effective_end = request.end_date or datetime.now().strftime("%Y-%m-%d")
    user_payload = {
        "topic_description": request.topic_description,
        "start_date": request.start_date,
        "end_date": effective_end,
        "categories": request.categories,
        "authors": request.authors,
        "search_intent": request.search_intent,
        "candidate_limit": request.candidate_limit,
        "top_k": request.top_k,
    }
    system_prompt = "\n".join(
        [
            "You are an arXiv query planning engine for question-driven literature search.",
            "Your job is to extract one simple topic phrase for broad arXiv retrieval.",
            "The query must be a short English phrase, not a Boolean expression.",
            "Do not include category filters, date filters, author filters, field prefixes, or parentheses in the query.",
            "Return valid json only.",
            "",
            "Skill:",
            skill_text,
        ]
    )
    user_prompt = "\n".join(
        [
            "Task:",
            "Create a query plan for arXiv search.",
            "Extract the core research theme and produce one plain arXiv query phrase.",
            "The query should be broad enough for recall and simple enough to avoid search brittleness.",
            "",
            "Input:",
            json.dumps(user_payload, ensure_ascii=False, indent=2),
            "",
            "JSON schema:",
            json.dumps(schema, ensure_ascii=False, indent=2),
        ]
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _parse_plan(request: SearchRequest, payload: dict) -> QueryPlan:
    query = _sanitize_simple_query(str(payload.get("query") or ""))
    if not query:
        query = _fallback_simple_query(request.topic_description)
    return QueryPlan(
        topic_description=request.topic_description,
        normalized_topic=_clean_text(str(payload.get("normalized_topic") or request.topic_description)),
        abstract_topic=_clean_text(str(payload.get("abstract_topic") or request.topic_description)),
        search_intent=_clean_text(str(payload.get("search_intent") or request.search_intent or "general literature discovery")),
        categories=_clean_list(payload.get("categories")) or list(request.categories),
        date_start=str(payload.get("date_start") or request.start_date or ""),
        date_end=str(payload.get("date_end") or request.end_date or datetime.now().strftime("%Y-%m-%d")),
        author_filters=_clean_list(payload.get("author_filters")) or list(request.authors),
        query=query,
        rationale=_clean_text(str(payload.get("rationale") or "")),
    )


def _fallback_plan(request: SearchRequest) -> QueryPlan:
    end_date = request.end_date or datetime.now().strftime("%Y-%m-%d")
    normalized_topic = _clean_text(request.topic_description)
    abstract_topic = _abstract_topic_phrase(normalized_topic)
    categories = list(request.categories)
    query = _fallback_simple_query(abstract_topic or normalized_topic)
    return QueryPlan(
        topic_description=request.topic_description,
        normalized_topic=normalized_topic,
        abstract_topic=abstract_topic,
        search_intent=_clean_text(request.search_intent or "general literature discovery"),
        categories=categories,
        date_start=request.start_date,
        date_end=end_date,
        author_filters=list(request.authors),
        query=query,
        rationale="Fallback query plan built from topic abstraction because no LLM plan was available.",
        fallback_used=True,
    )

def _derive_topic_terms(text: str, abstract_topic: str, limit: int = 6) -> list[str]:
    phrases: list[str] = []
    lowered = _clean_text(text)
    for part in re.split(r"\bfor\b|\bin\b|\bon\b|\bwith\b|\band\b", lowered, flags=re.IGNORECASE):
        phrase = _clean_text(part)
        if 6 <= len(phrase) <= 80 and phrase not in phrases and phrase != _clean_text(abstract_topic):
            phrases.append(phrase)
        if len(phrases) >= limit:
            break
    return phrases


def _abstract_topic_phrase(text: str) -> str:
    normalized = _clean_text(text)
    replacements = [
        ("how do ", ""),
        ("how can ", ""),
        ("what are ", ""),
        ("what is ", ""),
    ]
    lowered = normalized.lower()
    for source, target in replacements:
        if lowered.startswith(source):
            normalized = target + normalized[len(source):]
            break
    normalized = normalized.rstrip(" ?.")
    return _clean_text(normalized)


def _sanitize_simple_query(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    cleaned = re.sub(r"\b(?:AND|OR|NOT)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:cat|submittedDate|au|abs|ti)\s*:\s*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("(", " ").replace(")", " ")
    cleaned = cleaned.replace("[", " ").replace("]", " ")
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    cleaned = cleaned.replace('"', " ").replace("'", " ")
    cleaned = re.sub(r"[\:\+\=]", " ", cleaned)
    cleaned = _clean_text(cleaned)
    words = cleaned.split()
    if len(words) > 6:
        cleaned = " ".join(words[:6])
    return cleaned


def _fallback_simple_query(text: str) -> str:
    cleaned = _sanitize_simple_query(text)
    if not cleaned:
        return "machine learning"
    topic_terms = _derive_topic_terms(cleaned, cleaned, limit=1)
    if topic_terms:
        return topic_terms[0]
    return " ".join(cleaned.split()[:4])


def _clean_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            item = _clean_text(value)
            if item:
                result.append(item)
    return result


def _clean_text(text: str) -> str:
    return " ".join(str(text).split()).strip()


def _write_plan(plan: QueryPlan, planner_dir: Path) -> None:
    (planner_dir / "query_plan.json").write_text(
        json.dumps(plan.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
