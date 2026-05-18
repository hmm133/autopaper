---
name: latex-to-markdown
description: Convert unpacked arXiv LaTeX source trees into normalized markdown when Codex needs to locate entrypoint tex files, follow included sources, preserve section and evidence traces, and produce downstream-friendly markdown artifacts.
---

# LaTeX To Markdown

Use this skill after source archives have been unpacked.

## Responsibilities

- Locate the paper entrypoint, usually `main.tex` or an equivalent root file.
- Follow `\\input{}` and `\\include{}` chains when building the readable document view.
- Drop irrelevant boilerplate where possible.
- Preserve useful structure:
  - title
  - abstract
  - sections
  - figure captions
  - table captions
  - bibliography markers
- Produce normalized markdown under `data/outputs/.../markdown/`.
- Use the LLM when the source tree has multiple plausible entrypoints or an unusual structure.

## Output Rules

- Keep the markdown readable by both humans and downstream extraction code.
- Preserve source provenance whenever practical.
- Add enough structural hints that extraction can find experiment sections and figure-backed claims later.
- Keep this stage at document normalization level; do not prematurely convert the paper into fine-grained claim graphs.
- Prefer moderate cleaning over aggressive rewriting. Losing too much structure here will damage later attribution.
- Exclude bibliography and reference list sections from the markdown output. They are not primary targets for the current relationship analysis workflow.
- Keep figure and table cues only when they help later extraction of figure-backed assertions.

## References

- Shared contract: [`pipeline-contract.md`](D:\研究生\papers\实验\autopaper\skills\shared-references\pipeline-contract.md)
