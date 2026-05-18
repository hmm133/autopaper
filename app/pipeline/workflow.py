from __future__ import annotations

import json
from pathlib import Path

from app.config import LLMConfig
from app.pipeline.extract import ensure_placeholder_extraction, extract_paper_units
from app.pipeline.graph import build_relationship_graph, ensure_placeholder_graph
from app.pipeline.ingest import prepare_source_tree, read_input_list
from app.pipeline.markdown import build_markdown_from_source, ensure_placeholder_markdown
from app.utils.progress import ProgressReporter


def run_workflow(
    input_txt: Path,
    output_dir: Path,
    cache_dir: Path,
    llm_config: LLMConfig,
    reporter: ProgressReporter | None = None,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    records = read_input_list(input_txt)
    manifest = []
    if reporter:
        reporter.start(str(output_dir))

    for index, record in enumerate(records, start=1):
        try:
            if reporter:
                reporter.paper_stage(index, record.arxiv_id, "download-source")
            record = prepare_source_tree(record, cache_dir)
            if reporter:
                reporter.paper_stage(index, record.arxiv_id, "latex-to-markdown")
            record.markdown_path = build_markdown_from_source(record, output_dir, llm_config)
        except Exception as exc:
            record.status = "ingest-failed"
            record.notes.append(f"Ingest failed: {exc}")
            record.markdown_path = ensure_placeholder_markdown(record, output_dir)
        try:
            if record.status != "ingest-failed":
                if reporter:
                    reporter.paper_stage(index, record.arxiv_id, "extract-paper-units")
                record.extraction_path = extract_paper_units(record, output_dir, llm_config)
            else:
                record.extraction_path = ensure_placeholder_extraction(record, output_dir)
        except Exception as exc:
            record.notes.append(f"Extraction failed: {exc}")
            record.extraction_path = ensure_placeholder_extraction(record, output_dir)
        if record.status == "source-ready":
            record.status = "markdown-ready"
        if record.status == "markdown-ready":
            record.status = "extraction-ready"
        manifest.append(record.to_dict())
        if reporter:
            reporter.paper_done(index, record.arxiv_id, record.status)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    try:
        if reporter:
            reporter.graph_stage("build macro/micro graph")
        graph_path = build_relationship_graph(records, output_dir, llm_config)
    except Exception as exc:
        for record in records:
            record.notes.append(f"Graph build failed: {exc}")
        graph_path = ensure_placeholder_graph(records, output_dir)
    final_status = "extraction-ready" if records and all(
        record.status == "extraction-ready" for record in records
    ) else "partial"
    if reporter:
        reporter.finish(final_status)

    return {
        "input_txt": str(input_txt),
        "output_dir": str(output_dir),
        "cache_dir": str(cache_dir),
        "paper_count": len(records),
        "manifest_path": str(manifest_path),
        "graph_path": str(graph_path),
        "status": final_status,
    }
