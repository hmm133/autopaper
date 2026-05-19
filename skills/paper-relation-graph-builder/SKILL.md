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

## Core Principles

Use these principles as the operating frame for relation construction:

- Build relations from substantive academic support.
- Preserve paper independence when the extracted evidence does not justify a stronger connection.
- Keep every accepted edge traceable to explicit unit content and source evidence.
- Distinguish relation type from confidence.
- Use structured unit content rather than only topical resemblance.
- Treat the graph as an analytic structure for reasoning about academic relationships.
- Favor meaningful relations over dense relations.

## Cost Control

- For small batches, full pairwise comparison is acceptable.
- For larger batches, first generate candidate pairs, then run expensive LLM relation inference only on those pairs.
- Allocate deeper comparison effort to paper pairs that are most likely to contain meaningful cross-paper structure.

## Relation-First Interpretation

Start from academic relation hypotheses rather than from a rigid same-type comparison order.

Use the following reasoning frame:

1. What kind of academic relation, if any, seems plausible between these two papers?
2. If that relation were real, which units would best support it?
3. Are those units actually comparable?
4. Is the support strong enough to justify a micro edge?
5. Do the accepted micro edges justify a macro edge?

The relation should determine which unit combinations matter.
The unit types do not determine the relation by themselves.

## Unit Roles

The extracted unit set is not flat. Different unit types play different roles in graph construction.

### Main contribution units

- `research_question`
- `core_claim`
- `method`
- `formal_conclusion`

These units usually express the main intellectual content of the paper.

### Validation units

- `evidence`

These units help determine whether a claim, conclusion, or method relation is academically supported.

Use `evidence` to:

- strengthen a possible relation
- weaken a relation that looks plausible on the surface
- justify `support`
- justify `conflict`
- justify `comparable_validation`
- clarify whether two findings are truly comparable

### Boundary units

- `scope`
- `assumption`
- `limitation`

These units help define the interpretive boundary of a relation.

Use them mainly to:

- decide whether two other units are really comparable
- explain why a stronger relation is blocked
- detect when one paper explicitly addresses a weakness, restriction, or missing capability from another

### Resource units

- `resource`

These units are often important when relations involve:

- benchmark inheritance
- dataset reuse
- model reuse
- codebase reuse
- framework reuse
- evaluation transfer

Resource overlap can be meaningful, but resource overlap alone is usually not enough for a strong macro edge.

## Relation Discovery Procedure

When comparing two papers, use this order of reasoning:

1. Identify the most plausible academic relation candidates.
2. For each candidate relation, search for the most informative supporting unit combinations.
3. Check comparability using `scope` and `assumption`.
4. Use `evidence` to confirm, weaken, or reject the candidate relation.
5. Accept only the strongest justified micro edges.
6. Derive a macro edge only if the accepted micro edges form a coherent paper-level summary.

## High-Value Support Patterns

These are not hard constraints.
They are common high-value support patterns for relation reasoning.

### For `support`

Often supported by:

- `core_claim` -> `core_claim`
- `formal_conclusion` -> `formal_conclusion`
- `evidence` -> `core_claim`
- `evidence` -> `formal_conclusion`
- `method` -> `formal_conclusion`

### For `conflict`

Often supported by:

- `core_claim` -> `core_claim`
- `formal_conclusion` -> `formal_conclusion`
- `evidence` -> `evidence`

Only use when the units are genuinely comparable.

### For `extend`

Often supported by:

- `method` -> `method`
- `core_claim` -> `core_claim`
- `formal_conclusion` -> `formal_conclusion`
- `limitation` -> `method`
- `limitation` -> `core_claim`
- `research_question` -> `method`

The key idea is continuation plus expansion, not mere similarity.

### For `basis`

Often supported by:

- `resource` -> `resource`
- `method` -> `method`
- `research_question` -> `research_question`
- `resource` -> `method`

The key idea is that one paper provides a foundation that another paper materially builds on.

### For `apply`

Often supported by:

- `method` -> `method`
- `resource` -> `resource`
- `core_claim` -> `method`

The key idea is transfer into a new task, domain, or setting.

### For `complement`

Often supported by:

- `core_claim` -> `core_claim`
- `method` -> `method`
- `formal_conclusion` -> `formal_conclusion`

Use when the papers contribute different but compatible parts of a broader picture.

### For `addresses_limitation_of`

Often supported by:

- `limitation` -> `method`
- `limitation` -> `core_claim`
- `limitation` -> `formal_conclusion`

This is one of the most important cross-type relations.
Do not reduce it to same-type matching.

### For `comparable_validation`

Often supported by:

- `evidence` -> `evidence`
- `resource` -> `resource`
- `method` -> `evidence`

This relation is mainly about validation structure, benchmark comparability, or evaluation logic.

## Comparability Rules

Before asserting a strong relation, check whether the compared content is really comparable.

Use these questions:

- Are the papers addressing the same or adjacent object of study?
- Are the claims or conclusions framed at compatible levels?
- Are the methods being compared under compatible conditions?
- Are the benchmarks, datasets, or evaluation settings sufficiently aligned?
- Do scope restrictions make the apparent relation misleading?
- Do assumptions materially change the interpretation?

Use `scope` and `assumption` mainly as:

- comparability constraints
- relation blockers
- explanatory qualifiers

If comparability is weak:

- prefer `parallel`
- or prefer no edge

## Macro Relations

Use this standard paper-level label set:

- `support`
- `conflict`
- `extend`
- `parallel`
- `basis`
- `complement`
- `apply`

Macro edges are summary edges.
They must point back to supporting micro-edge ids.

## Micro Relations

Use this constrained unit-level label set:

- `support`
- `conflict`
- `extend`
- `parallel`
- `basis`
- `complement`
- `apply`
- `addresses_limitation_of`
- `comparable_validation`

Only produce cross-paper micro edges.
Do not emit intra-paper edges in this stage.

## Relation Meaning Rules

### `support`

Use only when:

- the compared content is substantively aligned
- the later or paired paper meaningfully strengthens, confirms, or corroborates the other
- the support is about contribution content, not only topic proximity

### `conflict`

Use only when:

- the units are genuinely comparable
- and the claims, findings, or conclusions materially disagree

### `extend`

Use when:

- one paper keeps the earlier core framing, capability, or problem structure
- and meaningfully expands it with broader scope, stronger method, richer evidence, or stronger performance

### `parallel`

Use when:

- the papers are clearly adjacent
- but none of the stronger relations is justified

### `basis`

Use when:

- one paper provides a conceptual, methodological, benchmark, dataset, framework, or evaluation foundation
- and the other paper materially builds on that foundation

### `complement`

Use when:

- the papers address different but compatible parts of a broader problem
- and they fit together better than they overlap

Use this sparingly.

### `apply`

Use when:

- one paper takes a method, framework, or resource from another paper
- and uses it in a new task, new setting, or new domain

### `addresses_limitation_of`

Use when:

- one paper explicitly identifies a limitation, weakness, missing capability, narrow scope, or unresolved issue
- and another paper directly addresses that limitation through its method, claim, or conclusion

### `comparable_validation`

Use when:

- the papers are strongly comparable at the evaluation or evidence layer
- but the relation is mainly about validation structure rather than substantive support or extension

This relation often helps explain a nearby relation.
By itself it often should not create a strong macro edge.

## Evidence Use Rules

When evaluating a possible relation:

- prefer direct, concrete support over abstract thematic resemblance
- prefer named resources, concrete claims, benchmark results, and explicit limitation-response patterns
- use `evidence` to validate or reject a candidate relation
- if evidence weakens the apparent relation, remove or downgrade the edge

In particular:

- `support` and `conflict` should be stricter when evidence is available
- `comparable_validation` should rely heavily on evidence-level or evaluation-level similarity

## No-Edge Rules

Keep papers and units independent when the extracted evidence indicates separation rather than a stronger structured relation.

Typical cases include:

- the papers are only broadly in the same area
- the terminology overlaps but the academic function differs
- a relation would rely mostly on title similarity or benchmark co-mention
- the compared units are not sufficiently comparable
- the relation would require too much unstated inference
- the relation is weaker than a reasonable human reader would defend

## Macro Aggregation Rules

The macro graph is a summary of the micro graph.

Use these rules:

- A macro edge must be supported by one or more convincing micro edges.
- The supporting micro edges may be heterogeneous. They do not need to come from same-type unit pairings.
- Do not create a macro edge if the micro support is thin, contradictory, or highly uncertain.
- If the only accepted micro edges are `comparable_validation`, usually do not emit a macro edge.
- If the main accepted evidence is that one paper addresses another paper's limitation, the macro edge will often be `extend`.
- If the main accepted evidence is foundational resource or benchmark dependence, the macro edge will often be `basis`.
- If the main accepted evidence is method or framework transfer into a new setting, the macro edge will often be `apply`.
- If multiple strong micro edges consistently point in one direction, summarize with that macro relation.
- If different strong micro edges point toward incompatible macro readings, prefer no macro edge.

## Output Rules

- Emit a graph payload with separate `macro` and `micro` sections.
- Keep the graph data UI-friendly and traceable.
- Keep nodes that have no edges; independence is a valid outcome.
- Do not rely on edge label text being displayed in the final UI.

Use [`relationship_graph.schema.json`](D:\研究生\papers\实验\autopaper\schemas\relationship_graph.schema.json) as the output contract.

## References

- Shared contract: [`pipeline-contract.md`](D:\研究生\papers\实验\autopaper\skills\shared-references\pipeline-contract.md)
- Graph schema: [`relationship_graph.schema.json`](D:\研究生\papers\实验\autopaper\schemas\relationship_graph.schema.json)
