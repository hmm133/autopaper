from __future__ import annotations

from pathlib import Path
import re
import json

from app.config import LLMConfig
from app.models.paper import PaperRecord
from app.prompts import build_source_analysis_messages, load_skill_text
from app.providers.base import LLMMessage
from app.providers.factory import build_provider

ENTRYPOINT_CANDIDATES = (
    "main.tex",
    "paper.tex",
    "ms.tex",
    "article.tex",
)

SECTION_RE = re.compile(r"\\(section|subsection|subsubsection)\*?\{([^}]*)\}")
ABSTRACT_RE = re.compile(
    r"\\begin\{abstract\}(?P<body>.*?)\\end\{abstract\}",
    re.DOTALL,
)
ABSTRACT_COMMAND_RE = re.compile(
    r"\\abstract\{(?P<body>.*?)\}",
    re.DOTALL,
)
DOC_START_RE = re.compile(r"\\begin\{document\}")
DOC_END_RE = re.compile(r"\\end\{document\}")
APPENDIX_RE = re.compile(r"\\appendix\b")
COMMENT_RE = re.compile(r"(?<!\\)%.*$")
INPUT_RE = re.compile(r"\\(input|include)\{([^}]+)\}")
SECTION_COMMAND_RE = re.compile(r"\\(sub)*section\*?\{")
TITLE_COLOR_RE = re.compile(r"\\textcolor\{[^{}]*\}\{(?P<body>[^{}]*)\}")
TITLE_STYLE_RE = re.compile(r"\\(?:textbf|textit|emph|textrm|textsf|texttt)\{(?P<body>[^{}]*)\}")
TITLE_COMMAND_CANDIDATES = (
    "title",
    "icmltitle",
    "icmltitlerunning",
    "titlerunning",
    "shorttitle",
)
REFERENCES_HEADING_RE = re.compile(
    r"\\(?:bibliography|begin\{thebibliography\}|section\*?\{(?:references|bibliography|acknowledgements?)\})",
    re.IGNORECASE,
)
COMMAND_REPLACEMENTS = {
    r"\&": "&",
    r"\%": "%",
    r"\_": "_",
    r"\#": "#",
}


def locate_entrypoint(
    source_dir: Path,
    record: PaperRecord,
    llm_config: LLMConfig,
    output_dir: Path,
) -> Path:
    tex_files = sorted(source_dir.rglob("*.tex"))
    if not tex_files:
        raise FileNotFoundError(f"No .tex files found in {source_dir}")

    candidate_paths = _rank_entrypoint_candidates(source_dir, tex_files)
    chosen = _choose_entrypoint_with_llm(record, source_dir, candidate_paths, llm_config, output_dir)
    if chosen is not None:
        return chosen
    return candidate_paths[0]


def ensure_placeholder_markdown(record: PaperRecord, output_dir: Path) -> Path:
    markdown_dir = output_dir / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = markdown_dir / f"{record.normalized_id}.md"

    if not markdown_path.exists():
        markdown_path.write_text(
            "\n".join(
                [
                    f"# Paper {record.arxiv_id}",
                    "",
                    f"- Source URL: {record.source_url}",
                    "- Status: placeholder markdown",
                    "",
                    "## TODO",
                    "",
                    "- Download arXiv source archive",
                    "- Unpack source tree",
                    "- Locate LaTeX entrypoint",
                    "- Convert source to normalized markdown",
                ]
            ),
            encoding="utf-8",
        )

    return markdown_path


def build_markdown_from_source(record: PaperRecord, output_dir: Path, llm_config: LLMConfig) -> Path:
    if not record.source_dir:
        raise ValueError("record.source_dir is required before markdown generation.")

    entrypoint = locate_entrypoint(record.source_dir, record, llm_config, output_dir)
    record.entrypoint_path = entrypoint

    markdown_dir = output_dir / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = markdown_dir / f"{record.normalized_id}.md"

    raw_text = _read_tex_tree(entrypoint)
    raw_no_comments = _strip_comments(raw_text)
    title = _extract_title(raw_no_comments) or record.arxiv_id
    record.title = title
    cleaned = _trim_to_document_body(raw_no_comments)
    cleaned = _strip_front_matter(cleaned)
    cleaned = _strip_references_tail(cleaned)

    body_lines = [
        f"# {title}",
        "",
        f"- arXiv ID: {record.arxiv_id}",
        f"- Source URL: {record.source_url}",
        f"- Entrypoint: {entrypoint.relative_to(record.source_dir)}",
        "",
    ]

    abstract = _extract_abstract(cleaned)
    if abstract:
        body_lines.extend(["## Abstract", "", abstract, ""])

    sections = _extract_sections(cleaned)
    if sections:
        for heading, content in sections:
            body_lines.extend([f"## {heading}", "", content, ""])
    else:
        body_lines.extend(["## Raw Body", "", _normalize_tex_text(cleaned), ""])

    markdown_path.write_text("\n".join(body_lines).strip() + "\n", encoding="utf-8")
    return markdown_path


def _strip_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        lines.append(COMMENT_RE.sub("", line))
    return "\n".join(lines)


def _extract_title(text: str) -> str | None:
    for command in TITLE_COMMAND_CANDIDATES:
        body = _extract_command_body(text, command)
        if body is None:
            continue
        cleaned = _clean_title_body(body)
        if cleaned:
            return cleaned
    return None


def _extract_abstract(text: str) -> str | None:
    match = ABSTRACT_RE.search(text)
    if match:
        return _normalize_tex_text(match.group("body")).strip() or None

    match = ABSTRACT_COMMAND_RE.search(text)
    if match:
        return _normalize_tex_text(match.group("body")).strip() or None
    return None


def _extract_sections(text: str) -> list[tuple[str, str]]:
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return []

    sections: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        heading = _normalize_tex_text(match.group(2)).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content = _normalize_tex_text(text[start:end]).strip()
        if content:
            sections.append((heading, content))
    return sections


def _trim_to_document_body(text: str) -> str:
    start_match = DOC_START_RE.search(text)
    if start_match:
        text = text[start_match.end():]

    end_match = DOC_END_RE.search(text)
    if end_match:
        text = text[:end_match.start()]

    appendix_match = APPENDIX_RE.search(text)
    if appendix_match:
        text = text[:appendix_match.start()]

    return text


def _strip_references_tail(text: str) -> str:
    section_matches = list(SECTION_RE.finditer(text))
    for match in section_matches:
        heading = _normalize_tex_text(match.group(2)).strip().lower()
        if heading in {"references", "bibliography", "acknowledgements", "acknowledgments"}:
            return text[:match.start()]

    ref_match = REFERENCES_HEADING_RE.search(text)
    if ref_match:
        return text[:ref_match.start()]

    return text


def _strip_front_matter(text: str) -> str:
    abstract_match = ABSTRACT_RE.search(text) or ABSTRACT_COMMAND_RE.search(text)
    if abstract_match:
        return text[abstract_match.start():]

    section_match = SECTION_RE.search(text)
    if section_match:
        return text[section_match.start():]

    return text


def _unwrap_simple_title_commands(text: str) -> str:
    previous = None
    current = text
    while previous != current:
        previous = current
        current = TITLE_COLOR_RE.sub(r"\g<body>", current)
        current = TITLE_STYLE_RE.sub(r"\g<body>", current)
    return current


def _clean_title_body(text: str) -> str:
    cleaned = text
    cleaned = re.sub(
        r"\\(?:paperlogo|papername|benchmark|agent)\*?(?:\[[^\]]*\])?\{([^{}]*)\}",
        r"\1",
        cleaned,
    )
    cleaned = re.sub(
        r"\\includegraphics\*?(?:\[[^\]]*\])?\{[^}]*\}",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"\\(?:hspace|vspace)\*?(?:\[[^\]]*\])?\{[^}]*\}",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        r"\\raisebox\{[^}]*\}\{",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"\\(?:centering|raggedright|raggedleft|Large|LARGE|large|huge|Huge)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        r"\\(?:thanks|footnote)\{[^{}]*\}",
        " ",
        cleaned,
    )
    cleaned = cleaned.replace("~", " ")
    cleaned = cleaned.replace("%", " ")
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    cleaned = _unwrap_simple_title_commands(cleaned)
    cleaned = _normalize_tex_text(cleaned)
    cleaned = re.sub(r"^\s*[-+]?\d+(?:\.\d+)?(?:em|ex|pt|pc|cm|mm|in)?\s+", "", cleaned)
    cleaned = re.sub(r"\b(?:height|width|linewidth|textwidth)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_command_body(text: str, command: str) -> str | None:
    needle = f"\\{command}"
    start = text.find(needle)
    if start == -1:
        return None

    brace_start = text.find("{", start + len(needle))
    if brace_start == -1:
        return None

    depth = 0
    chars: list[str] = []
    for index in range(brace_start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
            if depth > 1:
                chars.append(char)
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return "".join(chars)
            chars.append(char)
            continue
        if depth >= 1:
            chars.append(char)

    return None


def _normalize_tex_text(text: str) -> str:
    normalized = text
    for source, target in COMMAND_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)

    normalized = normalized.replace("~", " ")
    normalized = re.sub(
        r"\\includegraphics\*?(?:\[[^\]]*\])?\{([^}]*)\}",
        r"\n[figure: \1]\n",
        normalized,
    )
    normalized = re.sub(
        r"\\caption\*?(?:\[[^\]]*\])?\{([^{}]*)\}",
        r"\n[caption] \1\n",
        normalized,
    )
    normalized = re.sub(
        r"\\textcolor\{[^{}]*\}\{([^{}]*)\}",
        r"\1",
        normalized,
    )
    normalized = re.sub(
        r"\\(?:paperlogo|papername|benchmark|agent)\*?(?:\[[^\]]*\])?\{([^{}]*)\}",
        r"\1",
        normalized,
    )
    normalized = re.sub(r"\\twocolumn\s*\[", "", normalized)
    normalized = re.sub(r"\\onecolumn\b", "", normalized)
    normalized = re.sub(r"\\iclrfinalcopy\b", "", normalized)
    normalized = re.sub(r"\\cite[t|p]?\{[^}]*\}", "[citation]", normalized)
    normalized = re.sub(r"\\ref\{[^}]*\}", "[ref]", normalized)
    normalized = re.sub(r"\\label\{[^}]*\}", "", normalized)
    normalized = re.sub(r"\\bibliographystyle\{[^}]*\}", "", normalized)
    normalized = re.sub(r"\\bibliography\{[^}]*\}", "", normalized)
    normalized = re.sub(r"\\maketitle", "", normalized)
    normalized = re.sub(r"\\(?:author|date|affiliation|institute|icmlsetsymbol)\*?(?:\[[^\]]*\])?\{[^{}]*\}", "", normalized)
    normalized = re.sub(r"\\(?:footnotetext|footnote)\*?(?:\[[^\]]*\])?\{[^{}]*\}", "", normalized)
    normalized = re.sub(r"\\(?:renewcommand|setcounter)\*?(?:\[[^\]]*\])?\{[^{}]*\}", "", normalized)
    normalized = re.sub(r"\\begin\{[^}]*\}", "", normalized)
    normalized = re.sub(r"\\end\{[^}]*\}", "", normalized)
    normalized = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}", r"\1", normalized)
    normalized = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", "", normalized)
    normalized = normalized.replace("{", "").replace("}", "")
    normalized = re.sub(r"^\s*\[[Hhtbp!]+\]\s*$", "", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"^\s*\d+mm\s*$", "", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"^\s*\d+(?:\.\d+)?(?:em|ex|pt|pc|cm|mm|in)\s*$", "", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"^\s*[A-Z][A-Z \-]{3,}\s*$", "", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"^\s*[\]\[]\s*$", "", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"\n\s*\n\s*\n+", "\n\n", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return normalized.strip()


def _read_tex_tree(entrypoint: Path, seen: set[Path] | None = None) -> str:
    if seen is None:
        seen = set()

    entrypoint = entrypoint.resolve()
    if entrypoint in seen:
        return ""
    seen.add(entrypoint)

    text = entrypoint.read_text(encoding="utf-8", errors="ignore")

    def replace_include(match: re.Match[str]) -> str:
        raw_target = match.group(2).strip()
        child = _resolve_tex_reference(entrypoint.parent, raw_target)
        if child is None:
            return f"\n[missing-include: {raw_target}]\n"
        return "\n" + _read_tex_tree(child, seen) + "\n"

    return INPUT_RE.sub(replace_include, text)


def _resolve_tex_reference(base_dir: Path, raw_target: str) -> Path | None:
    candidates = []
    target = base_dir / raw_target
    candidates.append(target)
    if target.suffix != ".tex":
        candidates.append(base_dir / f"{raw_target}.tex")

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _rank_entrypoint_candidates(source_dir: Path, tex_files: list[Path]) -> list[Path]:
    ranked = sorted(
        tex_files,
        key=lambda path: (
            0 if path.name.lower() in ENTRYPOINT_CANDIDATES else 1,
            0 if path.parent == source_dir else 1,
            0 if "main" in path.stem.lower() or "paper" in path.stem.lower() or "ms" in path.stem.lower() else 1,
            len(path.parts),
            -path.stat().st_size,
        ),
    )
    return ranked[:12]


def _choose_entrypoint_with_llm(
    record: PaperRecord,
    source_dir: Path,
    candidates: list[Path],
    llm_config: LLMConfig,
    output_dir: Path,
) -> Path | None:
    schema = {
        "type": "object",
        "required": ["entrypoint", "reason"],
        "properties": {
            "entrypoint": {"type": "string"},
            "reason": {"type": "string"},
            "supporting_files": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }
    ingest_skill = load_skill_text(Path("skills/arxiv-batch-ingest/SKILL.md"))
    markdown_skill = load_skill_text(Path("skills/latex-to-markdown/SKILL.md"))
    listing = []
    for path in candidates:
        rel = path.relative_to(source_dir)
        preview = _preview_tex_file(path)
        listing.append(f"{rel}\n---\n{preview}\n")

    messages = build_source_analysis_messages(
        record=record,
        tree_listing=listing,
        ingest_skill_text=ingest_skill,
        markdown_skill_text=markdown_skill,
        schema=schema,
    )
    provider = build_provider(llm_config)
    response = provider.create_json([LLMMessage(**message) for message in messages], schema)
    debug_dir = output_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / f"{record.normalized_id}_entrypoint_choice.json").write_text(
        json.dumps(response, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    rel_path = response.get("entrypoint")
    if not rel_path:
        return None
    candidate = source_dir / rel_path
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def _preview_tex_file(path: Path, max_chars: int = 1200) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"\s+", " ", text)
    return text[:max_chars]
