# autopaper

`autopaper` is a local paper-analysis tool for batch-processing arXiv papers from a txt file.

It takes a list of arXiv IDs or URLs, downloads each paper's source package, reads the LaTeX source, converts it into normalized markdown, uses an LLM to extract structured academic units, and then builds cross-paper relationship graphs with both macro and micro views.

## What this tool does

Given a txt file of arXiv papers, `autopaper` will:

1. normalize each arXiv URL or ID
2. download the paper source package from arXiv
3. unpack the source tree locally
4. locate the most likely LaTeX entrypoint
5. convert the paper into normalized markdown
6. call an LLM to extract paper units
7. call an LLM again to infer cross-paper relations
8. export graph data and local graph viewers

## Current pipeline

The current workflow is:

1. `txt -> arXiv source archive`
2. `source archive -> normalized markdown`
3. `markdown -> structured paper units`
4. `paper units -> macro + micro relationship graph`
5. `graph json -> local HTML graph viewer`

## Extraction ontology

The current per-paper extraction target contains these nine unit types:

- `research_problem`
- `scope_or_setting`
- `core_claim`
- `method`
- `formal_conclusion`
- `validation_logic`
- `figure_backed_assertion`
- `assumption_or_prerequisite`
- `limitation`

Important rules:

- a paper may contain multiple units of the same type
- the extractor does not assume there is only one claim, method, or conclusion
- units are meant to support later cross-paper relation building

## Relationship graph output

The graph is split into two layers:

- `macro`: paper-to-paper relations
- `micro`: unit-to-unit relations across papers

Each run exports:

- `graph.json`: structured graph data
- `macro_graph.html`: standalone macro graph page
- `micro_graph.html`: standalone micro graph page
- `index.html`: linked local graph viewer
- `macro.mmd` and `micro.mmd`: Mermaid debug exports

## Project layout

- `app/`: Python package for the pipeline, config, providers, and graph export
- `config/`: config template and your local runtime config
- `data/inputs/`: txt input files with arXiv IDs or URLs
- `data/cache/`: downloaded source archives and unpacked source trees
- `data/outputs/`: markdown, extraction, graph, and viewer outputs
- `schemas/`: JSON schemas for extraction and graph artifacts
- `skills/`: local skill documents used as LLM instructions

## Requirements

You need:

- Python 3.10 or newer
- network access for:
  - downloading arXiv source packages
  - calling your configured LLM API
- a valid LLM API key

Current `pyproject.toml` does not declare extra runtime packages because the current implementation uses the Python standard library for the main pipeline.

## Configuration

Copy the example config:

- `config/autopaper_config.example.json`

Create your real local config file at:

- `config/autopaper_config.json`

The required fields are:

- `llm.provider`
- `llm.model`
- `llm.api_key`
- optional `llm.base_url`

Example:

```json
{
  "llm": {
    "provider": "deepseek-compatible",
    "model": "deepseek-v4-flash",
    "api_key": "YOUR_REAL_API_KEY",
    "base_url": "https://api.deepseek.com"
  }
}
```

You can also override the config file path with:

```powershell
python -m app.cli data\inputs\example_arxiv_list.txt --config path\to\config.json
```

Environment override:

- `AUTOPAPER_CONFIG`

If this environment variable is set, it will be used as the config file path.

## Git and privacy

Commit:

- `config/autopaper_config.example.json`
- code, schemas, skills, and safe sample inputs

Do not commit:

- `config/autopaper_config.json`
- real API keys
- `data/cache/`
- `data/outputs/`
- local scratch notes or temporary files

These are already covered in `.gitignore`:

- `config/autopaper_config.json`
- `data/cache/`
- `data/outputs/`
- top-level task notes and local scratch files

## How to prepare input

Create a txt file with one arXiv ID or URL per line.

Example:

```txt
https://arxiv.org/abs/2504.01848
https://arxiv.org/abs/2410.07095
https://arxiv.org/abs/2604.13018
```

The repository already includes an example input file:

- `data/inputs/example_arxiv_list.txt`

## How to run

Run with the module entrypoint:

```powershell
python -m app.cli data\inputs\example_arxiv_list.txt
```

Optional arguments:

- `--output-dir`
- `--cache-dir`
- `--config`

Example:

```powershell
python -m app.cli data\inputs\example_arxiv_list.txt --output-dir data\outputs\my_run --config config\autopaper_config.json
```

If you install the package entrypoint, you can also run:

```powershell
autopaper data\inputs\example_arxiv_list.txt
```

## Output convention

By default, each run writes to a timestamped directory under `data/outputs/`, for example:

```txt
data/outputs/run_20260518_122509
```

This keeps different runs separate.

Typical contents include:

- `manifest.json`
- `markdown/`
- `extractions/`
- `graphs/`

## Main output files

Inside one run directory:

- `manifest.json`: per-paper pipeline summary
- `markdown/*.md`: normalized paper markdown
- `extractions/*.json`: extracted units
- `graphs/graph.json`: graph data
- `graphs/index.html`: local linked viewer
- `graphs/debug/`: candidate-pair and relation debug files

## Current limitations

Current behavior to keep in mind:

- the tool currently works best when arXiv source packages are real LaTeX source packages
- some papers may still use unusual templates that require more markdown normalization support
- LLM extraction and relation inference can occasionally fail due to malformed or truncated JSON API responses
- the graph viewer is functional, but still being iterated visually and interactively

## Development note

In this repository, `skills/*.md` are used as LLM instruction documents.

They are not the runtime framework.

The runtime responsibilities are:

- local code handles files, caching, markdown generation, prompt construction, API calls, and output artifacts
- the LLM handles semantic extraction and relation inference

For GitHub publishing, keep `config/autopaper_config.example.json` in the repo and keep `config/autopaper_config.json` local only.
