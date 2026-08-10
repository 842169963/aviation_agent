"""
Step 11: CQ-Based SPARQL Benchmark — V1 vs V2 Ontology
=======================================================

Run the 35 Competency Questions against both KG.ttl (V1) and kg_v2.ttl (V2)
to measure whether the richer V2 ontology actually unlocks new query capability.

Pipeline:
    Step 1: generate — LLM translates each CQ to V1 + V2 SPARQL
    Step 2: execute  — Run each query against the matching KG
    Step 3: judge    — LLM judge scores answers (0 / 0.5 / 1) per side
    Step 4: report   — Write benchmark_report.md

Usage:
    python scripts/11_cq_sparql_benchmark.py                          # full pipeline
    python scripts/11_cq_sparql_benchmark.py --steps generate         # only generate
    python scripts/11_cq_sparql_benchmark.py --steps execute,judge,report --use-reviewed
    python scripts/11_cq_sparql_benchmark.py --limit 5                # first 5 CQs only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import OpenAI
from rdflib import Graph, Namespace

if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "cp936", "gb2312"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ── Paths ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CQ_FILE = PROJECT_ROOT / "output" / "ontology_experiment_v2" / "domain_cqs.json"
V1_SCHEMA = PROJECT_ROOT / "schema" / "emergency_schema.yaml"
V2_SCHEMA = PROJECT_ROOT / "schema" / "emergency_schema_v2.yaml"
V1_KG = PROJECT_ROOT / "output" / "kg.ttl"
V2_KG = PROJECT_ROOT / "output" / "schema_v2" / "kg_v2.ttl"

OUT_DIR = PROJECT_ROOT / "output" / "cq_benchmark"
QUERIES_FILE = OUT_DIR / "sparql_queries.json"
REVIEWED_FILE = OUT_DIR / "sparql_queries.reviewed.json"
RESULTS_FILE = OUT_DIR / "sparql_results.json"
SCORES_FILE = OUT_DIR / "judge_scores.json"
REPORT_FILE = OUT_DIR / "benchmark_report.md"

AV = Namespace("https://example.org/aviation/")

# Default models — cheap for generator, stronger for judge.
GENERATOR_MODEL_DEFAULT = "gpt-4o-mini"
JUDGE_MODEL_DEFAULT = "gpt-4o"

# Avoid blowing the context window on huge result sets.
RESULT_ROW_CAP = 20


# ── LLM client (mirrors 01_extract.py logic) ───────────────────────
def create_llm_client(model_override: str | None = None) -> tuple[OpenAI, str, str]:
    """Pick OpenAI or Gemini via the same .env conventions as the rest of the project."""
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

    import os

    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    gemini_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    base_url = (os.getenv("OPENAI_BASE_URL") or "").strip() or None

    if provider == "gemini" or (not provider and gemini_key and not openai_key):
        if not gemini_key:
            raise RuntimeError("GEMINI_API_KEY missing in .env")
        gemini_base = base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"
        model = model_override or os.getenv("MODEL_NAME") or "gemini-2.5-flash"
        return OpenAI(api_key=gemini_key, base_url=gemini_base), model, "gemini"

    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY missing in .env")
    kwargs = {"api_key": openai_key}
    if base_url:
        kwargs["base_url"] = base_url
    model = model_override or os.getenv("MODEL_NAME") or GENERATOR_MODEL_DEFAULT
    return OpenAI(**kwargs), model, "openai"


def parse_json_response(raw: str) -> Any:
    """Strip markdown fences, then json.loads."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    # Find outermost JSON object/array
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = cleaned.find(open_ch)
        end = cleaned.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                continue
    return json.loads(cleaned)


# ── Schema summarization for the generator prompt ──────────────────
def describe_kg_shape(kg_path: Path, label: str) -> str:
    """Introspect the actual KG to enumerate classes, their predicates, and example values.

    This is more reliable than parsing the LinkML YAML because the YAML attribute
    names (e.g. `steps`) do not always match the KG predicates (`hasStep`).
    """
    graph = Graph()
    graph.parse(kg_path, format="turtle")
    rdf_type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

    # class -> {predicate -> {object_kind: 'literal' or class_label, sample_values: [..]}}
    class_predicates: dict[str, dict[str, dict[str, Any]]] = {}
    instance_class: dict[Any, str] = {}

    # First pass: instance → class
    for s, p, o in graph:
        if str(p) == rdf_type and str(o).startswith(str(AV)):
            instance_class[s] = str(o).split("/")[-1]

    # Second pass: collect predicate usage per class
    for s, p, o in graph:
        if str(p) == rdf_type:
            continue
        cls = instance_class.get(s)
        if not cls:
            continue
        pred = str(p).split("/")[-1] if str(p).startswith(str(AV)) else str(p)
        bucket = class_predicates.setdefault(cls, {}).setdefault(pred, {
            "object_kinds": set(), "samples": []
        })
        target_cls = instance_class.get(o)
        if target_cls:
            bucket["object_kinds"].add(target_cls)
        else:
            bucket["object_kinds"].add("literal")
            sample = str(o)
            if len(sample) > 80:
                sample = sample[:80] + "..."
            if len(bucket["samples"]) < 2 and sample not in bucket["samples"]:
                bucket["samples"].append(sample)

    lines = [f"# {label} KG — actual predicates extracted from {kg_path.name}"]
    lines.append(f"# Total triples: {len(graph)}")
    for cls in sorted(class_predicates.keys()):
        lines.append(f"\nClass av:{cls}")
        preds = class_predicates[cls]
        for pred in sorted(preds.keys()):
            info = preds[pred]
            kinds = sorted(info["object_kinds"])
            kinds_str = " | ".join(kinds)
            sample_str = ""
            if info["samples"]:
                sample_str = "  e.g. " + " / ".join(f'"{s}"' for s in info["samples"])
            lines.append(f"  - av:{pred} -> {kinds_str}{sample_str}")
    return "\n".join(lines)


# ── Step 1: SPARQL generation ──────────────────────────────────────
GENERATOR_SYSTEM = (
    "You translate aviation Competency Questions (CQs) into SPARQL queries.\n"
    "You will be given the actual predicate inventory of TWO knowledge graphs "
    "(V1 and V2) and one CQ. Produce one SPARQL query per KG.\n\n"
    "Rules:\n"
    "1. Use ONLY predicates and classes that appear in the supplied inventory. "
    "Do not invent or rename predicates (e.g. do not use `steps` if the inventory says `hasStep`).\n"
    "2. Always include `PREFIX av: <https://example.org/aviation/>` and `PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>`.\n"
    "3. The CQ asks a real question — the V1 query should still try keyword-based "
    "retrieval over the string fields (name, trigger_condition, action, description, "
    "source_excerpt) even when the CQ involves hazards or systems. Mark v1_query as "
    "\"UNSUPPORTED\" only when the CQ asks for a STRUCTURAL relationship V1 truly cannot "
    "express (e.g. \"which hazard affects which system\" — V1 has no Hazard class).\n"
    "4. Prefer SELECT queries returning meaningful bindings. End with `LIMIT 20`.\n"
    "5. Use case-insensitive matching: FILTER(CONTAINS(LCASE(STR(?x)), \"keyword\")).\n"
    "6. For multi-keyword filters, prefer OR over AND unless the CQ requires both. "
    "Avoid filters that require multiple specific keywords in a single short field — "
    "they almost always return empty.\n"
    "7. Both KGs use blank nodes for steps, warnings, hazards, evidence, etc. "
    "Use variables (?step, ?h) — never assume URIs.\n\n"
    "Output strict JSON:\n"
    "{\n"
    '  "v1_query": "PREFIX av: ... SELECT ... WHERE { ... } LIMIT 20",\n'
    '  "v1_unsupported_reason": "..."  // ONLY when v1_query == "UNSUPPORTED"\n'
    '  "v2_query": "PREFIX av: ... SELECT ... WHERE { ... } LIMIT 20",\n'
    '  "notes": "1-sentence rationale"\n'
    "}\n"
)

GENERATOR_EXAMPLE = """
Example CQ: "Which hazards are linked to the electrical system?"
Example output:
{
  "v1_query": "UNSUPPORTED",
  "v1_unsupported_reason": "V1 has no Hazard or AircraftSystem class; only free-text warnings.",
  "v2_query": "PREFIX av: <https://example.org/aviation/>\\nSELECT ?procName ?hazardName ?sysName WHERE {\\n  ?p a av:EmergencyProcedure ; av:name ?procName ; av:hasHazard ?h .\\n  ?h av:name ?hazardName ; av:affectedSystem ?s .\\n  ?s av:name ?sysName .\\n  FILTER(CONTAINS(LCASE(STR(?sysName)), \\"electrical\\"))\\n} LIMIT 20",
  "notes": "V2 directly traverses procedure->hazard->affectedSystem; V1 lacks this structure."
}

Example CQ: "What techniques does the manual describe for emergency landings on adverse terrain?"
Example output:
{
  "v1_query": "PREFIX av: <https://example.org/aviation/>\\nSELECT ?procName ?action WHERE {\\n  ?p a av:EmergencyProcedure ; av:name ?procName ; av:hasStep ?step .\\n  ?step av:action ?action .\\n  FILTER(CONTAINS(LCASE(STR(?procName)), \\"landing\\") || CONTAINS(LCASE(STR(?action)), \\"terrain\\"))\\n} LIMIT 20",
  "v2_query": "PREFIX av: <https://example.org/aviation/>\\nSELECT ?procName ?action ?phase WHERE {\\n  ?p a av:EmergencyProcedure ; av:name ?procName ; av:hasStep ?step .\\n  ?step av:action ?action .\\n  OPTIONAL { ?p av:hasFlightPhase ?fp . ?fp av:name ?phase . }\\n  FILTER(CONTAINS(LCASE(STR(?procName)), \\"landing\\") || CONTAINS(LCASE(STR(?action)), \\"terrain\\"))\\n} LIMIT 20",
  "notes": "Same retrieval shape on both sides; V2 adds flight phase context."
}
"""


def generate_sparql_for_cq(
    cq: dict[str, Any],
    v1_schema_desc: str,
    v2_schema_desc: str,
    client: OpenAI,
    model: str,
) -> dict[str, Any]:
    user_msg = (
        f"{GENERATOR_EXAMPLE}\n\n"
        "V1 SCHEMA:\n```\n" + v1_schema_desc + "\n```\n\n"
        "V2 SCHEMA:\n```\n" + v2_schema_desc + "\n```\n\n"
        "Competency Question:\n```json\n"
        + json.dumps({
            "id": cq.get("id"),
            "question": cq.get("question"),
            "expected_answer": cq.get("expected_answer"),
            "required_concepts": cq.get("required_concepts", []),
            "required_relations": cq.get("required_relations", []),
        }, indent=2)
        + "\n```\n\nReturn ONLY the JSON object."
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": GENERATOR_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "{}"
    payload = parse_json_response(raw)
    usage = response.usage
    return {
        "cq_id": cq.get("id"),
        "v1_query": payload.get("v1_query", "UNSUPPORTED"),
        "v1_unsupported_reason": payload.get("v1_unsupported_reason"),
        "v2_query": payload.get("v2_query", "UNSUPPORTED"),
        "notes": payload.get("notes", ""),
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        },
    }


def step_generate(cqs: list[dict[str, Any]], limit: int | None) -> dict[str, Any]:
    client, model, provider = create_llm_client(GENERATOR_MODEL_DEFAULT)
    print(f"[generate] provider={provider} model={model}")

    v1_desc = describe_kg_shape(V1_KG, "V1")
    v2_desc = describe_kg_shape(V2_KG, "V2")

    selected = cqs if limit is None else cqs[:limit]
    queries = []
    total_in = total_out = 0

    for i, cq in enumerate(selected, start=1):
        print(f"  [{i}/{len(selected)}] {cq.get('id')} — {cq.get('question', '')[:70]}")
        try:
            row = generate_sparql_for_cq(cq, v1_desc, v2_desc, client, model)
            queries.append(row)
            total_in += row["usage"]["prompt_tokens"]
            total_out += row["usage"]["completion_tokens"]
        except Exception as exc:
            print(f"      generator error: {exc}")
            queries.append({
                "cq_id": cq.get("id"),
                "v1_query": "UNSUPPORTED",
                "v1_unsupported_reason": f"generator failed: {exc}",
                "v2_query": "UNSUPPORTED",
                "notes": "generator failed",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            })
        # Gentle pacing if upstream is rate-limited
        if provider == "gemini":
            time.sleep(1.0)

    payload = {
        "model": model,
        "provider": provider,
        "generator_total_tokens": {"input": total_in, "output": total_out},
        "queries": queries,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    QUERIES_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[generate] wrote {QUERIES_FILE} ({len(queries)} queries; tokens in={total_in} out={total_out})")
    return payload


# ── Step 2: SPARQL execution ────────────────────────────────────────
def _format_value(val: Any) -> Any:
    if val is None:
        return None
    s = str(val)
    # Strip language tags and datatype annotations rdflib often appends
    return s


def execute_sparql(query: str, graph: Graph, top_n: int = RESULT_ROW_CAP) -> dict[str, Any]:
    if not query or query.strip().upper().startswith("UNSUPPORTED") or query.strip() == "UNSUPPORTED":
        return {"status": "unsupported", "row_count": 0, "rows": [], "error": None}
    try:
        result = graph.query(query)
    except Exception as exc:
        return {
            "status": "error",
            "row_count": 0,
            "rows": [],
            "error": str(exc)[:500],
        }

    rows = []
    var_names = [str(v) for v in (result.vars or [])]
    count = 0
    for row in result:
        count += 1
        if len(rows) < top_n:
            row_obj = {}
            for var_name, val in zip(var_names, row):
                row_obj[var_name] = _format_value(val)
            rows.append(row_obj)
    return {
        "status": "ok" if count > 0 else "empty",
        "row_count": count,
        "rows": rows,
        "error": None,
    }


def step_execute(queries_payload: dict[str, Any]) -> dict[str, Any]:
    print(f"[execute] loading V1 KG: {V1_KG}")
    v1_graph = Graph()
    v1_graph.bind("av", AV)
    v1_graph.parse(V1_KG, format="turtle")
    print(f"          {len(v1_graph)} triples")

    print(f"[execute] loading V2 KG: {V2_KG}")
    v2_graph = Graph()
    v2_graph.bind("av", AV)
    v2_graph.parse(V2_KG, format="turtle")
    print(f"          {len(v2_graph)} triples")

    results = []
    for q in queries_payload["queries"]:
        cq_id = q.get("cq_id")
        v1_run = execute_sparql(q.get("v1_query", ""), v1_graph)
        v2_run = execute_sparql(q.get("v2_query", ""), v2_graph)
        # Carry unsupported reason through to results for the judge
        if v1_run["status"] == "unsupported" and q.get("v1_unsupported_reason"):
            v1_run["unsupported_reason"] = q["v1_unsupported_reason"]
        results.append({
            "cq_id": cq_id,
            "v1_query": q.get("v1_query"),
            "v2_query": q.get("v2_query"),
            "v1_run": v1_run,
            "v2_run": v2_run,
        })
        v1_tag = v1_run["status"]
        v2_tag = v2_run["status"]
        print(f"  {cq_id}: V1={v1_tag}({v1_run['row_count']})  V2={v2_tag}({v2_run['row_count']})")

    payload = {"results": results}
    RESULTS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[execute] wrote {RESULTS_FILE}")
    return payload


# ── Step 3: LLM judge ──────────────────────────────────────────────
JUDGE_SYSTEM = (
    "You are an evaluator scoring SPARQL query answers against an aviation "
    "Competency Question. You will see:\n"
    "- The CQ (question, expected_answer, required_concepts)\n"
    "- The V1 query (or UNSUPPORTED) and V1 result rows\n"
    "- The V2 query and V2 result rows\n\n"
    "Scoring rubric per side:\n"
    "  1.0  result rows clearly contain the entities/relations called for by the "
    "expected_answer or required_concepts.\n"
    "  0.5  result is partially relevant — covers some concepts, misses others, "
    "or contains noise that would confuse an end user.\n"
    "  0.0  result is empty, errored, UNSUPPORTED, or unrelated.\n\n"
    "Be conservative: do not give credit for keyword overlap if the structural "
    "answer the CQ asks for is missing. Free-text fields that happen to contain "
    "the keyword usually score 0.5 at best.\n\n"
    "Output strict JSON:\n"
    "{\n"
    '  "v1_score": 0 | 0.5 | 1,\n'
    '  "v2_score": 0 | 0.5 | 1,\n'
    '  "v1_reasoning": "1-2 sentence justification",\n'
    '  "v2_reasoning": "1-2 sentence justification",\n'
    '  "structural_win": true | false  // true if V1 is UNSUPPORTED or 0 AND V2 >= 0.5\n'
    "}\n"
)


def judge_cq(
    cq: dict[str, Any],
    result_row: dict[str, Any],
    client: OpenAI,
    model: str,
) -> dict[str, Any]:
    def trim_rows(run: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": run.get("status"),
            "row_count": run.get("row_count"),
            "rows": run.get("rows", [])[:10],  # keep judge payload small
            "error": run.get("error"),
            "unsupported_reason": run.get("unsupported_reason"),
        }

    payload = {
        "cq": {
            "id": cq.get("id"),
            "question": cq.get("question"),
            "expected_answer": cq.get("expected_answer"),
            "required_concepts": cq.get("required_concepts", []),
        },
        "v1_query": result_row.get("v1_query"),
        "v1_run": trim_rows(result_row["v1_run"]),
        "v2_query": result_row.get("v2_query"),
        "v2_run": trim_rows(result_row["v2_run"]),
    }
    user_msg = json.dumps(payload, indent=2)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "{}"
    judgment = parse_json_response(raw)
    usage = response.usage
    return {
        "cq_id": cq.get("id"),
        "v1_score": float(judgment.get("v1_score", 0)),
        "v2_score": float(judgment.get("v2_score", 0)),
        "v1_reasoning": judgment.get("v1_reasoning", ""),
        "v2_reasoning": judgment.get("v2_reasoning", ""),
        "structural_win": bool(judgment.get("structural_win", False)),
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        },
    }


def step_judge(
    cqs_by_id: dict[str, dict[str, Any]],
    results_payload: dict[str, Any],
    judge_model: str,
) -> dict[str, Any]:
    client, model, provider = create_llm_client(judge_model)
    print(f"[judge] provider={provider} model={model}")
    scores = []
    total_in = total_out = 0
    for row in results_payload["results"]:
        cq_id = row["cq_id"]
        cq = cqs_by_id.get(cq_id)
        if not cq:
            continue
        try:
            score = judge_cq(cq, row, client, model)
            scores.append(score)
            total_in += score["usage"]["prompt_tokens"]
            total_out += score["usage"]["completion_tokens"]
            mark = "*" if score["structural_win"] else " "
            print(f"  {cq_id}{mark} V1={score['v1_score']} V2={score['v2_score']}")
        except Exception as exc:
            print(f"  {cq_id} judge error: {exc}")
            scores.append({
                "cq_id": cq_id,
                "v1_score": 0.0,
                "v2_score": 0.0,
                "v1_reasoning": f"judge failed: {exc}",
                "v2_reasoning": f"judge failed: {exc}",
                "structural_win": False,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            })
        if provider == "gemini":
            time.sleep(1.0)

    payload = {
        "model": model,
        "provider": provider,
        "judge_total_tokens": {"input": total_in, "output": total_out},
        "scores": scores,
    }
    SCORES_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[judge] wrote {SCORES_FILE} (tokens in={total_in} out={total_out})")
    return payload


# ── Step 4: Report ─────────────────────────────────────────────────
def write_report(
    cqs_by_id: dict[str, dict[str, Any]],
    queries_payload: dict[str, Any],
    results_payload: dict[str, Any],
    scores_payload: dict[str, Any],
) -> None:
    scores = scores_payload["scores"]
    results_by_id = {r["cq_id"]: r for r in results_payload["results"]}
    queries_by_id = {q["cq_id"]: q for q in queries_payload["queries"]}

    total_v1 = sum(s["v1_score"] for s in scores)
    total_v2 = sum(s["v2_score"] for s in scores)
    n = len(scores)
    structural_wins = [s for s in scores if s["structural_win"]]

    def hist(values):
        return {
            "0": sum(1 for v in values if v == 0.0),
            "0.5": sum(1 for v in values if v == 0.5),
            "1": sum(1 for v in values if v == 1.0),
        }

    v1_hist = hist([s["v1_score"] for s in scores])
    v2_hist = hist([s["v2_score"] for s in scores])

    lines = [
        "# CQ SPARQL Benchmark — V1 vs V2 Ontology",
        "",
        f"- Scored CQs: **{n}**",
        f"- Generator model: `{queries_payload.get('model')}`  ({queries_payload.get('provider')})",
        f"- Judge model: `{scores_payload.get('model')}`  ({scores_payload.get('provider')})",
        "",
        "## Summary",
        "",
        f"| Metric | V1 | V2 |",
        f"|---|---:|---:|",
        f"| Total score | {total_v1:.1f} / {n} | {total_v2:.1f} / {n} |",
        f"| Avg score | {total_v1 / n if n else 0:.3f} | {total_v2 / n if n else 0:.3f} |",
        f"| 1.0 | {v1_hist['1']} | {v2_hist['1']} |",
        f"| 0.5 | {v1_hist['0.5']} | {v2_hist['0.5']} |",
        f"| 0.0 | {v1_hist['0']} | {v2_hist['0']} |",
        "",
        f"**Structural wins (V1 fails, V2 ≥ 0.5):** {len(structural_wins)}",
        "",
        f"**Token cost:** generator in={queries_payload.get('generator_total_tokens', {}).get('input', 0)} "
        f"out={queries_payload.get('generator_total_tokens', {}).get('output', 0)}; "
        f"judge in={scores_payload.get('judge_total_tokens', {}).get('input', 0)} "
        f"out={scores_payload.get('judge_total_tokens', {}).get('output', 0)}",
        "",
        "## Per-CQ scores",
        "",
        "| CQ | Question | V1 | V2 | Struct. win |",
        "|---|---|---:|---:|:---:|",
    ]
    for s in scores:
        cq = cqs_by_id.get(s["cq_id"], {})
        q_text = (cq.get("question") or "")[:90].replace("|", "\\|")
        sw = "✅" if s["structural_win"] else ""
        lines.append(f"| {s['cq_id']} | {q_text} | {s['v1_score']} | {s['v2_score']} | {sw} |")

    # Top structural wins detail
    if structural_wins:
        lines.append("")
        lines.append("## Top structural wins (V2 unlocks queries V1 cannot express)")
        lines.append("")
        sw_sorted = sorted(structural_wins, key=lambda s: -s["v2_score"])[:5]
        for s in sw_sorted:
            cq = cqs_by_id.get(s["cq_id"], {})
            q = queries_by_id.get(s["cq_id"], {})
            r = results_by_id.get(s["cq_id"], {})
            v2_run = r.get("v2_run", {})
            lines.extend([
                f"### {s['cq_id']} — {cq.get('question', '')}",
                f"- Expected: {cq.get('expected_answer', '')}",
                f"- V1: **{s['v1_score']}** — {s['v1_reasoning']}",
                f"- V2: **{s['v2_score']}** — {s['v2_reasoning']}",
                "",
                "V2 query:",
                "```sparql",
                (q.get("v2_query") or "").strip(),
                "```",
                "",
                f"V2 result rows (first {min(len(v2_run.get('rows', [])), 5)} of {v2_run.get('row_count', 0)}):",
                "```json",
                json.dumps(v2_run.get("rows", [])[:5], indent=2),
                "```",
                "",
            ])

    # Failure cases — both 0
    both_zero = [s for s in scores if s["v1_score"] == 0 and s["v2_score"] == 0]
    if both_zero:
        lines.append("")
        lines.append("## Failure cases (V1 = 0 and V2 = 0)")
        lines.append("")
        lines.append("These reveal data-quality gaps, not schema gaps — candidates for LLM re-extraction.")
        lines.append("")
        for s in both_zero:
            cq = cqs_by_id.get(s["cq_id"], {})
            lines.append(f"- **{s['cq_id']}**: {cq.get('question', '')}  \n  V2 reason: {s['v2_reasoning']}")

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"[report] wrote {REPORT_FILE}")
    print()
    print(f"Summary: V1 {total_v1:.1f}/{n}   V2 {total_v2:.1f}/{n}   structural wins: {len(structural_wins)}")


# ── Orchestrator ───────────────────────────────────────────────────
def load_cqs() -> list[dict[str, Any]]:
    data = json.loads(CQ_FILE.read_text(encoding="utf-8"))
    return data.get("competency_questions", [])


def load_queries_for_execution(use_reviewed: bool) -> dict[str, Any]:
    if use_reviewed and REVIEWED_FILE.exists():
        print(f"[load] using reviewed queries: {REVIEWED_FILE}")
        return json.loads(REVIEWED_FILE.read_text(encoding="utf-8"))
    if REVIEWED_FILE.exists():
        print(f"[load] reviewed file exists but --use-reviewed not set; using raw queries")
    return json.loads(QUERIES_FILE.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="CQ-based SPARQL benchmark for V1 vs V2 ontology")
    parser.add_argument(
        "--steps",
        default="generate,execute,judge,report",
        help="Comma-separated subset of: generate, execute, judge, report",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N CQs")
    parser.add_argument("--use-reviewed", action="store_true",
                        help="Use sparql_queries.reviewed.json when running execute")
    parser.add_argument("--judge-model", default=JUDGE_MODEL_DEFAULT,
                        help=f"Model name for the judge (default: {JUDGE_MODEL_DEFAULT})")
    args = parser.parse_args()

    steps = {s.strip() for s in args.steps.split(",") if s.strip()}
    cqs = load_cqs()
    if args.limit is not None:
        cqs = cqs[:args.limit]
    cqs_by_id = {cq["id"]: cq for cq in cqs}
    print(f"Loaded {len(cqs)} CQs from {CQ_FILE}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if "generate" in steps:
        step_generate(cqs, limit=None)  # cqs already limited

    if "execute" in steps:
        queries_payload = load_queries_for_execution(args.use_reviewed)
        # When --limit is set during a downstream-only run, filter the loaded queries too
        if args.limit is not None:
            queries_payload = dict(queries_payload)
            queries_payload["queries"] = [
                q for q in queries_payload["queries"] if q["cq_id"] in cqs_by_id
            ]
        step_execute(queries_payload)

    if "judge" in steps:
        results_payload = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        if args.limit is not None:
            results_payload["results"] = [
                r for r in results_payload["results"] if r["cq_id"] in cqs_by_id
            ]
        step_judge(cqs_by_id, results_payload, args.judge_model)

    if "report" in steps:
        queries_payload = load_queries_for_execution(args.use_reviewed)
        results_payload = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        scores_payload = json.loads(SCORES_FILE.read_text(encoding="utf-8"))
        if args.limit is not None:
            queries_payload["queries"] = [q for q in queries_payload["queries"] if q["cq_id"] in cqs_by_id]
            results_payload["results"] = [r for r in results_payload["results"] if r["cq_id"] in cqs_by_id]
            scores_payload["scores"] = [s for s in scores_payload["scores"] if s["cq_id"] in cqs_by_id]
        write_report(cqs_by_id, queries_payload, results_payload, scores_payload)


if __name__ == "__main__":
    main()
