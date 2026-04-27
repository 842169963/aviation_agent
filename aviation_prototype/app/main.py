from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "app" / "static"
HYBRID_QUERY_PATH = PROJECT_ROOT / "scripts" / "06_hybrid_query.py"


app = FastAPI(title="Aviation Advisor Demo")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    top_k: int = Field(default=3, ge=1, le=5)
    vector_top_k: int = Field(default=5, ge=1, le=10)
    synthesize: bool = True


class QueryResponse(BaseModel):
    question: str
    top_procedure: dict[str, Any] | None
    candidates: list[dict[str, Any]]
    advisor_response: str | None
    synthesis_model: str | None
    source_policy: str


def _load_hybrid_module():
    spec = importlib.util.spec_from_file_location("aviation_hybrid_query", HYBRID_QUERY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load hybrid query module: {HYBRID_QUERY_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def hybrid_module():
    return _load_hybrid_module()


def compact_text(value: str, limit: int = 260) -> str:
    module = hybrid_module()
    text = module.normalize_space(value or "")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def procedure_payload(record: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    steps = []
    for step in record.get("steps", []):
        steps.append(
            {
                "number": step.get("num"),
                "step_type": step.get("step_type") or "immediate_action",
                "action": step.get("action") or "",
                "expected_result": step.get("result") or "",
                "source_excerpt": compact_text(step.get("source_excerpt") or "", 220),
            }
        )

    return {
        "name": record.get("name"),
        "trigger": record.get("trigger"),
        "aircraft_phase": record.get("aircraft_phase"),
        "source_file": record.get("source_file"),
        "source_section": record.get("source_section"),
        "procedure_evidence": compact_text(record.get("proc_excerpt") or "", 300),
        "steps": steps,
        "warnings": [compact_text(item, 240) for item in record.get("warnings", [])],
        "score": {
            "final": candidate.get("final_score"),
            "kg": candidate.get("kg_score"),
            "vector": candidate.get("vector_score"),
            "vector_rank": candidate.get("vector_rank"),
            "distance": candidate.get("distance"),
            "matched_fields": candidate.get("matched_fields") or [],
        },
    }


def run_advisor_query(request: QueryRequest) -> QueryResponse:
    module = hybrid_module()
    graph = module.load_kg()
    records = module.load_procedure_records(graph)
    kg_hits = module.kg_retrieve(request.question, records)
    vector_hits = module.vector_retrieve(request.question, n_results=request.vector_top_k)
    candidates = module.merge_candidates(kg_hits, vector_hits, top_k=request.top_k)

    payloads = []
    for candidate in candidates:
        record = records.get(candidate["procedure_name"])
        if record:
            payloads.append(procedure_payload(record, candidate))

    advisor_response = None
    synthesis_model = None
    if request.synthesize and candidates:
        advisor_response, synthesis_model = module.synthesize_answer(
            request.question,
            records,
            candidates[:1],
        )

    return QueryResponse(
        question=request.question,
        top_procedure=payloads[0] if payloads else None,
        candidates=payloads,
        advisor_response=advisor_response,
        synthesis_model=synthesis_model,
        source_policy=(
            "Retrieval is hybrid; final procedure content is read from the validated KG. "
            "Always follow aircraft POH/AFM, ATC instructions, and pilot judgment."
        ),
    )


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/query", response_model=QueryResponse)
def query(request: QueryRequest):
    try:
        return run_advisor_query(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
