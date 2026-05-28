from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class SearchRequest:
    topic_description: str
    start_date: str | None = None
    end_date: str | None = None
    categories: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    search_intent: str | None = None
    candidate_limit: int = 50
    top_k: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchRunManifest:
    request: SearchRequest
    output_dir: Path
    cache_dir: Path
    status: str = "planned"
    stages: list[str] = field(
        default_factory=lambda: [
            "request-validated",
            "arxiv-retrieval",
            "relevance-screening",
            "autopaper-bridge-export",
        ]
    )
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["output_dir"] = str(self.output_dir)
        data["cache_dir"] = str(self.cache_dir)
        data["request"] = self.request.to_dict()
        return data


@dataclass
class SearchContext:
    request: SearchRequest
    output_dir: Path
    cache_dir: Path
    manifest_path: Path | None = None


@dataclass
class PaperCandidate:
    arxiv_id: str
    title: str
    summary: str
    authors: list[str] = field(default_factory=list)
    published: str | None = None
    updated: str | None = None
    primary_category: str | None = None
    categories: list[str] = field(default_factory=list)
    abstract_url: str | None = None
    pdf_url: str | None = None
    comment: str | None = None
    journal_ref: str | None = None
    doi: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RelevanceJudgement:
    paper_id: str
    title: str
    score: float
    rationale: str
    matched_signals: list[str] = field(default_factory=list)
    missing_signals: list[str] = field(default_factory=list)
    method_signals: list[str] = field(default_factory=list)
    dataset_signals: list[str] = field(default_factory=list)
    benchmark_signals: list[str] = field(default_factory=list)
    fallback_used: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScreeningResult:
    request: SearchRequest
    judgements: list[RelevanceJudgement]
    core_papers: list[PaperCandidate]
    strategy: str

    def to_dict(self) -> dict:
        return {
            "request": self.request.to_dict(),
            "strategy": self.strategy,
            "judgements": [item.to_dict() for item in self.judgements],
            "core_papers": [paper.to_dict() for paper in self.core_papers],
        }


@dataclass
class QueryPlan:
    topic_description: str
    normalized_topic: str
    abstract_topic: str
    search_intent: str
    categories: list[str] = field(default_factory=list)
    date_start: str | None = None
    date_end: str | None = None
    author_filters: list[str] = field(default_factory=list)
    query: str = ""
    rationale: str = ""
    fallback_used: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
