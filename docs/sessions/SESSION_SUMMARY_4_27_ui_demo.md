# Session Summary - 2026-04-27 UI Demo

This session moved the aviation prototype from a command-line Hybrid RAG workflow into a small browser-based demo that can be used for presentation.

## What Changed

### 1. Clarified the real pipeline

The README now separates two extraction modes:

- Formal FAA pipeline:
  ```bash
  python scripts/01_extract.py --input-dir data/procedures
  python scripts/04_targeted_reextract.py
  python scripts/02_validate.py
  python scripts/05_build_vector_index.py
  python scripts/07_eval_hybrid_rag.py --include-synthesis
  ```
- Small smoke-test pipeline:
  ```bash
  python scripts/01_extract.py
  python scripts/02_validate.py
  ```

The second mode only reads `data/efato_sample.txt` and overwrites `output/extracted.json` with a two-procedure toy sample, so it should not be treated as the full project dataset.

### 2. Re-ran the full data pipeline

The full FAA text pipeline was run from `data/procedures/`, followed by targeted re-extraction.

Current output state:

- Source text chunks: 35
- Procedures in KG: 18
- Procedure steps: 89
- Warnings: 23
- SHACL validation: PASS
- Retrieval evaluation: 14/14 PASS
- Synthesis evaluation: 9/10 PASS

The remaining synthesis issue is specific to EFATO: the retrieved procedure is correct, but one synthesis evaluation expects the `practice turns` training note to be preserved more reliably.

### 3. Added a FastAPI UI demo

New files:

- `aviation_prototype/app/main.py`
- `aviation_prototype/app/static/index.html`
- `aviation_prototype/app/static/styles.css`
- `aviation_prototype/app/static/app.js`

The UI calls:

```text
POST /api/query
```

The backend currently reuses the existing Hybrid RAG functions from `scripts/06_hybrid_query.py`:

```text
load KG
-> KG keyword retrieval
-> vector retrieval
-> merge candidates
-> grounded synthesis
-> JSON response for the UI
```

This keeps the future LangGraph integration simple: `/api/query` can later call `advisor_graph.invoke(...)` without redesigning the frontend.

### 4. Added demo dependencies

`requirements.txt` now includes:

- `fastapi`
- `uvicorn`

## How To Run The UI

From `aviation_prototype/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

Good demo queries:

```text
accidentally flew into clouds
smoke in cabin
engine failure after takeoff
pilot incapacitated parachute
landing on snow whiteout
```

## Verified Smoke Tests

API health:

```text
/api/health -> {"status":"ok"}
```

Query checks:

```text
accidentally flew into clouds -> Inadvertent VFR Flight Into IMC
smoke in cabin -> Cabin Fire
```

## Recommended Next Steps

1. Use the UI demo for presentation.
2. Fix the remaining EFATO synthesis issue so synthesis evaluation reaches 10/10.
3. Create an EFATO golden instance to stabilize data quality and synthesis evaluation.
4. Add LangGraph as the backend orchestration layer behind the existing `/api/query` endpoint.
