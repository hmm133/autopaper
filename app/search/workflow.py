from __future__ import annotations

import json
from pathlib import Path

from app.search.arxiv_client import ArxivClient
from app.search.query_planner import build_query_plan
from app.search.relevance import screen_candidates
from app.search.schemas import (
    PaperCandidate,
    SearchContext,
    SearchRequest,
    SearchRunManifest,
)
from app.config import LLMConfig


def run_search_workflow(
    request: SearchRequest,
    output_dir: Path,
    cache_dir: Path,
    llm_config: LLMConfig | None = None,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    _validate_request(request)

    query_plan = build_query_plan(
        request=request,
        llm_config=llm_config,
        output_dir=output_dir,
    )

    candidates_dir = output_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = candidates_dir / "arxiv_candidates.json"
    retrieval_error: str | None = None
    retrieval = None
    try:
        client = ArxivClient(cache_dir=cache_dir)
        retrieval = client.retrieve(request, query_plan=query_plan)
        candidate_payload = retrieval.to_dict()
    except Exception as exc:
        retrieval_error = str(exc)
        candidate_payload = {
            "query": None,
            "total_results": 0,
            "pages": 0,
            "page_size": 0,
            "candidates": [],
            "error": retrieval_error,
        }
    candidate_path.write_text(
        json.dumps(candidate_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = SearchRunManifest(
        request=request,
        output_dir=output_dir,
        cache_dir=cache_dir,
        status="retrieved" if retrieval is not None else "retrieval-failed",
        notes=(
            [
                f"Retrieved {len(retrieval.candidates)} candidate papers from arXiv.",
                "Stage 2 retrieval completed.",
            ]
            if retrieval is not None
            else [
                f"Retrieval failed: {retrieval_error}",
                "Stage 2 completed with fallback placeholder output.",
            ]
        ),
    )
    manifest_path = output_dir / "search_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    context = SearchContext(
        request=request,
        output_dir=output_dir,
        cache_dir=cache_dir,
        manifest_path=manifest_path,
    )
    _write_request_snapshot(context)

    screening = screen_candidates(
        request=request,
        candidates=retrieval.candidates if retrieval is not None else [],
        llm_config=llm_config,
        output_dir=output_dir,
    )
    bridge_dir = output_dir / "bridge"
    bridge_dir.mkdir(parents=True, exist_ok=True)
    bridge_artifacts = _write_autopaper_bridge_artifacts(screening.core_papers, bridge_dir)

    return {
        "status": "retrieved" if retrieval is not None else "retrieval-failed",
        "output_dir": str(output_dir),
        "cache_dir": str(cache_dir),
        "manifest_path": str(manifest_path),
        "candidate_path": str(candidate_path),
        "candidate_count": len(retrieval.candidates) if retrieval is not None else 0,
        "total_results": retrieval.total_results if retrieval is not None else 0,
        "pages": retrieval.pages if retrieval is not None else 0,
        "page_size": retrieval.page_size if retrieval is not None else 0,
        "query": retrieval.query if retrieval is not None else None,
        "query_plan_dir": str(output_dir / "query_plan"),
        "error": retrieval_error,
        "screening_strategy": screening.strategy,
        "core_count": len(screening.core_papers),
        "judgement_count": len(screening.judgements),
        "screening_dir": str(output_dir / "screening"),
        "autopaper_input_txt": str(bridge_artifacts["input_txt"]),
        "autopaper_input_urls_txt": str(bridge_artifacts["input_urls_txt"]),
        "autopaper_input_json": str(bridge_artifacts["input_json"]),
        "request": request.to_dict(),
    }


def _validate_request(request: SearchRequest) -> None:
    topic = request.topic_description.strip()
    if not topic:
        raise ValueError("topic_description must not be empty.")
    if request.candidate_limit <= 0:
        raise ValueError("candidate_limit must be positive.")
    if request.top_k is not None and request.top_k <= 0:
        raise ValueError("top_k must be positive when provided.")
    if request.top_k is not None and request.top_k > request.candidate_limit:
        raise ValueError("top_k must be less than or equal to candidate_limit.")
    if request.start_date and request.end_date and request.start_date > request.end_date:
        raise ValueError("start_date must be earlier than or equal to end_date.")


def _write_request_snapshot(context: SearchContext) -> None:
    snapshot_path = context.output_dir / "search_request.json"
    snapshot_path.write_text(
        json.dumps(context.request.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_autopaper_bridge_artifacts(core_papers: list[PaperCandidate], bridge_dir: Path) -> dict[str, Path]:
    ids_path = bridge_dir / "selected_arxiv_ids.txt"
    urls_path = bridge_dir / "selected_arxiv_urls.txt"
    json_path = bridge_dir / "selected_papers.json"

    ids = [paper.arxiv_id for paper in core_papers if getattr(paper, "arxiv_id", "").strip()]
    urls = [f"https://arxiv.org/abs/{paper_id}" for paper_id in ids]
    payload = [
        {
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "abstract_url": paper.abstract_url or f"https://arxiv.org/abs/{paper.arxiv_id}",
            "pdf_url": paper.pdf_url,
        }
        for paper in core_papers
    ]

    ids_path.write_text("\n".join(ids).strip() + ("\n" if ids else ""), encoding="utf-8")
    urls_path.write_text("\n".join(urls).strip() + ("\n" if urls else ""), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "input_txt": ids_path,
        "input_urls_txt": urls_path,
        "input_json": json_path,
    }
