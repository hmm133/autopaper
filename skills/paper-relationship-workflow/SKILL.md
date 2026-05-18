---
name: paper-relationship-workflow
description: Orchestrate the full autopaper workflow when the tool needs to process many arXiv papers from a txt file, normalize them into markdown, extract structured academic units, and build macro and micro relationship graphs across papers.
---

# Paper Relationship Workflow

Use this skill as the top-level coordinator for the project in this repository.

## Workflow

1. Read [`pipeline-contract.md`](D:\研究生\papers\实验\autopaper\skills\shared-references\pipeline-contract.md) before planning.
2. Treat the repository as a multi-stage pipeline, not a single script.
3. Keep the stages loosely coupled through explicit files and schemas.
4. Prefer producing stable intermediate artifacts:
   - input manifest
   - normalized markdown
   - extracted unit JSON
   - relationship graph JSON
   - candidate pair debug JSON when relation-building is enabled
5. Preserve attribution whenever information is transformed.

## Stage Order

1. Use [`arxiv-batch-ingest`](D:\研究生\papers\实验\autopaper\skills\arxiv-batch-ingest\SKILL.md) for txt parsing, arXiv normalization, downloading, and unpacking.
2. Use [`latex-to-markdown`](D:\研究生\papers\实验\autopaper\skills\latex-to-markdown\SKILL.md) for source tree reading and markdown normalization.
3. Use [`paper-unit-extractor`](D:\研究生\papers\实验\autopaper\skills\paper-unit-extractor\SKILL.md) for structured academic unit extraction.
4. Use [`paper-relation-graph-builder`](D:\研究生\papers\实验\autopaper\skills\paper-relation-graph-builder\SKILL.md) for macro and micro graph construction.

## Project Rules

- Keep input simple: one txt file of arXiv IDs or URLs.
- Build for automation first; interactive prompts are fallback only.
- Prefer deterministic scripts for repetitive file transformation.
- Keep schemas stable and versionable.
- Avoid collapsing macro and micro relations into one undifferentiated graph.
- Do not force every paper into the graph with artificial edges.
- For relation building, allow isolated papers and isolated units.
- For larger batches, use a candidate-filtering stage before LLM comparison to control cost.

## References

- Shared contract: [`pipeline-contract.md`](D:\研究生\papers\实验\autopaper\skills\shared-references\pipeline-contract.md)
- Unit schema: [`paper_units.schema.json`](D:\研究生\papers\实验\autopaper\schemas\paper_units.schema.json)
- Graph schema: [`relationship_graph.schema.json`](D:\研究生\papers\实验\autopaper\schemas\relationship_graph.schema.json)
