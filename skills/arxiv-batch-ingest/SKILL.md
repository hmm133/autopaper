---
name: arxiv-batch-ingest
description: Batch-ingest many arXiv papers when Codex needs to read a txt file of arXiv IDs or URLs, normalize each entry, download the source archive, unpack the source tree, and emit a local manifest for downstream stages.
---

# ArXiv Batch Ingest

Use this skill for the first stage of the autopaper pipeline.

## Responsibilities

- Read a txt file path from the user or workflow.
- Ignore empty lines and comment lines.
- Accept:
  - bare arXiv IDs
  - `/abs/` URLs
  - `/src/` URLs
- Normalize every entry to:
  - `arxiv_id`
  - `source_url`
  - `normalized_id`
- Store downloaded archives and unpacked trees under `data/cache/`.
- Emit a machine-readable manifest for downstream stages.
- Allow the LLM to help interpret ambiguous source trees after download and unpacking.

## Implementation Notes

- Keep download and unpack logic in scripts under `scripts/`.
- Reuse cached archives when present.
- Prefer deterministic filenames based on `normalized_id`.
- Record failures per paper instead of aborting the entire batch.
- Keep the stage narrow: this skill should stop at a usable local source tree and manifest.
- Do not start summarizing or extracting academic relations here.
- Preserve simple status fields so downstream stages can skip failed papers.
- Let code handle network and filesystem operations; let the LLM handle ambiguous source-tree understanding.

## Output

For each paper, prepare:

- `archive_path`
- `source_dir`
- `status`
- `notes`
- `entrypoint_path` only if a later stage has already resolved it

## References

- Shared contract: [`pipeline-contract.md`](D:\研究生\papers\实验\autopaper\skills\shared-references\pipeline-contract.md)
