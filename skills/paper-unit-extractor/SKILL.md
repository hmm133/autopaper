---
name: paper-unit-extractor
description: Extract structured mid-granularity academic units when Codex needs to turn paper markdown into reusable research problems, settings, claims, methods, conclusions, validation logic, figure-backed assertions, assumptions, and limitations with explicit attribution for each unit.
---

# Paper Unit Extractor

Use this skill to transform per-paper markdown into structured extraction JSON.

## Required Unit Types

- `research_problem`
- `scope_or_setting`
- `core_claim`
- `method`
- `formal_conclusion`
- `validation_logic`
- `figure_backed_assertion`
- `assumption_or_prerequisite`
- `limitation`

## Cardinality Rule

- Never assume there is only one unit per type.
- A paper may contain:
  - multiple claims
  - multiple methods or sub-methods worth tracking
  - multiple conclusions
  - multiple validation logics
  - multiple figure-backed assertions
  - multiple assumptions or limitations
- Extract as many units as are genuinely relation-relevant, but do not fragment the paper into sentence-level trivia.
- If two candidate units are materially the same, merge them.
- If they support different future cross-paper relations, keep them separate.

## Extraction Rules

- Extract only academically meaningful units.
- Avoid sentence-by-sentence decomposition.
- Avoid full-paper vague summaries.
- Keep each unit specific enough for cross-paper comparison.
- Attach evidence for every unit.
- Prefer section-driven extraction over isolated sentence mining.
- Use the paper structure to keep units at a fixed middle granularity.
- If a section is noisy, extract one denser synthesized unit rather than many brittle fragments.

## Type Definitions

### `research_problem`

- What concrete research question or challenge the paper addresses.
- Extract more than one only if the paper clearly tackles multiple distinct problems.
- Do not restate the whole paper; focus on the problem statement itself.

### `scope_or_setting`

- The task setting, domain, scenario, data regime, or formal problem setting in which the paper operates.
- Use this when the setting changes how comparisons with other papers should be interpreted.
- Extract multiple units if the paper studies multiple clearly distinct settings.

### `core_claim`

- The paper's central claims, contributions, or thesis-level assertions.
- Multiple core claims are allowed when the paper makes several distinct contributions.
- Do not collapse unrelated contributions into one vague summary.

### `method`

- The method, framework, algorithm, system design, modeling strategy, or procedural solution proposed or used.
- A paper may have multiple methods if it introduces multiple components that can independently relate to later work.
- Avoid extracting generic implementation details unless they matter for cross-paper comparison.

### `formal_conclusion`

- The final takeaways the paper wants the reader to accept as established.
- A paper may have multiple formal conclusions if it reaches several distinct findings.
- Prefer conclusions that are stable, explicit, and relation-worthy over proof-local or incidental statements.

### `validation_logic`

- The evidence structure used to support claims or conclusions.
- Capture what is being validated, how it is validated, against what baselines or comparisons, and what kind of result pattern matters.
- This is not parameter logging or raw experiment detail dumping.
- Multiple validation logics are expected when different claims are validated in different ways.

### `figure_backed_assertion`

- A claim or conclusion directly supported by a figure, table, ablation, case study result, or reported numeric comparison.
- Extract only assertions that are useful for later relation reasoning.
- Multiple figure-backed assertions are normal.

### `assumption_or_prerequisite`

- Preconditions, modeling assumptions, theoretical assumptions, or operational prerequisites under which the paper's method or conclusion holds.
- Extract them when they affect comparability or explain why two papers may align or differ.
- Multiple assumptions are allowed.

### `limitation`

- Explicitly stated weaknesses, uncovered cases, tradeoffs, or boundaries of the paper.
- These are important because later papers often extend or repair them.
- Extract multiple limitations if they are distinct and relation-relevant.

## Attribution Rules

Each extracted unit should preserve:

- source file
- section hint
- quote or near-quote evidence

Use [`paper_units.schema.json`](D:\研究生\papers\实验\autopaper\schemas\paper_units.schema.json) as the output contract.

## References

- Shared contract: [`pipeline-contract.md`](D:\研究生\papers\实验\autopaper\skills\shared-references\pipeline-contract.md)
- Unit schema: [`paper_units.schema.json`](D:\研究生\papers\实验\autopaper\schemas\paper_units.schema.json)
