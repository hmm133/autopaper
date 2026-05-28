from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

from app.config import load_llm_config
from app.pipeline.workflow import run_workflow
from app.utils.progress import ProgressReporter
from app.search.cli import main as search_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autopaper",
        description="Run the autopaper arXiv-to-graph workflow.",
    )
    parser.add_argument(
        "input_txt",
        help="Path to a txt file containing arXiv URLs or IDs.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Base output directory or concrete run directory. Defaults to a timestamped folder under data/outputs/.",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/cache",
        help="Directory for downloaded source archives and unpacked source trees.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the tool config JSON containing API key and model settings.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "search":
        search_main(args_list[1:])
        return

    parser = build_parser()
    args = parser.parse_args(args_list)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir()
    llm_config = load_llm_config(Path(args.config)) if args.config else load_llm_config()
    reporter = ProgressReporter(total_papers=_count_papers(Path(args.input_txt)))

    result = run_workflow(
        input_txt=Path(args.input_txt),
        output_dir=output_dir,
        cache_dir=Path(args.cache_dir),
        llm_config=llm_config,
        reporter=reporter,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("data/outputs") / f"run_{stamp}"


def _count_papers(input_txt: Path) -> int:
    if not input_txt.exists():
        return 0
    count = 0
    for line in input_txt.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


if __name__ == "__main__":
    main()
