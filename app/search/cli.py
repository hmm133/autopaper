from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from app.config import load_llm_config
from app.search.schemas import SearchRequest
from app.search.workflow import run_search_workflow


def build_search_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autopaper search",
        description="Search arXiv, screen relevant papers, and export an autopaper-ready arXiv list.",
    )
    parser.add_argument("topic_description", help="Natural language topic description.")
    parser.add_argument("--start-date", default=None, help="Optional metadata field. Currently not injected into the arXiv query.")
    parser.add_argument("--end-date", default=None, help="Optional metadata field. Currently not injected into the arXiv query.")
    parser.add_argument(
        "--categories",
        nargs="*",
        default=[],
        help="Optional metadata field. Currently not injected into the arXiv query.",
    )
    parser.add_argument(
        "--authors",
        nargs="*",
        default=[],
        help="Optional metadata field. Currently not injected into the arXiv query.",
    )
    parser.add_argument(
        "--search-intent",
        default=None,
        help="Optional search purpose, e.g. latest methods, baselines, datasets, limitations, or survey building.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=50,
        help="Number of latest arXiv results to pull into the candidate pool before LLM screening.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Maximum number of screened papers to keep. If omitted, keep all papers judged relevant.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to a timestamped folder under data/outputs/search/.",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/cache/search",
        help="Directory for search caches and retrieval artifacts.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the runtime config JSON containing LLM settings. If omitted, query planning and relevance screening use fallback logic.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_search_parser()
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir()
    request = SearchRequest(
        topic_description=args.topic_description,
        start_date=args.start_date,
        end_date=args.end_date,
        categories=args.categories,
        authors=args.authors,
        search_intent=args.search_intent,
        candidate_limit=args.candidate_limit,
        top_k=args.top_k,
    )
    llm_config = None
    if args.config:
        llm_config = load_llm_config(Path(args.config))
    else:
        default_config = Path("config/autopaper_config.json")
        if default_config.exists():
            llm_config = load_llm_config(default_config)
    result = run_search_workflow(
        request=request,
        output_dir=output_dir,
        cache_dir=Path(args.cache_dir),
        llm_config=llm_config,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("data/outputs") / f"run_{stamp}"
