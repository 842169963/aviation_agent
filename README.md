# Aviation Agentic AI — Grounded Emergency Advisor for Private Pilots

A research prototype that turns FAA handbook text into a **SHACL-validated knowledge graph**, retrieves from it with **Hybrid RAG (KG + vector)**, and generates **grounded** advisory answers for abnormal and emergency flight situations.

The design rule of the whole project: the LLM never invents flight advice. It extracts and rephrases; every step, warning, and piece of evidence in an answer comes from the validated graph.

> ⚠️ Research prototype, not an operational aviation safety product. Do not use it for real flight decisions.

## Why

Private pilots fly less often than professional pilots and are more likely to forget the correct procedure under stress. FAA handbooks contain the right answers but are static documents, while a flight situation is dynamic and time-critical. This project explores whether ontology + knowledge graph + retrieval can turn that static text into a trustworthy, evidence-backed advisor.

## Pipeline

```text
FAA AFH Ch.18 PDF
  -> text chunks (35 procedure sections)
  -> LLM extraction  ->  structured procedure instances (JSON)
  -> RDF knowledge graph (Turtle)
  -> SHACL validation
  -> ChromaDB vector index
  -> Hybrid retrieval (KG keyword channel + vector channel)
  -> grounded LLM synthesis
  -> FastAPI + browser UI
```

Vector retrieval only selects *candidate procedures*. The steps, warnings, and evidence shown to the user are always read back from the validated KG.

## Current state

| | |
|---|---|
| Source chunks | 35 |
| Procedures in KG | 18 |
| Procedure steps | 89 |
| Warnings | 23 |
| SHACL validation | PASS |
| Retrieval eval | 14 / 14 PASS |
| Synthesis eval | 9 / 10 PASS |

Ontology V2 experiment (`ontology` branch): the V1 schema (4 classes / 15 attributes, 818 triples) was extended to a controlled V2 (10 classes / 33 attributes, 2611 triples) adding `SourceEvidence`, `TriggerCondition`, `FlightPhase`, `Hazard`, `AircraftState`, `AircraftSystem`. On a 35-question CQ→SPARQL benchmark, V2 scored **17.0/35 vs V1's 12.0/35**, with 10 CQs answerable only under V2. See the [V1 vs V2 report](aviation_prototype/output/schema_v2/ontology_v1_vs_v2_report.md) and the [CQ benchmark report](aviation_prototype/output/cq_benchmark/benchmark_report.md).

## Quickstart

```bash
cd aviation_prototype
python -m venv .venv && .venv/Scripts/activate    # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then add your API key
```

The extracted data and `kg.ttl` are committed, but the vector index is a local artifact — build it once, then start the demo:

```bash
python scripts/05_build_vector_index.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` and try: `accidentally flew into clouds`, `smoke in cabin`, `engine failure after takeoff`, `landing on snow whiteout`.

Rebuild the full pipeline from source text:

```bash
python scripts/01_extract.py --input-dir data/procedures
python scripts/04_targeted_reextract.py
python scripts/02_validate.py
python scripts/05_build_vector_index.py
python scripts/07_eval_hybrid_rag.py --include-synthesis
```

Note: running `01_extract.py` **without** `--input-dir` is the small smoke-test mode — it reads only `data/efato_sample.txt` and overwrites `output/extracted.json` with a two-procedure toy sample.

Full runbook, provider configuration, and demo commands: [aviation_prototype/README.md](aviation_prototype/README.md).

## Repository layout

```text
README.md                     this file
aviation_prototype/           the runnable system
  app/                        FastAPI backend + static UI
  data/                       FAA source PDF and the 35 procedure text chunks
  schema/                     LinkML-style YAML schemas (v1, v2)
  shacl/                      SHACL shapes (v1, v2)
  scripts/                    00-11, the numbered pipeline stages
  output/                     generated KG, reports, benchmarks
  README.md                   detailed runbook
  HYBRID_RAG_V1.md            Hybrid RAG design notes
docs/                         project documentation and history
  PROJECT_SUMMARY_START_TO_NOW.md   consolidated end-to-end summary
  HANDOFF.md                        early handoff notes
  original_project_brief.md         the original problem statement
  aviation_presentation_summary.md  conceptual overview
  simple_shacl_linkml_ontogpt_summary.md   LinkML / OntoGPT / SHACL primer
  sessions/                   per-session working notes
  presentations/              slide decks
```

### Pipeline scripts

| Script | Purpose |
|---|---|
| `00_pdf_parse.py` | Parse the FAA PDF, split Chapter 18 into procedure text chunks |
| `01_extract.py` | LLM extraction of structured procedures (single file or `--input-dir`) |
| `02_validate.py` | Build `kg.ttl` and run SHACL validation |
| `03_query.py` | Command-line KG query |
| `04_targeted_reextract.py` | Repair specific low-quality procedures without a full re-run |
| `05_build_vector_index.py` | Build the ChromaDB index |
| `06_hybrid_query.py` | Hybrid KG + vector retrieval, optional grounded synthesis |
| `07_eval_hybrid_rag.py` | Retrieval and synthesis regression evaluation |
| `08_extract_ontology_multi_agent.py` | Paper-inspired multi-agent ontology generation experiment |
| `09_migrate_to_schema_v2.py` | Deterministic migration of extracted data into the V2 ontology |
| `10_compare_ontology_versions.py` | V1 vs V2 schema / KG / CQ comparison report |
| `11_cq_sparql_benchmark.py` | 35-CQ SPARQL benchmark with LLM judge, V1 vs V2 |

## Stack

Python · OpenAI-compatible chat + embeddings · rdflib · pyshacl · pdfplumber · ChromaDB · FastAPI · Uvicorn. Data is represented as LinkML-style YAML schema → JSON instances → RDF Turtle → SHACL shapes → vector index.

## Configuration

`.env` in `aviation_prototype/` (see `.env.example`):

```bash
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.chatanywhere.tech/v1
MODEL_NAME=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
SYNTHESIS_MODEL=gpt-4o-mini
```

## Limitations

- Prototype quality; not validated for operational use.
- English queries are the reliable path — the FAA source and KG fields are English.
- One EFATO synthesis case still drops a `training_note` from the correct section.
- Provenance is file/chunk-level, not yet page or line level.
- No LangGraph orchestration, no aircraft-specific POH/AFM adaptation, no live aircraft state integration yet.

## Branches

- `main` — the Hybrid RAG prototype and UI demo.
- `ontology` — ontology V2 experiment, migration, and the CQ/SPARQL benchmark.

## Data and licensing notes

FAA *Airplane Flying Handbook* (FAA-H-8083-3C) material is US-government public domain. The `ontoloom/` directory, if present locally, is a **separate repository** (`gitlab.tu-clausthal.de/students/ontoloom`) and is intentionally excluded here. The third-party ontology-generation paper used for the V2 experiment is kept locally and not redistributed from this repository.
