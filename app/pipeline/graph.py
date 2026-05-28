from __future__ import annotations

import json
import html
from itertools import combinations
from pathlib import Path

from app.config import LLMConfig
from app.models.paper import PaperRecord
from app.prompts import build_relationship_inference_messages, load_skill_text
from app.providers.base import LLMMessage
from app.providers.factory import build_provider

FULL_PAIRWISE_LIMIT = 8
DEFAULT_TOP_K = 4
SIMILARITY_FIELDS = {
    "research_question": 3.0,
    "core_claim": 2.5,
    "method": 2.0,
    "formal_conclusion": 2.0,
    "evidence": 1.5,
    "scope": 1.0,
    "assumption": 0.8,
    "limitation": 1.0,
    "resource": 1.0,
}


def build_relationship_graph(
    records: list[PaperRecord],
    output_dir: Path,
    llm_config: LLMConfig,
) -> Path:
    graph_dir = output_dir / "graphs"
    graph_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = graph_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    extraction_payloads = _load_extractions(records)
    macro_nodes = _build_macro_nodes(records, extraction_payloads)
    micro_nodes = _build_micro_nodes(extraction_payloads)

    candidate_pairs, comparison_mode = _select_candidate_pairs(extraction_payloads, debug_dir)
    evaluations = _evaluate_candidate_pairs(candidate_pairs, extraction_payloads, output_dir, llm_config, debug_dir)

    micro_edges = []
    macro_edges = []
    for evaluation in evaluations:
        micro_edges.extend(evaluation.get("accepted_micro_edges", []))
        macro_edge = evaluation.get("accepted_macro_edge")
        if macro_edge:
            macro_edges.append(macro_edge)

    payload = {
        "metadata": {
            "paper_count": len(records),
            "comparison_mode": comparison_mode,
            "candidate_pair_count": len(candidate_pairs),
            "evaluated_pair_count": len(evaluations),
            "accepted_macro_edge_count": len(macro_edges),
            "accepted_micro_edge_count": len(micro_edges),
        },
        "macro": {
            "nodes": macro_nodes,
            "edges": macro_edges,
        },
        "micro": {
            "nodes": micro_nodes,
            "edges": micro_edges,
        },
    }

    graph_path = graph_dir / "graph.json"
    graph_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    export_graph_views(payload, graph_dir)
    return graph_path


def ensure_placeholder_graph(records: list[PaperRecord], output_dir: Path) -> Path:
    graph_dir = output_dir / "graphs"
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph_path = graph_dir / "graph.json"
    payload = {
        "metadata": {
            "paper_count": len(records),
            "comparison_mode": "full_pairwise",
            "candidate_pair_count": 0,
            "evaluated_pair_count": 0,
            "accepted_macro_edge_count": 0,
            "accepted_micro_edge_count": 0,
        },
        "macro": {
            "nodes": [
                {
                    "id": record.arxiv_id,
                    "label": record.title or record.arxiv_id,
                    "kind": "paper",
                    "paper_id": record.arxiv_id,
                    "title": record.title,
                }
                for record in records
            ],
            "edges": [],
        },
        "micro": {
            "nodes": [],
            "edges": [],
        },
    }
    graph_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    export_graph_views(payload, graph_dir)
    return graph_path


def export_graph_views(payload: dict, graph_dir: Path) -> None:
    macro = payload.get("macro", {})
    micro = payload.get("micro", {})

    (graph_dir / "macro.mmd").write_text(_build_mermaid("macro", macro), encoding="utf-8")
    (graph_dir / "micro.mmd").write_text(_build_mermaid("micro", micro), encoding="utf-8")
    (graph_dir / "macro_graph.html").write_text(
        _build_single_layer_html("Macro Graph", "macro", macro),
        encoding="utf-8",
    )
    (graph_dir / "micro_graph.html").write_text(
        _build_single_layer_html("Micro Graph", "micro", micro),
        encoding="utf-8",
    )
    (graph_dir / "index.html").write_text(
        _build_linked_viewer_html(payload),
        encoding="utf-8",
    )


def _load_extractions(records: list[PaperRecord]) -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    for record in records:
        if not record.extraction_path or not record.extraction_path.exists():
            continue
        data = json.loads(record.extraction_path.read_text(encoding="utf-8"))
        payloads[record.arxiv_id] = data
    return payloads


def _build_macro_nodes(records: list[PaperRecord], extraction_payloads: dict[str, dict]) -> list[dict]:
    nodes = []
    for record in records:
        extraction = extraction_payloads.get(record.arxiv_id, {})
        metadata = extraction.get("paper_metadata") or {}
        title = metadata.get("title") or record.title
        nodes.append(
            {
                "id": record.arxiv_id,
                "label": title or record.arxiv_id,
                "kind": "paper",
                "paper_id": record.arxiv_id,
                "title": title,
            }
        )
    return nodes


def _build_micro_nodes(extraction_payloads: dict[str, dict]) -> list[dict]:
    nodes: list[dict] = []
    for paper_id, extraction in extraction_payloads.items():
        metadata = extraction.get("paper_metadata") or {}
        title = metadata.get("title")
        for unit in extraction.get("units", []):
            nodes.append(
                {
                    "id": unit["id"],
                    "label": unit.get("summary") or unit["type"],
                    "kind": "paper_unit",
                    "paper_id": paper_id,
                    "title": title,
                    "unit_type": unit["type"],
                    "summary": unit.get("summary"),
                    "text": unit.get("text"),
                    "supports": unit.get("supports", []),
                    "evidence_type": unit.get("evidence_type"),
                    "scope_data": unit.get("scope_data"),
                    "resource_name": unit.get("resource_name"),
                    "resource_type": unit.get("resource_type"),
                    "resource_role": unit.get("resource_role"),
                    "sources": unit.get("sources", []),
                }
            )
    return nodes


def _select_candidate_pairs(extraction_payloads: dict[str, dict], debug_dir: Path) -> tuple[list[tuple[str, str]], str]:
    paper_ids = sorted(extraction_payloads.keys())
    if len(paper_ids) <= FULL_PAIRWISE_LIMIT:
        pairs = list(combinations(paper_ids, 2))
        _write_candidate_debug(debug_dir, pairs, "full_pairwise", {})
        return pairs, "full_pairwise"

    scores: dict[tuple[str, str], float] = {}
    top_neighbors: dict[str, list[str]] = {}
    for left, right in combinations(paper_ids, 2):
        score = _paper_similarity_score(extraction_payloads[left], extraction_payloads[right])
        scores[(left, right)] = score

    for paper_id in paper_ids:
        neighbors = []
        for other_id in paper_ids:
            if other_id == paper_id:
                continue
            pair = tuple(sorted((paper_id, other_id)))
            neighbors.append((other_id, scores.get(pair, 0.0)))
        neighbors.sort(key=lambda item: item[1], reverse=True)
        top_neighbors[paper_id] = [item[0] for item in neighbors[:DEFAULT_TOP_K] if item[1] > 0]

    pair_set = set()
    for paper_id, neighbors in top_neighbors.items():
        for other_id in neighbors:
            pair_set.add(tuple(sorted((paper_id, other_id))))
    pairs = sorted(pair_set)
    _write_candidate_debug(debug_dir, pairs, "candidate_filtered", top_neighbors, scores)
    return pairs, "candidate_filtered"


def _paper_similarity_score(left: dict, right: dict) -> float:
    total = 0.0
    left_by_type = _summaries_by_type(left)
    right_by_type = _summaries_by_type(right)
    for unit_type, weight in SIMILARITY_FIELDS.items():
        left_tokens = _summary_tokens(left_by_type.get(unit_type, []))
        right_tokens = _summary_tokens(right_by_type.get(unit_type, []))
        if not left_tokens or not right_tokens:
            continue
        overlap = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        if union:
            total += weight * (overlap / union)
    return round(total, 4)


def _summaries_by_type(extraction: dict) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for unit in extraction.get("units", []):
        grouped.setdefault(unit["type"], []).append(unit.get("summary") or unit.get("text") or "")
    return grouped


def _summary_tokens(texts: list[str]) -> set[str]:
    tokens: set[str] = set()
    for text in texts:
        for token in text.lower().replace("/", " ").replace("-", " ").split():
            normalized = "".join(ch for ch in token if ch.isalnum())
            if len(normalized) >= 4:
                tokens.add(normalized)
    return tokens


def _write_candidate_debug(
    debug_dir: Path,
    pairs: list[tuple[str, str]],
    mode: str,
    top_neighbors: dict[str, list[str]],
    scores: dict[tuple[str, str], float] | None = None,
) -> None:
    payload = {
        "comparison_mode": mode,
        "candidate_pairs": [{"paper_a": left, "paper_b": right} for left, right in pairs],
        "top_neighbors": top_neighbors,
        "pair_scores": {
            f"{left}__{right}": score for (left, right), score in (scores or {}).items()
        },
    }
    (debug_dir / "candidate_pairs.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _evaluate_candidate_pairs(
    candidate_pairs: list[tuple[str, str]],
    extraction_payloads: dict[str, dict],
    output_dir: Path,
    llm_config: LLMConfig,
    debug_dir: Path,
) -> list[dict]:
    if not candidate_pairs:
        return []

    graph_skill = load_skill_text(Path("skills/paper-relation-graph-builder/SKILL.md"))
    provider = build_provider(llm_config)
    schema = _relationship_inference_schema()
    evaluations = []

    for left_id, right_id in candidate_pairs:
        left = extraction_payloads[left_id]
        right = extraction_payloads[right_id]
        messages = build_relationship_inference_messages(
            left=left,
            right=right,
            skill_text=graph_skill,
            schema=schema,
        )
        response = provider.create_json([LLMMessage(**message) for message in messages], schema)
        normalized = _normalize_relationship_response(left_id, right_id, response)
        evaluations.append(normalized)
        (debug_dir / f"{left_id.replace('.', '_')}__{right_id.replace('.', '_')}.json").write_text(
            json.dumps(
                {
                    "paper_a": left_id,
                    "paper_b": right_id,
                    "raw_response": response,
                    "normalized": normalized,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return evaluations


def _relationship_inference_schema() -> dict:
    return {
        "type": "object",
        "required": ["paper_a", "paper_b", "decision", "micro_relations"],
        "properties": {
            "paper_a": {"type": "string"},
            "paper_b": {"type": "string"},
            "decision": {
                "type": "object",
                "required": ["has_meaningful_relation", "macro_relation", "confidence", "rationale"],
                "properties": {
                    "has_meaningful_relation": {"type": "boolean"},
                    "macro_relation": {
                        "type": ["string", "null"],
                        "enum": [None, "support", "conflict", "extend", "parallel", "basis", "complement", "apply"],
                    },
                    "confidence": {"type": ["number", "null"]},
                    "rationale": {"type": ["string", "null"]},
                },
            },
            "micro_relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["source_unit_id", "target_unit_id", "relation", "confidence", "rationale", "evidence_refs"],
                    "properties": {
                        "source_unit_id": {"type": "string"},
                        "target_unit_id": {"type": "string"},
                        "relation": {
                            "enum": [
                                "support",
                                "conflict",
                                "extend",
                                "parallel",
                                "basis",
                                "complement",
                                "apply",
                                "addresses_limitation_of",
                                "comparable_validation",
                            ]
                        },
                        "confidence": {"type": ["number", "null"]},
                        "rationale": {"type": ["string", "null"]},
                        "evidence_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def _normalize_relationship_response(left_id: str, right_id: str, response: dict) -> dict:
    decision = response.get("decision", {})
    has_relation = bool(decision.get("has_meaningful_relation"))
    raw_micro = response.get("micro_relations", [])

    accepted_micro_edges = []
    for idx, relation in enumerate(raw_micro, start=1):
        accepted_micro_edges.append(
            {
                "id": f"micro_{left_id.replace('.', '_')}_{right_id.replace('.', '_')}_{idx}",
                "source": relation["source_unit_id"],
                "target": relation["target_unit_id"],
                "relation": relation["relation"],
                "confidence": relation.get("confidence"),
                "rationale": relation.get("rationale"),
                "evidence_refs": relation.get("evidence_refs", []),
            }
        )

    accepted_macro_edge = None
    if has_relation and decision.get("macro_relation") and accepted_micro_edges:
        accepted_macro_edge = {
            "id": f"macro_{left_id.replace('.', '_')}_{right_id.replace('.', '_')}",
            "source": left_id,
            "target": right_id,
            "relation": decision["macro_relation"],
            "confidence": decision.get("confidence"),
            "rationale": decision.get("rationale"),
            "supporting_micro_edges": [edge["id"] for edge in accepted_micro_edges],
        }

    return {
        "paper_a": left_id,
        "paper_b": right_id,
        "accepted_micro_edges": accepted_micro_edges if has_relation else [],
        "accepted_macro_edge": accepted_macro_edge,
    }


def _build_mermaid(layer_name: str, layer: dict) -> str:
    lines = ["graph LR"]
    for node in layer.get("nodes", []):
        node_id = _mermaid_safe_id(node["id"])
        label = _mermaid_escape(node.get("label") or node["id"])
        lines.append(f'    {node_id}["{label}"]')

    for edge in layer.get("edges", []):
        source = _mermaid_safe_id(edge["source"])
        target = _mermaid_safe_id(edge["target"])
        relation = _mermaid_escape(edge.get("relation") or "")
        lines.append(f"    {source} -->|{relation}| {target}")

    if len(lines) == 1:
        lines.append(f'    empty_{layer_name}["No edges"]')
    return "\n".join(lines) + "\n"


def _build_single_layer_html(title: str, layer_name: str, layer: dict) -> str:
    payload = {
        "nodes": layer.get("nodes", []),
        "edges": layer.get("edges", []),
        "layer_name": layer_name,
    }
    json_blob = json.dumps(payload, ensure_ascii=False)
    escaped_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escaped_title}</title>
  <script src="https://unpkg.com/@antv/g6@5/dist/g6.min.js"></script>
  <style>
    body {{
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(255, 228, 196, 0.58), transparent 26%),
        radial-gradient(circle at bottom right, rgba(198, 221, 255, 0.54), transparent 28%),
        #f6f2ea;
      color: #1f2328;
    }}
    .shell {{
      display: grid;
      grid-template-columns: 1fr 320px;
      min-height: 100vh;
    }}
    .canvas-wrap {{
      position: relative;
      overflow: hidden;
      padding: 18px;
    }}
    #mount {{
      width: 100%;
      height: calc(100vh - 36px);
      background: rgba(255,255,255,0.42);
      border: 1px solid #ddd3c3;
      border-radius: 24px;
      box-shadow: 0 20px 50px rgba(72, 56, 34, 0.08);
    }}
    .panel {{
      border-left: 1px solid #d4cfc4;
      background: rgba(255,255,255,0.78);
      backdrop-filter: blur(10px);
      padding: 20px;
      overflow: auto;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 20px;
    }}
    .meta {{
      margin-bottom: 16px;
      color: #5a5f66;
      font-size: 13px;
    }}
    .stat {{
      margin: 0 0 8px;
      font-size: 13px;
    }}
    .detail {{
      white-space: pre-wrap;
      line-height: 1.45;
      font-size: 13px;
    }}
    .hint {{
      color: #6b7280;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="canvas-wrap">
      <div id="mount"></div>
    </div>
    <aside class="panel">
      <h1>{escaped_title}</h1>
      <div class="meta">Nodes: <span id="node-count"></span> | Edges: <span id="edge-count"></span></div>
      <div class="stat"><strong>Layer:</strong> {html.escape(layer_name)}</div>
      <div class="hint">Click a node or edge to inspect its details.</div>
      <hr>
      <div id="detail" class="detail">Nothing selected.</div>
    </aside>
  </div>
  <script>
    const payload = {json_blob};
    const detail = document.getElementById("detail");
    document.getElementById("node-count").textContent = payload.nodes.length;
    document.getElementById("edge-count").textContent = payload.edges.length;
    const relationColors = {{
      support: '#16a34a',
      conflict: '#dc2626',
      extend: '#2563eb',
      parallel: '#f59e0b',
      basis: '#7c3aed',
      complement: '#ea580c',
      apply: '#0891b2',
      addresses_limitation_of: '#be123c',
      comparable_validation: '#475569',
    }};
    const unitColors = {{
      research_question: '#0f766e',
      core_claim: '#b91c1c',
      method: '#1d4ed8',
      formal_conclusion: '#7c3aed',
      evidence: '#ea580c',
      assumption: '#a16207',
      limitation: '#be123c',
      scope: '#475569',
      resource: '#0891b2',
    }};
    const layerPalette = payload.layer_name === 'macro'
      ? {{ fill: '#fffaf0', stroke: '#7c6651', tag: '#e7ddcf' }}
      : {{ fill: '#fffdfa', stroke: '#6d7682', tag: '#e8eef9' }};

    function hexToRgba(hex, alpha) {{
      const normalized = (hex || '#6d7682').replace('#', '');
      const full = normalized.length === 3
        ? normalized.split('').map((c) => c + c).join('')
        : normalized;
      const num = parseInt(full, 16);
      const r = (num >> 16) & 255;
      const g = (num >> 8) & 255;
      const b = num & 255;
      return `rgba(${{r}}, ${{g}}, ${{b}}, ${{alpha}})`;
    }}

    function splitLines(text, maxChars) {{
      if (!text) return [''];
      const raw = String(text).replace(/\\s+/g, ' ').trim();
      const chunks = [];
      for (let i = 0; i < raw.length; i += maxChars) {{
        chunks.push(raw.slice(i, i + maxChars));
      }}
      return chunks.length ? chunks : [''];
    }}

    function wrapText(text, length) {{
      if (!text) return '';
      return text.length > length ? text.slice(0, length - 3) + '...' : text;
    }}

    const nodes = payload.nodes.map((node) => {{
      const isMacro = payload.layer_name === 'macro';
      const labelRaw = node.label || node.id;
      const subtitleRaw = isMacro
        ? (node.paper_id || node.id)
        : ((node.paper_id || '') + ' / ' + (node.unit_type || node.kind || ''));
      const labelLines = splitLines(labelRaw, isMacro ? 34 : 30).slice(0, isMacro ? 2 : 3);
      const subtitleLines = splitLines(subtitleRaw, isMacro ? 22 : 26).slice(0, 2);
      const label = labelLines.map((item) => wrapText(item, isMacro ? 34 : 30)).join('\\n');
      const subtitle = subtitleLines.map((item) => wrapText(item, isMacro ? 22 : 26)).join('\\n');
      const lineCount = labelLines.length + subtitleLines.length;
      const minHeight = isMacro ? 104 : 96;
      const maxHeight = isMacro ? 160 : 154;
      const height = Math.min(maxHeight, minHeight + Math.max(0, lineCount - 2) * 16);
      const width = isMacro ? 284 : 318;
      const unitColor = unitColors[node.unit_type] || layerPalette.stroke;
      return {{
        id: node.id,
        data: node,
        style: {{
          size: [width, height],
          labelText: label,
          subtitleText: subtitle,
          fill: payload.layer_name === 'micro' ? hexToRgba(unitColor, 0.14) : layerPalette.fill,
          stroke: payload.layer_name === 'micro' ? unitColor : layerPalette.stroke,
          labelLineHeight: isMacro ? 20 : 18,
          labelMaxWidth: width - 28,
        }},
      }};
    }});

    const edges = payload.edges.map((edge) => {{
      return {{
        id: edge.id || `${{edge.source}}__${{edge.target}}__${{edge.relation || 'edge'}}`,
        source: edge.source,
        target: edge.target,
        data: edge,
        style: {{
          stroke: relationColors[edge.relation] || '#59636e',
          labelText: edge.relation || '',
          endArrow: true,
          lineWidth: 2,
        }},
      }};
    }});

    const graph = new G6.Graph({{
      container: 'mount',
      autoFit: 'view',
      data: {{ nodes, edges }},
      node: {{
        type: 'rect',
        style: {{
          radius: 18,
          shadowColor: 'rgba(72,56,34,0.10)',
          shadowBlur: 22,
          shadowOffsetY: 10,
          lineWidth: payload.layer_name === 'micro' ? 3 : 1.6,
          labelFill: '#1f2328',
          labelFontSize: 13,
          labelFontWeight: 600,
          labelPlacement: 'center',
        }},
      }},
      edge: {{
        type: 'cubic-horizontal',
        style: {{
          labelFill: '#344054',
          labelBackground: true,
          labelBackgroundFill: '#f6f2ea',
          labelBackgroundRadius: 6,
          labelPadding: [2, 6, 2, 6],
        }},
      }},
      layout: {{
        type: 'dagre',
        rankdir: 'LR',
        nodesep: payload.layer_name === 'macro' ? 48 : 34,
        ranksep: payload.layer_name === 'macro' ? 86 : 62,
      }},
      behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
      plugins: [
        {{
          type: 'grid-line',
          follow: false,
        }},
      ],
    }});

    graph.render();

    graph.on('node:click', (evt) => {{
      const data = evt.target?.data || evt.data?.data || evt.data;
      detail.textContent = JSON.stringify(data, null, 2);
    }});

    graph.on('edge:click', (evt) => {{
      const data = evt.target?.data || evt.data?.data || evt.data;
      detail.textContent = JSON.stringify(data, null, 2);
    }});
  </script>
</body>
</html>
"""


def _build_linked_viewer_html(payload: dict) -> str:
    metadata = payload.get("metadata", {})
    json_blob = json.dumps(payload, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Autopaper Graph Viewer</title>
  <script src="https://unpkg.com/@antv/g6@5/dist/g6.min.js"></script>
  <style>
    :root {{
      --bg: #f4efe6;
      --panel: rgba(255,255,255,0.84);
      --line: #d7cec0;
      --text: #1f2328;
      --muted: #66707c;
      --paper-fill: #fffaf0;
      --paper-stroke: #7e6750;
      --micro-fill: #fffdf9;
      --shadow: 0 18px 40px rgba(53, 44, 31, 0.10);
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(250, 221, 200, 0.52), transparent 24%),
        radial-gradient(circle at bottom right, rgba(205, 229, 255, 0.58), transparent 28%),
        var(--bg);
    }}
    .shell {{
      display: grid;
      grid-template-columns: 1.2fr 1.1fr 320px;
      min-height: 100vh;
      gap: 0;
    }}
    .shell.expand-macro {{
      grid-template-columns: 2.2fr 0.55fr 320px;
    }}
    .shell.expand-micro {{
      grid-template-columns: 0.55fr 2.2fr 320px;
    }}
    .pane {{
      border-right: 1px solid var(--line);
      min-width: 0;
      position: relative;
      transition: opacity 160ms ease, transform 160ms ease;
    }}
    .pane:last-child {{
      border-right: 0;
    }}
    .shell.expand-macro .pane.micro-pane,
    .shell.expand-micro .pane.macro-pane {{
      opacity: 0.45;
    }}
    .pane-head {{
      padding: 18px 20px 12px;
      background: rgba(255,255,255,0.55);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--line);
    }}
    .pane-head h2 {{
      margin: 0 0 6px;
      font-size: 18px;
    }}
    .pane-toolbar {{
      position: absolute;
      top: 16px;
      right: 16px;
      display: flex;
      gap: 8px;
    }}
    .pane-btn {{
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.88);
      color: var(--text);
      border-radius: 999px;
      font-size: 12px;
      line-height: 1;
      padding: 8px 10px;
      cursor: pointer;
    }}
    .pane-btn:hover {{
      background: #fff;
    }}
    .meta {{
      font-size: 13px;
      color: var(--muted);
    }}
    .canvas {{
      height: calc(100vh - 74px);
      overflow: hidden;
      padding: 18px;
    }}
    .mount {{
      width: 100%;
      height: 100%;
      background: rgba(255,255,255,0.42);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
    }}
    .detail-pane {{
      background: rgba(255,255,255,0.72);
      backdrop-filter: blur(12px);
      padding: 20px;
      overflow: auto;
    }}
    .detail-pane h1 {{
      margin: 0 0 8px;
      font-size: 22px;
    }}
    .detail-box {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: var(--shadow);
      padding: 14px 16px;
      margin-bottom: 14px;
    }}
    .detail-label {{
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 8px;
    }}
    .detail-pre {{
      white-space: pre-wrap;
      font-size: 13px;
      line-height: 1.5;
    }}
    .pill {{
      display: inline-block;
      font-size: 12px;
      line-height: 1;
      padding: 6px 8px;
      border-radius: 999px;
      background: #ede4d5;
      color: #5a4d3e;
      margin: 4px 6px 0 0;
    }}
    .muted {{
      color: var(--muted);
    }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }}
    .legend span {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: var(--muted);
    }}
    .swatch {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="pane macro-pane">
      <div class="pane-head">
        <h2>Macro View</h2>
        <div class="pane-toolbar">
          <button id="macro-expand-btn" class="pane-btn" type="button">Expand</button>
        </div>
        <div class="meta">
          Papers: {metadata.get("paper_count", 0)} |
          Macro edges: {payload.get("metadata", {}).get("accepted_macro_edge_count", 0)}
        </div>
      </div>
      <div class="canvas"><div id="macro-mount" class="mount"></div></div>
    </section>
    <section class="pane micro-pane">
      <div class="pane-head">
        <h2>Micro View</h2>
        <div class="pane-toolbar">
          <button id="micro-expand-btn" class="pane-btn" type="button">Expand</button>
        </div>
        <div class="meta" id="micro-meta">Select a macro edge to inspect the corresponding micro subgraph.</div>
        <div class="legend">
          <span><i class="swatch" style="background:#0f766e;"></i>question</span>
          <span><i class="swatch" style="background:#b91c1c;"></i>claim</span>
          <span><i class="swatch" style="background:#1d4ed8;"></i>method</span>
          <span><i class="swatch" style="background:#7c3aed;"></i>conclusion</span>
          <span><i class="swatch" style="background:#ea580c;"></i>evidence</span>
          <span><i class="swatch" style="background:#475569;"></i>scope</span>
          <span><i class="swatch" style="background:#a16207;"></i>assumption</span>
          <span><i class="swatch" style="background:#be123c;"></i>limitation</span>
          <span><i class="swatch" style="background:#0891b2;"></i>resource</span>
        </div>
      </div>
      <div class="canvas"><div id="micro-mount" class="mount"></div></div>
    </section>
    <aside class="detail-pane">
      <h1>Autopaper Graph Viewer</h1>
      <div class="meta">Comparison mode: {html.escape(str(metadata.get("comparison_mode", "")))}</div>
      <div class="detail-box">
        <div class="detail-label">Selection</div>
        <div id="selection-summary" class="detail-pre">Nothing selected.</div>
      </div>
      <div class="detail-box">
        <div class="detail-label">Details</div>
        <div id="selection-detail" class="detail-pre muted">Click a paper node, a macro edge, or a micro edge.</div>
      </div>
      <div class="detail-box">
        <div class="detail-label">Exports</div>
        <div class="detail-pre"><a href="graph.json">graph.json</a>
<a href="macro.mmd">macro.mmd</a>
<a href="micro.mmd">micro.mmd</a>
<a href="macro_graph.html">macro_graph.html</a>
<a href="micro_graph.html">micro_graph.html</a></div>
      </div>
    </aside>
  </div>
  <script>
    const graph = {json_blob};
    const shell = document.querySelector('.shell');
    const selectionSummary = document.getElementById("selection-summary");
    const selectionDetail = document.getElementById("selection-detail");
    const microMeta = document.getElementById("micro-meta");
    const macroExpandBtn = document.getElementById('macro-expand-btn');
    const microExpandBtn = document.getElementById('micro-expand-btn');
    const macroNodeMap = new Map((graph.macro?.nodes || []).map((item) => [item.id, item]));
    const macroEdgeMap = new Map((graph.macro?.edges || []).map((item) => [item.id, item]));
    const microNodeMap = new Map((graph.micro?.nodes || []).map((item) => [item.id, item]));
    const microEdgeMap = new Map((graph.micro?.edges || []).map((item) => [item.id, item]));

    const relationColors = {{
      support: "#16a34a",
      conflict: "#dc2626",
      extend: "#2563eb",
      parallel: "#f59e0b",
      basis: "#7c3aed",
      complement: "#ea580c",
      apply: "#0891b2",
      addresses_limitation_of: "#be123c",
      comparable_validation: "#475569",
    }};

    const unitColors = {{
      research_question: "#0f766e",
      core_claim: "#b91c1c",
      method: "#1d4ed8",
      formal_conclusion: "#7c3aed",
      evidence: "#ea580c",
      assumption: "#a16207",
      limitation: "#be123c",
      scope: "#475569",
      resource: "#0891b2",
    }};

    function hexToRgba(hex, alpha) {{
      const normalized = (hex || '#6d7682').replace('#', '');
      const full = normalized.length === 3
        ? normalized.split('').map((c) => c + c).join('')
        : normalized;
      const num = parseInt(full, 16);
      const r = (num >> 16) & 255;
      const g = (num >> 8) & 255;
      const b = num & 255;
      return `rgba(${{r}}, ${{g}}, ${{b}}, ${{alpha}})`;
    }}

    function splitLines(text, maxChars) {{
      if (!text) return [''];
      const raw = String(text).replace(/\\s+/g, ' ').trim();
      const chunks = [];
      for (let i = 0; i < raw.length; i += maxChars) {{
        chunks.push(raw.slice(i, i + maxChars));
      }}
      return chunks.length ? chunks : [''];
    }}

    function truncate(text, limit) {{
      if (!text) return "";
      return text.length > limit ? text.slice(0, limit - 3) + "..." : text;
    }}

    function formatBlock(label, value) {{
      if (value === null || value === undefined) return '';
      if (Array.isArray(value) && value.length === 0) return '';
      if (typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 0) return '';
      const rendered = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
      return `${{label}}: ${{rendered}}`;
    }}

    function renderMicroNodeDetail(node) {{
      const blocks = [];
      blocks.push(formatBlock('Type', node.unit_type));
      blocks.push(formatBlock('Text', node.text));
      blocks.push(formatBlock('Evidence Type', node.evidence_type));
      blocks.push(formatBlock('Resource Name', node.resource_name));
      blocks.push(formatBlock('Resource Type', node.resource_type));
      blocks.push(formatBlock('Resource Role', node.resource_role));
      blocks.push(formatBlock('Supports', node.supports));
      blocks.push(formatBlock('Scope Data', node.scope_data));
      return blocks.filter(Boolean).join('\\n\\n');
    }}

    function renderMacroNodeDetail(node) {{
      const blocks = [];
      blocks.push(formatBlock('Title', node.title));
      blocks.push(formatBlock('ID', node.id));
      return blocks.filter(Boolean).join('\\n\\n');
    }}

    function renderEdgeDetail(edge) {{
      const blocks = [];
      blocks.push(formatBlock('Relation', edge.relation));
      blocks.push(formatBlock('Confidence', edge.confidence));
      blocks.push(formatBlock('Rationale', edge.rationale));
      blocks.push(formatBlock('Supporting Micro Edges', edge.supporting_micro_edges));
      blocks.push(formatBlock('Evidence Refs', edge.evidence_refs));
      return blocks.filter(Boolean).join('\\n\\n');
    }}

    function setExpandState(mode) {{
      shell.classList.remove('expand-macro', 'expand-micro');
      if (mode === 'macro') shell.classList.add('expand-macro');
      if (mode === 'micro') shell.classList.add('expand-micro');
      macroExpandBtn.textContent = mode === 'macro' ? 'Shrink' : 'Expand';
      microExpandBtn.textContent = mode === 'micro' ? 'Shrink' : 'Expand';
      window.setTimeout(() => {{
        refreshGraphViewport(macroGraph, document.getElementById('macro-mount'));
        refreshGraphViewport(microGraph, document.getElementById('micro-mount'));
      }}, 60);
    }}

    function eventElementId(evt) {{
      return evt?.target?.id || evt?.target?.config?.id || evt?.data?.id || evt?.item?.id || null;
    }}

    function resolveNode(evt, layer) {{
      const direct = evt?.data?.data || evt?.data;
      if (direct && direct.paper_id) return direct;
      const id = eventElementId(evt);
      if (!id) return null;
      return (layer === 'macro' ? macroNodeMap : microNodeMap).get(id) || null;
    }}

    function resolveEdge(evt, layer) {{
      const direct = evt?.data?.data || evt?.data;
      if (direct && direct.source && direct.target) return direct;
      const id = eventElementId(evt);
      if (id) {{
        const fromId = (layer === 'macro' ? macroEdgeMap : microEdgeMap).get(id);
        if (fromId) return fromId;
      }}
      const source = evt?.data?.source;
      const target = evt?.data?.target;
      const relation = evt?.data?.relation;
      const haystack = layer === 'macro' ? (graph.macro?.edges || []) : (graph.micro?.edges || []);
      return haystack.find((edge) =>
        edge.source === source && edge.target === target && (!relation || edge.relation === relation)
      ) || null;
    }}

    function buildNodes(nodes, layer) {{
      return nodes.map((node) => {{
        const isMacro = layer === 'macro';
        const labelRaw = node.label || node.id;
        const subtitleRaw = isMacro
          ? (node.paper_id || node.id)
          : `${{node.paper_id || ''}} / ${{node.unit_type || ''}}`;
        const labelLines = splitLines(labelRaw, isMacro ? 34 : 30).slice(0, isMacro ? 2 : 3);
        const subtitleLines = splitLines(subtitleRaw, isMacro ? 22 : 26).slice(0, 2);
        const label = labelLines.map((item) => truncate(item, isMacro ? 34 : 30)).join('\\n');
        const subtitle = subtitleLines.map((item) => truncate(item, isMacro ? 22 : 26)).join('\\n');
        const lineCount = labelLines.length + subtitleLines.length;
        const minHeight = isMacro ? 104 : 96;
        const maxHeight = isMacro ? 160 : 154;
        const height = Math.min(maxHeight, minHeight + Math.max(0, lineCount - 2) * 16);
        const width = isMacro ? 284 : 318;
        const stroke = layer === 'macro'
          ? '#7e6750'
          : (unitColors[node.unit_type] || '#6b7280');
        const fill = layer === 'macro'
          ? '#fff9ef'
          : hexToRgba(stroke, 0.14);
        return {{
          id: node.id,
          data: node,
          style: {{
            size: [width, height],
            fill,
            stroke,
            radius: 18,
            labelText: `${{label}}\\n${{subtitle}}`,
            labelFill: '#1f2328',
            labelFontSize: isMacro ? 13 : 12,
            labelLineHeight: isMacro ? 20 : 18,
            labelMaxWidth: width - 28,
            labelPlacement: 'center',
            lineWidth: isMacro ? 1.6 : 3,
            shadowColor: 'rgba(72,56,34,0.10)',
            shadowBlur: 20,
            shadowOffsetY: 8,
          }},
        }};
      }});
    }}

    function buildEdges(edges) {{
      return edges.map((edge) => {{
        return {{
          id: edge.id || `${{edge.source}}__${{edge.target}}__${{edge.relation || 'edge'}}`,
          source: edge.source,
          target: edge.target,
          data: edge,
          style: {{
            stroke: relationColors[edge.relation] || '#53606f',
            labelText: edge.relation || '',
            endArrow: true,
            lineWidth: 2.2,
            labelFill: '#344054',
            labelBackground: true,
            labelBackgroundFill: '#f4efe6',
            labelBackgroundRadius: 6,
            labelPadding: [2, 6, 2, 6],
          }},
        }};
      }});
    }}

    function createGraph(container, nodes, edges, layer, onNodeClick, onEdgeClick) {{
      const instance = new G6.Graph({{
        container,
        autoFit: 'view',
        data: {{
          nodes: buildNodes(nodes, layer),
          edges: buildEdges(edges),
        }},
        node: {{
          type: 'rect',
        }},
        edge: {{
          type: 'cubic-horizontal',
        }},
        layout: {{
          type: 'dagre',
          rankdir: 'LR',
          nodesep: layer === 'macro' ? 52 : 34,
          ranksep: layer === 'macro' ? 96 : 70,
        }},
        behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
        plugins: [
          {{
            type: 'grid-line',
            follow: false,
          }},
        ],
      }});
      instance.render();
      instance.on('node:click', (evt) => {{
        const data = resolveNode(evt, layer);
        onNodeClick(data);
      }});
      instance.on('edge:click', (evt) => {{
        const data = resolveEdge(evt, layer);
        onEdgeClick(data);
      }});
      return instance;
    }}

    function refreshGraphViewport(instance, mount) {{
      if (!instance || !mount) return;
      const width = mount.clientWidth || 800;
      const height = mount.clientHeight || 600;
      if (typeof instance.setSize === 'function') {{
        instance.setSize(width, height);
      }} else if (typeof instance.resize === 'function') {{
        instance.resize(width, height);
      }}
      if (typeof instance.fitView === 'function') {{
        instance.fitView();
      }} else if (typeof instance.fitCenter === 'function') {{
        instance.fitCenter();
      }}
    }}

    function selectMacroEdge(edge) {{
      if (!edge) return;
      const microEdges = graph.micro.edges.filter((item) => (edge.supporting_micro_edges || []).includes(item.id));
      const nodeIds = new Set();
      microEdges.forEach((item) => {{
        nodeIds.add(item.source);
        nodeIds.add(item.target);
      }});
      const microNodes = graph.micro.nodes.filter((node) => nodeIds.has(node.id));
      const sourceNode = graph.macro.nodes.find((n) => n.id === edge.source);
      const targetNode = graph.macro.nodes.find((n) => n.id === edge.target);
      microMeta.textContent = `${{sourceNode?.label || edge.source}}  ->  ${{targetNode?.label || edge.target}} | micro edges: ${{microEdges.length}}`;
      renderMicroSubgraph(microNodes, microEdges);
    }}

    function selectMacroNode(node) {{
      if (!node) return;
      const microNodes = (graph.micro?.nodes || []).filter((item) => item.paper_id === node.id);
      const nodeIds = new Set(microNodes.map((item) => item.id));
      const microEdges = (graph.micro?.edges || []).filter((edge) => nodeIds.has(edge.source) || nodeIds.has(edge.target));
      microMeta.textContent = `${{node.label || node.id}} | micro nodes: ${{microNodes.length}} | micro edges: ${{microEdges.length}}`;
      renderMicroSubgraph(microNodes, microEdges);
    }}

    let macroGraph = null;
    let microGraph = null;

    function renderMicroSubgraph(nodes, edges) {{
      const mount = document.getElementById('micro-mount');
      mount.innerHTML = '';
      if (!nodes.length) {{
        mount.innerHTML = '<div style="padding:28px;color:#6b7280;font-size:14px;">Select a macro edge to inspect the corresponding micro subgraph.</div>';
        return;
      }}
      microGraph = createGraph(
        'micro-mount',
        nodes,
        edges,
        'micro',
        (node) => {{
          selectionSummary.textContent = `Micro node: ${{node.unit_type || node.kind}}`;
          selectionDetail.textContent = renderMicroNodeDetail(node);
        }},
        (edge) => {{
          selectionSummary.textContent = `Micro edge: ${{edge.relation}}`;
          selectionDetail.textContent = renderEdgeDetail(edge);
        }},
      );
      window.setTimeout(() => refreshGraphViewport(microGraph, document.getElementById('micro-mount')), 30);
    }}

    macroGraph = createGraph(
      'macro-mount',
      graph.macro.nodes,
      graph.macro.edges,
      'macro',
      (node) => {{
        if (!node) return;
        selectionSummary.textContent = `Paper: ${{node.label || node.id}}`;
        selectionDetail.textContent = renderMacroNodeDetail(node);
        selectMacroNode(node);
      }},
      (edge) => {{
        if (!edge) return;
        selectionSummary.textContent = `Macro edge: ${{edge.relation}}`;
        selectionDetail.textContent = renderEdgeDetail(edge);
        selectMacroEdge(edge);
      }},
    );
    window.setTimeout(() => refreshGraphViewport(macroGraph, document.getElementById('macro-mount')), 30);
    renderMicroSubgraph([], []);

    window.addEventListener('resize', () => {{
      refreshGraphViewport(macroGraph, document.getElementById('macro-mount'));
      refreshGraphViewport(microGraph, document.getElementById('micro-mount'));
    }});

    macroExpandBtn.addEventListener('click', () => {{
      const expanded = shell.classList.contains('expand-macro');
      setExpandState(expanded ? null : 'macro');
    }});

    microExpandBtn.addEventListener('click', () => {{
      const expanded = shell.classList.contains('expand-micro');
      setExpandState(expanded ? null : 'micro');
    }});
  </script>
</body>
</html>
"""


def _mermaid_safe_id(raw: str) -> str:
    safe = raw.replace(".", "_").replace("-", "_").replace(":", "_")
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in safe)


def _mermaid_escape(text: str) -> str:
    return text.replace('"', "'")
