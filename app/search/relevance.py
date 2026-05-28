from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import LLMConfig
from app.providers.base import LLMMessage
from app.providers.factory import build_provider
from app.search.prompts import build_relevance_screening_messages
from app.search.schemas import PaperCandidate, RelevanceJudgement, ScreeningResult, SearchRequest

BATCH_SIZE = 8
MAX_REASON_LENGTH = 400


def screen_candidates(
    request: SearchRequest,
    candidates: list[PaperCandidate],
    llm_config: LLMConfig | None,
    output_dir: Path,
) -> ScreeningResult:
    screening_dir = output_dir / "screening"
    screening_dir.mkdir(parents=True, exist_ok=True)

    if not candidates:
        result = ScreeningResult(
            request=request,
            judgements=[],
            core_papers=[],
            strategy="empty",
        )
        _write_screening_artifacts(result, screening_dir)
        return result

    if llm_config is None:
        result = _screen_with_heuristics(request, candidates)
        _write_screening_artifacts(result, screening_dir)
        return result

    result = _screen_with_llm(request, candidates, llm_config)
    _write_screening_artifacts(result, screening_dir)
    return result


def _screen_with_llm(
    request: SearchRequest,
    candidates: list[PaperCandidate],
    llm_config: LLMConfig,
) -> ScreeningResult:
    provider = build_provider(llm_config)
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "literature_relevance.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    judgements: list[RelevanceJudgement] = []

    for batch in _batched(candidates, BATCH_SIZE):
        fallback_batch = {candidate.arxiv_id: _heuristic_judgement(request, candidate) for candidate in batch}
        try:
            raw_messages = build_relevance_screening_messages(request, batch, schema)
            messages = [LLMMessage(**message) for message in raw_messages]
            payload = provider.create_json(messages, schema)
            judgements.extend(_parse_batch_judgements(batch, payload))
        except Exception:
            for fallback in fallback_batch.values():
                fallback.fallback_used = True
                judgements.append(fallback)

    seen_ids = {item.paper_id for item in judgements}
    for candidate in candidates:
        if candidate.arxiv_id not in seen_ids:
            fallback = _heuristic_judgement(request, candidate)
            fallback.fallback_used = True
            judgements.append(fallback)

    judgements = _sort_judgements(judgements)
    core_papers = _select_core_papers(candidates, judgements, request.top_k)
    return ScreeningResult(
        request=request,
        judgements=judgements,
        core_papers=core_papers,
        strategy="llm",
    )


def _screen_with_heuristics(request: SearchRequest, candidates: list[PaperCandidate]) -> ScreeningResult:
    judgements = [_heuristic_judgement(request, candidate) for candidate in candidates]
    core_papers = _select_core_papers(candidates, judgements, request.top_k)
    for item in judgements:
        item.fallback_used = True
    return ScreeningResult(
        request=request,
        judgements=judgements,
        core_papers=core_papers,
        strategy="heuristic",
    )


def _parse_batch_judgements(candidates: list[PaperCandidate], payload: dict) -> list[RelevanceJudgement]:
    by_id = {candidate.arxiv_id: candidate for candidate in candidates}
    results: list[RelevanceJudgement] = []
    for item in payload.get("scores", []):
        if not isinstance(item, dict):
            continue
        paper_id = str(item.get("paper_id") or "").strip()
        candidate = by_id.get(paper_id)
        if candidate is None:
            continue
        score = _normalize_score(item.get("score"))
        results.append(
            RelevanceJudgement(
                paper_id=candidate.arxiv_id,
                title=candidate.title,
                score=score,
                rationale="",
                matched_signals=[],
                missing_signals=[],
                method_signals=[],
                dataset_signals=[],
                benchmark_signals=[],
            )
        )
    return results


def _heuristic_judgement(request: SearchRequest, candidate: PaperCandidate) -> RelevanceJudgement:
    question_tokens = _tokenize(request.topic_description)
    author_tokens = _tokenize(" ".join(request.authors))
    title_tokens = _tokenize(candidate.title)
    summary_tokens = _tokenize(candidate.summary)

    combined_tokens = title_tokens | summary_tokens
    overlap = len((question_tokens | author_tokens) & combined_tokens)
    title_overlap = len((question_tokens | author_tokens) & title_tokens)
    summary_overlap = len((question_tokens | author_tokens) & summary_tokens)

    score = min(
        100.0,
        round(
            overlap * 15.0
            + title_overlap * 10.0
            + summary_overlap * 6.0
            + _category_bonus(candidate.categories, request.categories),
            2,
        ),
    )

    return RelevanceJudgement(
        paper_id=candidate.arxiv_id,
        title=candidate.title,
        score=score,
        rationale=_trim_text("Heuristic match based on title/abstract token overlap with the topic description."),
        matched_signals=[],
        missing_signals=[],
        method_signals=[],
        dataset_signals=[],
        benchmark_signals=[],
        fallback_used=True,
    )


def _select_core_papers(
    candidates: list[PaperCandidate],
    judgements: list[RelevanceJudgement],
    top_k: int | None,
) -> list[PaperCandidate]:
    judgement_by_id = {judgement.paper_id: judgement for judgement in judgements}
    scored_candidates = [
        (candidate, judgement_by_id[candidate.arxiv_id])
        for candidate in candidates
        if candidate.arxiv_id in judgement_by_id
    ]
    ranked = sorted(scored_candidates, key=lambda item: item[1].score, reverse=True)
    if top_k is None:
        return [candidate for candidate, _ in ranked]
    return [candidate for candidate, _ in ranked[:top_k]]


def _write_screening_artifacts(result: ScreeningResult, screening_dir: Path) -> None:
    (screening_dir / "relevance_judgements.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    core_summary = {
        "request": result.request.to_dict(),
        "strategy": result.strategy,
        "core_papers": [paper.to_dict() for paper in result.core_papers],
    }
    (screening_dir / "core_papers.json").write_text(
        json.dumps(core_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_markdown_summary(result, screening_dir)


def _write_markdown_summary(result: ScreeningResult, screening_dir: Path) -> None:
    lines = [
        "# Relevance Screening Summary",
        "",
        f"- strategy: `{result.strategy}`",
        f"- candidate_count: `{len(result.judgements)}`",
        f"- core_count: `{len(result.core_papers)}`",
        "",
        "## Core Papers",
    ]
    score_by_id = {item.paper_id: item.score for item in result.judgements}
    for idx, paper in enumerate(result.core_papers, start=1):
        lines.extend(
            [
                "",
                f"{idx}. {paper.title}",
                f"   - arXiv ID: `{paper.arxiv_id}`",
                f"   - score: `{score_by_id.get(paper.arxiv_id, 0.0):.2f}`",
            ]
        )
    (screening_dir / "summary.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _normalize_score(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if score <= 1.0:
        score *= 100.0
    return max(0.0, min(score, 100.0))

def _trim_text(text: str, limit: int = MAX_REASON_LENGTH) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:limit]


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in re.split(r"[\s,;:/()\-]+", text.lower()):
        token = "".join(ch for ch in token if ch.isalnum())
        if len(token) >= 3:
            tokens.add(token)
    return tokens


def _category_matches(candidate_categories: list[str], request_categories: list[str]) -> bool:
    if not request_categories:
        return True
    candidate = {category.lower() for category in candidate_categories}
    requested = {category.lower() for category in request_categories}
    return bool(candidate & requested)


def _category_bonus(candidate_categories: list[str], request_categories: list[str]) -> float:
    if _category_matches(candidate_categories, request_categories):
        return 10.0
    return 0.0


def _batched(items: list[PaperCandidate], batch_size: int) -> list[list[PaperCandidate]]:
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def _sort_judgements(judgements: list[RelevanceJudgement]) -> list[RelevanceJudgement]:
    return sorted(judgements, key=lambda item: item.score, reverse=True)
