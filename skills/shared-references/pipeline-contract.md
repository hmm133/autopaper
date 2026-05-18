# Pipeline Contract

## Goal

Build a deterministic local pipeline with four skill-guided stages:

1. `arxiv-batch-ingest`
2. `latex-to-markdown`
3. `paper-unit-extractor`
4. `paper-relation-graph-builder`

The pipeline should eventually support a simple one-click UX, but the current implementation can start as a CLI.

## Input contract

- Input is a txt file path.
- Each non-empty line contains either:
  - an arXiv URL such as `https://arxiv.org/abs/2501.01234`
  - an arXiv source URL such as `https://arxiv.org/src/2501.01234`
  - a bare arXiv ID such as `2501.01234`

## Extraction contract

Each paper should be reduced to mid-granularity academic units. A paper may yield multiple units of the same type.

Required types:

- research problem
- scope or setting
- core claim
- method
- formal conclusion
- validation logic
- figure-backed assertion
- assumption or prerequisite
- limitation

Do not extract sentence-level trivia or full-document vague summaries.

## Relationship contract

Support a standard label set first:

- support
- conflict
- extend
- parallel
- foundational

Allow additional labels only when the standard set is insufficient.

## Output contract

Produce:

- per-paper normalized markdown
- per-paper structured extraction JSON
- relationship graph JSON with `macro` and `micro` layers

The graph is intended for a dual-view UI:

- left: macro paper graph
- right: selected paper micro graph
- optional toggle: full global micro graph
