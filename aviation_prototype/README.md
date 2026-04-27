# Aviation Agentic AI Prototype

Private-pilot decision-support prototype for grounded aviation emergency guidance.

This project does not let an LLM freely invent flight advice. It extracts structured emergency procedures from FAA handbook text, validates them as a knowledge graph, retrieves relevant procedures with Hybrid RAG, and generates grounded advisory responses from validated evidence.

## Current Status

The current prototype supports an end-to-end pipeline:

```text
FAA chapter text chunks
  -> LLM extraction
  -> structured procedure instances
  -> RDF knowledge graph
  -> SHACL validation
  -> ChromaDB vector index
  -> Hybrid KG + vector retrieval
  -> grounded LLM synthesis
  -> regression evaluation
```

Latest verified run:

```text
Source text chunks: 35
Procedures in KG: 18
Procedure steps: 89
Warnings: 23
SHACL validation: PASS
Retrieval evaluation: 14/14 PASS
Synthesis evaluation: 9/10 PASS
```

The remaining synthesis issue is specific: the EFATO case retrieves the correct procedure, but one evaluation run did not preserve the `practice turns` training note in the generated response.

## Important: Two Extraction Modes

There are two ways to run `01_extract.py`.

### Formal FAA Procedure Pipeline

Use this for the full project and demos:

```bash
python scripts/01_extract.py --input-dir data/procedures
python scripts/04_targeted_reextract.py
python scripts/02_validate.py
python scripts/05_build_vector_index.py
python scripts/07_eval_hybrid_rag.py --include-synthesis
```

This reads the 35 FAA chapter text chunks in `data/procedures/`, applies targeted re-extraction for known difficult sections, and produces the current 18-procedure KG.

### Small Sample Pipeline

Use this only for a quick smoke test:

```bash
python scripts/01_extract.py
python scripts/02_validate.py
```

This reads only `data/efato_sample.txt` and overwrites `output/extracted.json` with a two-procedure toy sample. It is useful for fast testing, but it is not the full project dataset.

## Demo Commands

Start the local UI demo:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

Run a semantic retrieval example:

```bash
python scripts/06_hybrid_query.py --question "accidentally flew into clouds" --top-k 3 --no-debug
```

Expected top result:

```text
Inadvertent VFR Flight Into IMC
```

Run a grounded synthesis example:

```bash
python scripts/06_hybrid_query.py --question "accidentally flew into clouds" --synthesis-only --top-k 1 --no-debug
```

Run the regression evaluation:

```bash
python scripts/07_eval_hybrid_rag.py --include-synthesis
```

## Why Hybrid RAG

The system uses two retrieval channels:

- KG retrieval finds exact matches from structured fields such as procedure name, trigger condition, phase, step action, warning, and source evidence.
- Vector retrieval finds semantic matches when the user does not use the official FAA term.

Example:

```text
Question: accidentally flew into clouds
Official procedure: Inadvertent VFR Flight Into IMC
```

The user does not say `IMC`, but vector retrieval can still find the correct procedure. The final response is then built from validated KG content rather than free-form model memory.

## Step Types

`ProcedureStep.step_type` separates different kinds of procedural content:

```text
immediate_action
caution
training_note
background
```

This matters because a pilot-facing response should not mix training notes with immediate emergency actions. For example, practicing turnbacks at a safe altitude is a training note, not an in-flight EFATO action.

## About Golden Instances

A golden instance is a manually reviewed, high-quality procedure instance used as a reference standard.

The next recommended golden instance is:

```text
Engine Failure After Takeoff (Single-Engine)
```

It should preserve:

- immediate actions
- cautions
- training notes
- warnings
- FAA source evidence

Golden instances are not required before building a UI demo. They are mainly useful for improving data quality, checking schema coverage, and making synthesis evaluation stricter.

## Recommended Next Step

For a near-term presentation, build a small UI/demo first.

The UI should demonstrate:

```text
User question
  -> top retrieved procedure
  -> immediate actions
  -> warnings
  -> source evidence
  -> grounded advisor response
```

Good demo questions:

```text
accidentally flew into clouds
smoke in cabin
engine failure after takeoff
pilot incapacitated parachute
landing on snow whiteout
```

After the demo UI is in place, use EFATO as the first golden instance to fix the remaining synthesis-quality issue and make the system more reliable.

## File Structure

```text
aviation_prototype/
  data/
    efato_sample.txt
    procedures/
      index.txt
      *.txt
  schema/
    emergency_schema.yaml
  shacl/
    procedure_shapes.ttl
  scripts/
    00_pdf_parse.py
    01_extract.py
    02_validate.py
    03_query.py
    04_targeted_reextract.py
    05_build_vector_index.py
    06_hybrid_query.py
    07_eval_hybrid_rag.py
  output/
    extracted.json
    kg.ttl
    validation_report.txt
    hybrid_eval_report.md
    vector_index/
  requirements.txt
```

## LLM Provider

`01_extract.py` supports OpenAI-compatible providers.

Common environment variables:

```bash
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.chatanywhere.tech/v1
MODEL_NAME=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
SYNTHESIS_MODEL=gpt-4o-mini
```

Create `.env` from `.env.example` and add the required API key before running extraction, embedding, or synthesis.
