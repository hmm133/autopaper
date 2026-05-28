---
name: research-question-query-builder
description: Convert a natural-language topic description into one simple topic phrase for broad arXiv recall.
---

# Research Topic Query Builder

Use this skill when the search tool needs one simple arXiv search phrase from a user's natural-language topic description.

## Goals

- Preserve the user's actual research intent
- Extract the core research theme
- Prefer one short topic phrase that is broad enough for recall
- Avoid complex Boolean search syntax
- Make the phrase directly usable as a plain arXiv query string

## Rules

1. Normalize the topic description into a concise topic statement.
2. Produce an `abstract_topic` that generalizes the user's wording into a broader research theme.
3. Produce `query` as one short English topic phrase, usually 1 to 4 words, at most 6 words.
4. `query` must not contain:
   - `AND`
   - `OR`
   - `NOT`
   - `cat:`
   - `submittedDate:`
   - `au:`
   - parentheses
   - field prefixes such as `abs:` or `ti:`
5. Do not turn the topic into a sentence or question.
6. Do not enumerate many subtopics in the query.
7. Prefer the most central phrase that can recall related papers broadly.
8. Categories, dates, and authors may still appear elsewhere in the plan, but they should not be encoded into the query string.
9. Produce one simple query phrase and a short rationale.

## Output Expectations

- `normalized_topic` should be short and explicit
- `abstract_topic` should be broader and more general than the original wording
- `query` should be a plain topic phrase such as:
  - `scientific citation`
  - `agent memory`
  - `reinforcement learning`
- `query` should be directly usable against arXiv without extra parsing
- `rationale` should explain why that phrase is the right abstraction briefly
