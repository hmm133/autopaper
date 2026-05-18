---
name: paper-relation-graph-builder
description: Build macro and micro relationship graphs when the tool needs to compare extracted paper units, control comparison cost, avoid forced links, and emit a dual-view graph across papers.
---

# Paper Relation Graph Builder

Use this skill after per-paper extraction JSON artifacts exist.

## Goal

Build two views only:

- Macro view:
  - paper-to-paper graph
  - used for high-level structure
- Micro view:
  - unit-to-unit graph across papers
  - used for fine-grained semantic evidence

The micro graph is the primary semantic layer.
The macro graph must be derived from cross-paper unit relations, not invented independently.

## Cost Control

- Do not assume every paper should be compared deeply against every other paper.
- For small batches, full pairwise comparison is acceptable.
- For larger batches, first generate candidate pairs, then run expensive LLM relation inference only on those pairs.
- If evidence is insufficient, keep papers or units disconnected.

## Inference Rules

- Do not force a relation when none is clearly supported.
- Prefer no edge over a weak or speculative edge.
- Every accepted edge must preserve evidence references.
- Separate confidence from relation type.

## Macro Relations

Use this standard paper-level label set:

- `support`
- `conflict`
- `extend`
- `parallel`
- `basis`
- `complement`
- `apply`

Macro edges are summary edges. They must point back to supporting micro-edge ids.

## Micro Relations

Use a constrained unit-level label set that can support the macro view:

- `support`
- `conflict`
- `extend`
- `parallel`
- `basis`
- `complement`
- `apply`
- `addresses_limitation_of`
- `comparable_validation`

Only produce cross-paper micro edges. Do not emit intra-paper edges in this stage.

## Output Rules

- Emit a graph payload with separate `macro` and `micro` sections.
- Keep the graph data UI-friendly and traceable.
- Keep nodes that have no edges; independence is a valid outcome.
- Do not rely on edge label text being displayed in the final UI.

Use [`relationship_graph.schema.json`](D:\研究生\papers\实验\autopaper\schemas\relationship_graph.schema.json) as the output contract.

## References

- Shared contract: [`pipeline-contract.md`](D:\研究生\papers\实验\autopaper\skills\shared-references\pipeline-contract.md)
- Graph schema: [`relationship_graph.schema.json`](D:\研究生\papers\实验\autopaper\schemas\relationship_graph.schema.json)
