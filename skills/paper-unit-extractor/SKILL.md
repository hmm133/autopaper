---
name: paper-unit-extractor
description: Extract relation-oriented paper units from markdown so later graph construction can compare research questions, claims, methods, conclusions, evidence, assumptions, limitations, scope, and resources with explicit traceable support.
---

# Paper Unit Extractor

Use this skill to transform one paper markdown file into a structured unit JSON that is optimized for later cross-paper relation inference.

The goal is not generic summarization.

The goal is to extract a stable intermediate representation that makes later paper-to-paper and unit-to-unit comparison easier, cheaper, and less ambiguous.

## Required Top-Level Output

The output should contain:

- `paper_metadata`
- `units`

`paper_metadata` should be lightweight and only include fields that are explicitly available or strongly recoverable from the paper:

- `title`
- `authors`
- `year`
- `venue`
- `arxiv_id`
- `doi`
- `source_url`
- `markdown_path`

If a field is missing, use `null` or `[]` as appropriate. Do not hallucinate.

## Required Unit Types

- `research_question`
- `core_claim`
- `formal_conclusion`
- `method`
- `evidence`
- `limitation`
- `assumption`
- `scope`
- `resource`

## Core Principle

Extract units for relation building, not for archival completeness.

Every extracted unit should help answer at least one later question such as:

- Do these two papers solve the same or adjacent research question?
- Does one paper support, extend, apply, or conflict with another?
- Are two methods comparable, inherited, or meaningfully different?
- Does one paper address a limitation or assumption stated by another?
- Do two papers rely on similar evidence or comparable benchmarks?
- Are they using or producing the same benchmark, dataset, model, or code artifact?

If a candidate unit is too weak to support later relation reasoning, do not extract it.

## Granularity Rules

- Use middle granularity.
- Each unit should express one coherent academic idea, usually around one compact statement rather than one sentence fragment or one full section summary.
- `summary` should stay short.
- `text` should be clearly more detailed than `summary`.
- `text` may use 1 to 3 sentences when needed so the substance of the idea is preserved.
- Do not force `text` to be overly short, but do not let it expand into a long paragraph.
- Prefer one stronger unit over several brittle fragments.
- Do not decompose the paper sentence by sentence.
- Do not produce vague whole-paper blurbs.

## Cardinality Rules

- Never assume only one unit exists for a given type.
- Every type may contain `0..N` units.
- Extract multiple units only when they are genuinely distinct and relation-relevant.
- Merge near-duplicates.
- Keep separate units when they could support different future relations.

## Type Definitions

### `research_question`

- The concrete research question, target problem, or study objective the paper addresses.
- It should say what is being solved, explained, tested, or improved.
- Extract more than one only when the paper clearly tackles multiple distinct questions.

### `core_claim`

- The paper's main thesis-level claims or contribution assertions.
- These are the statements the paper wants the reader to take seriously before validation details.
- A paper may have multiple distinct claims.

### `formal_conclusion`

- The specific findings the paper presents as established after analysis, experiments, proofs, or evaluation.
- These are more evidence-bound than `core_claim`.
- Keep them separate from claims whenever the paper distinguishes proposal from validated finding.

### `method`

- The proposed method, framework, algorithm, system design, modeling strategy, or structured solution.
- Extract method units that are comparison-worthy across papers.
- Ignore low-level implementation trivia unless it changes later relation reasoning.

### `evidence`

- A concrete piece of support for one or more claims or conclusions.
- This may come from experiments, benchmarks, ablations, figures, tables, case studies, simulations, or theoretical proof structure.
- Every `evidence` unit should make clear what it supports.
- Use `supports` to point to the relevant `core_claim` and/or `formal_conclusion` IDs.
- Use `evidence_type` when possible:
  - `experimental`
  - `theoretical`
  - `simulation`
  - `case_study`
  - `benchmark`
  - `ablation`
  - `figure_or_table`

Do not split evidence into raw numbers unless the numeric contrast itself is relation-relevant.

### `limitation`

- An explicit limitation, boundary condition, weakness, tradeoff, or uncovered case stated by the authors.
- Only extract author-stated limitations.
- Do not invent reviewer-style criticisms.

### `assumption`

- A prerequisite or assumption under which the method, argument, or conclusion is meant to hold.
- Extract assumptions that affect comparability or explain later agreement and disagreement between papers.

### `scope`

- The task setting, domain, environment, data regime, benchmark context, or study setting in which the work operates.
- This is mainly a comparison and filtering unit, not a catch-all summary.
- Prefer `scope_data` when obvious, such as task, domain, dataset, environment, or benchmark.

### `resource`

- A reusable artifact that the paper uses or produces.
- Preserve the concrete resource name whenever the paper provides one.
- If helpful, use:
  - `resource_name` for the specific benchmark, dataset, model, codebase, or tool name
  - `resource_type` such as `dataset`, `benchmark`, `model`, `code`, `software`, `tool`
  - `resource_role` such as `used` or `produced`

Only extract resources that are relation-relevant.

## Unit Structure Rules

Each unit should contain:

- `id`
- `type`
- `text`
- `summary`
- `sources`

Optional fields may include:

- `supports`
- `evidence_type`
- `scope_data`
- `resource_name`
- `resource_type`
- `resource_role`

## Evidence Traceability Rules

Every unit must preserve traceable support through the `sources` array.

Each source item should include:

- `section_hint`
- `quote`

Keep quotes short and targeted. Near-quote is acceptable when needed for cleanup.

## Cross-Reference Rule For `evidence`

When extracting `evidence` units:

- Prefer linking them to concrete `core_claim` or `formal_conclusion` IDs through `supports`.
- Only reference IDs that actually exist in the previously extracted claim/conclusion set for the same paper.
- If no valid target exists, use an empty array rather than fabricating links.

## Output Discipline

- Return valid JSON only.
- Follow the schema exactly.
- If a type is not present, output no unit for that type.
- Do not emit empty optional fields just to fill space.
- For `resource`, prefer concrete names over generic descriptions whenever the paper states them.
- Do not hallucinate metadata, results, or resources.
- Ignore references and bibliography.
- Favor precision over coverage.

## References

- Shared contract: [`pipeline-contract.md`](D:\研究生\papers\实验\autopaper\skills\shared-references\pipeline-contract.md)
- Unit schema: [`paper_units.schema.json`](D:\研究生\papers\实验\autopaper\schemas\paper_units.schema.json)
