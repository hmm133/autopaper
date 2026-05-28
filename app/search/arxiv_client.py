from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path

import arxiv

from app.search.schemas import PaperCandidate, QueryPlan, SearchRequest

ARXIV_REQUEST_DELAY_SECONDS = 3.0
ARXIV_PAGE_SIZE = 100
ARXIV_REQUEST_TIMEOUT_SECONDS = 30
ARXIV_MAX_RETRIES = 3


@dataclass
class ArxivRetrievalResult:
    query: str
    candidates: list[PaperCandidate]
    total_results: int
    pages: int
    page_size: int

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "total_results": self.total_results,
            "pages": self.pages,
            "page_size": self.page_size,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


class ArxivClient:
    def __init__(
        self,
        cache_dir: Path,
        *,
        request_timeout_seconds: int = ARXIV_REQUEST_TIMEOUT_SECONDS,
        max_retries: int = ARXIV_MAX_RETRIES,
        request_delay_seconds: float = ARXIV_REQUEST_DELAY_SECONDS,
        page_size: int = ARXIV_PAGE_SIZE,
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.results_cache_dir = self.cache_dir / "results"
        self.results_cache_dir.mkdir(parents=True, exist_ok=True)
        self.request_timeout_seconds = request_timeout_seconds
        self.max_retries = max_retries
        self.request_delay_seconds = request_delay_seconds
        self.page_size = max(page_size, 1)

    def retrieve(self, request: SearchRequest, query_plan: QueryPlan | None = None) -> ArxivRetrievalResult:
        query = _simple_query(query_plan.query if query_plan is not None else build_arxiv_query(request))
        cache_path = self.results_cache_dir / f"{_cache_key(query, request.candidate_limit)}.json"
        if cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return _result_from_payload(payload)

        client = arxiv.Client(
            page_size=min(max(request.candidate_limit, 1), self.page_size),
            delay_seconds=self.request_delay_seconds,
            num_retries=self.max_retries,
        )
        search = arxiv.Search(
            query=query,
            max_results=max(request.candidate_limit, 1),
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        candidates: list[PaperCandidate] = []
        try:
            for item in client.results(search):
                candidates.append(_to_candidate(item))
                if len(candidates) >= request.candidate_limit:
                    break
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch arXiv results via arxiv library: {exc}") from exc

        result = ArxivRetrievalResult(
            query=query,
            candidates=candidates,
            total_results=len(candidates),
            pages=1 if candidates else 0,
            page_size=min(max(request.candidate_limit, 1), self.page_size),
        )
        cache_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result
def build_arxiv_query(request: SearchRequest) -> str:
    from app.search.query_planner import _fallback_plan

    return _fallback_plan(request).query


def _simple_query(query: str) -> str:
    cleaned = " ".join(str(query).split()).strip()
    return cleaned or "machine learning"


def _to_candidate(item: arxiv.Result) -> PaperCandidate:
    primary_category = getattr(item, "primary_category", None)
    categories = list(getattr(item, "categories", []) or [])
    abstract_url = getattr(item, "entry_id", None)
    pdf_url = getattr(item, "pdf_url", None)
    comment = getattr(item, "comment", None)
    journal_ref = getattr(item, "journal_ref", None)
    doi = getattr(item, "doi", None)

    return PaperCandidate(
        arxiv_id=_strip_version(str(abstract_url or "")),
        title=_clean_text(getattr(item, "title", "") or ""),
        summary=_clean_text(getattr(item, "summary", "") or ""),
        authors=[str(author) for author in getattr(item, "authors", []) or []],
        published=_format_datetime(getattr(item, "published", None)),
        updated=_format_datetime(getattr(item, "updated", None)),
        primary_category=primary_category,
        categories=categories,
        abstract_url=abstract_url,
        pdf_url=pdf_url,
        comment=comment,
        journal_ref=journal_ref,
        doi=doi,
    )


def _result_from_payload(payload: dict) -> ArxivRetrievalResult:
    return ArxivRetrievalResult(
        query=str(payload.get("query") or ""),
        total_results=int(payload.get("total_results") or 0),
        pages=int(payload.get("pages") or 0),
        page_size=int(payload.get("page_size") or 0),
        candidates=[PaperCandidate(**item) for item in payload.get("candidates", [])],
    )

def _strip_version(arxiv_id: str) -> str:
    import re
    match = re.search(r"/abs/([^?#]+)", arxiv_id)
    if match:
        arxiv_id = match.group(1)
    return re.sub(r"v\d+$", "", arxiv_id)


def _clean_text(text: str) -> str:
    return " ".join(str(text).split())


def _format_datetime(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _cache_key(query: str, candidate_limit: int) -> str:
    payload = json.dumps({"query": query, "candidate_limit": candidate_limit}, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
