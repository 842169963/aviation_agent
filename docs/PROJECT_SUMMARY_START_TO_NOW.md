# Aviation Project Summary - From Start To Current State

Generated: 2026-04-27

This document summarizes the aviation AI project from the initial presentation stage to the current runnable UI demo. It consolidates the project-level Markdown files, session summaries, prototype code, data files, generated outputs, and recent Git history.

## Does This Document Already Exist?

Before this file, the repository had several stage-specific summaries, but no single complete "from start to now" project summary.

Existing related documents:

- `aviation_presentation_summary.md`: early conceptual summary for ontology, knowledge extraction, RAG, and agentic AI.
- `simple_shacl_linkml_ontogpt_summary.md`: short explanation of LinkML, OntoGPT, and SHACL.
- `HANDOFF.md`: early handoff after the first prototype and presentation materials.
- `SESSION_SUMMARY_4_17.md`: FAA PDF parsing and Chapter 18 text extraction.
- `SESSION_SUMMARY_4_20.md`: full extraction pipeline cleanup, provider support, provenance, and KG validation.
- `SESSION_SUMMARY_4_21.md`: targeted re-extraction and data quality repair.
- `SESSION_SUMMARY_4_22_hybrid_rag.md`: Hybrid RAG retrieval prototype.
- `SESSION_SUMMARY_4_27_ui_demo.md`: FastAPI UI demo and latest runnable state.
- `aviation_prototype/README.md`: current runbook for the prototype and demo.
- `aviation_prototype/HYBRID_RAG_V1.md`: design plan for Hybrid RAG v1.

So the answer is: there were good partial summaries, but this file is the first consolidated end-to-end summary.

## 1. Original Project Goal

The project goal is to build a grounded AI decision-support system for private pilots.

The system is not intended to replace the pilot. It is intended to help a pilot in abnormal or emergency situations by retrieving relevant FAA-backed procedures and presenting short, structured, evidence-based guidance.

Core motivation:

- Private pilots often fly less frequently than professional pilots.
- Rare emergency or abnormal situations are hard to recall under stress.
- FAA handbooks and checklists exist, but they are static documents.
- A flight situation is dynamic, time-sensitive, and context-dependent.
- A useful advisor should retrieve grounded procedure knowledge instead of generating unsupported advice.

The project therefore explores:

```text
FAA manuals / checklists
  -> structured knowledge extraction
  -> ontology / schema modeling
  -> knowledge graph construction
  -> SHACL validation
  -> Hybrid RAG retrieval
  -> grounded synthesis
  -> future agentic orchestration
  -> pilot-facing advisory UI
```

## 2. Initial Presentation Work

The earliest work focused on explaining the conceptual pipeline and the role of three core technologies:

- LinkML
- OntoGPT
- SHACL

The presentation materials include:

- `aviation_ai_presentation.pptx`
- `aviation_ai_v2.pptx`
- `4.14.ppt`
- `aviation_presentation_summary.md`
- `simple_shacl_linkml_ontogpt_summary.md`

The key distinction established at this stage was:

```text
LinkML defines the target schema.
OntoGPT or an LLM extracts structured knowledge from text.
SHACL validates the resulting graph data.
```

The presentation also introduced the larger idea:

```text
Ontology / schema
  + knowledge extraction
  + graph validation
  + retrieval
  + agentic orchestration
  = grounded aviation advisory assistant
```

## 3. First Runnable Prototype

The first runnable Python prototype lives in:

```text
aviation_prototype/
```

The original prototype had a small EFATO-focused sample:

```text
data/efato_sample.txt
```

The initial pipeline was:

```text
01_extract.py
  -> output/extracted.json
02_validate.py
  -> output/kg.ttl
  -> output/validation_report.txt
03_query.py
  -> command-line advisory output
```

The first schema centered on:

- `EmergencyProcedure`
- `ProcedureStep`
- `Warning`

The first SHACL constraints checked basic data validity, such as:

- a procedure must have a name
- a procedure must have at least one step
- each step must have an action
- each step must have a step number

This stage proved that a small piece of aviation text could be converted into a validated RDF knowledge graph and queried in a pilot-readable way.

## 4. FAA Chapter 18 Integration

The next major step was moving beyond the toy EFATO sample and into real FAA source material.

The relevant FAA source is:

```text
aviation_prototype/data/19_afh_ch18.pdf
```

Important correction:

- Earlier notes referred to Emergency Procedures as Chapter 17.
- In FAA-H-8083-3C, Emergency Procedures is Chapter 18.

Script added:

```text
aviation_prototype/scripts/00_pdf_parse.py
```

Purpose:

- parse the FAA PDF
- clean page text
- split Chapter 18 into smaller procedure text files
- write outputs into `data/procedures/`

Current active text dataset:

```text
aviation_prototype/data/procedures/
```

It contains 35 formal text chunks listed by:

```text
aviation_prototype/data/procedures/index.txt
```

Examples:

- `12_engine_failure_after_takeoff_single_engine.txt`
- `13_emergency_descents.txt`
- `16_electrical_fires.txt`
- `17_cabin_fire.txt`
- `20_landing_gear_malfunction.txt`
- `24_inadvertent_vfr_flight_into_imc.txt`
- `33_ballistic_parachutes.txt`

This made the prototype source-grounded in real FAA handbook material instead of a manually written sample only.

## 5. Extraction Pipeline Improvements

The extraction script evolved substantially:

```text
aviation_prototype/scripts/01_extract.py
```

Important capabilities added:

- single-file extraction mode
- batch extraction mode with `--input-dir data/procedures`
- reading formal input order from `index.txt`
- OpenAI-compatible provider support
- Gemini provider support
- `OPENAI_BASE_URL` support for ChatAnywhere-style forwarding
- `MODEL_NAME`, `LLM_PROVIDER`, and embedding/synthesis model configuration
- JSON cleanup and parsing logic
- procedure normalization and deduplication
- protection against overwriting good output when extraction fails
- provenance fields at procedure and step level

Important note:

```bash
python scripts/01_extract.py
```

is only the small sample mode. It reads `data/efato_sample.txt` and can overwrite the output with only two toy procedures.

The formal pipeline uses:

```bash
python scripts/01_extract.py --input-dir data/procedures
```

## 6. Provenance And Data Quality

The project added source-grounding fields so the advisor can show where each procedure and step came from.

Current provenance fields include:

- `EmergencyProcedure.source_file`
- `EmergencyProcedure.source_section`
- `EmergencyProcedure.source_excerpt`
- `ProcedureStep.source_excerpt`

This is important because the system should not only retrieve a procedure; it should be able to show evidence from the original FAA text.

The project also discovered that broad batch extraction was not enough for all FAA sections. Some procedures needed targeted re-extraction.

Script added:

```text
aviation_prototype/scripts/04_targeted_reextract.py
```

Purpose:

- repair low-quality or missing extracted procedures
- avoid rerunning all 35 source files every time
- merge targeted replacements back into `output/extracted.json`

Important repaired cases:

- `Snow Landing`
- `Inadvertent VFR Flight Into IMC`
- `Ballistic Parachute Deployment`

Key finding:

`Inadvertent VFR Flight Into IMC` was not simply extracted poorly. Its source material was split across multiple text files, so the repair had to treat files 24 through 31 as one grouped procedure context.

## 7. Knowledge Graph And SHACL Validation

The validation script is:

```text
aviation_prototype/scripts/02_validate.py
```

It reads:

```text
output/extracted.json
```

and writes:

```text
output/kg.ttl
output/validation_report.txt
```

The SHACL shapes live in:

```text
aviation_prototype/shacl/procedure_shapes.ttl
```

The RDF graph stores:

- emergency procedures
- ordered steps
- warnings
- source fields
- step types

Latest verified state:

```text
Procedures in KG: 18
Procedure steps: 89
Warnings: 23
SHACL validation: PASS
```

## 8. Step Type Classification

The project later added `ProcedureStep.step_type`.

Purpose:

The system needs to separate what a pilot should do immediately from what is a training note or caution.

Current step type categories include:

```text
immediate_action
caution
training_note
background
```

This matters especially for aviation safety. For example:

- "Lower the nose" is an immediate EFATO action.
- "Practice turnbacks at a safe altitude" is a training note.
- "Do not attempt a turnback unless assured" is a caution.

The grounded synthesis layer should not mix these categories.

## 9. Hybrid RAG Retrieval

The project then added Hybrid RAG v1.

Design document:

```text
aviation_prototype/HYBRID_RAG_V1.md
```

Scripts:

```text
aviation_prototype/scripts/05_build_vector_index.py
aviation_prototype/scripts/06_hybrid_query.py
```

The vector index is stored locally at:

```text
aviation_prototype/output/vector_index/
```

This directory is ignored by Git because it is a local generated artifact.

Hybrid retrieval has two channels:

```text
KG channel:
  exact/keyword matching over structured fields

Vector channel:
  semantic retrieval over procedure-level documents
```

The merge strategy is simple:

```text
final_score = kg_score + vector_score
```

Important design rule:

Vector retrieval only finds candidate procedures. The final steps, warnings, and evidence are still read from the validated KG.

This prevents unvalidated vector chunks from becoming the final answer source.

Important success example:

```text
Question: accidentally flew into clouds
Expected procedure: Inadvertent VFR Flight Into IMC
```

The user does not say `IMC`, so keyword matching may fail. The vector channel can still retrieve the correct procedure.

## 10. Grounded LLM Synthesis

The hybrid query script then gained an optional synthesis mode:

```bash
python scripts/06_hybrid_query.py --question "accidentally flew into clouds" --synthesis-only --top-k 1 --no-debug
```

The synthesis model receives only retrieved KG context and is instructed not to invent:

- checklist steps
- speeds
- altitudes
- frequencies
- aircraft-specific limits
- causal claims

The generated answer is structured into:

1. likely relevant procedure
2. operational actions from the KG
3. training/preparation/background notes from the KG
4. procedure-specific warnings from the KG
5. source/evidence note and safety disclaimer

This moved the system from "retrieval output" toward "pilot-readable advisor response", while keeping the response grounded in the KG.

## 11. Evaluation Harness

The evaluation script is:

```text
aviation_prototype/scripts/07_eval_hybrid_rag.py
```

The latest report is:

```text
aviation_prototype/output/hybrid_eval_report.md
```

The evaluation checks:

- happy-path retrieval
- semantic variants
- ambiguous cases
- out-of-scope abstention behavior
- optional synthesis checks

Latest verified result:

```text
Retrieval evaluation: 14/14 PASS
Synthesis evaluation: 9/10 PASS
```

The remaining issue:

```text
happy_efato synthesis: practice turns training note missing entirely
```

Interpretation:

Retrieval is currently strong. The remaining problem is synthesis stability around preserving training notes without mixing them into operational actions.

## 12. UI Demo

The newest major addition is a browser-based UI demo.

Files:

```text
aviation_prototype/app/main.py
aviation_prototype/app/static/index.html
aviation_prototype/app/static/styles.css
aviation_prototype/app/static/app.js
```

Dependencies added:

```text
fastapi
uvicorn
```

The UI exposes:

```text
POST /api/query
GET /api/health
```

The backend currently reuses `scripts/06_hybrid_query.py` rather than duplicating retrieval logic.

Current flow:

```text
User question in browser
  -> FastAPI /api/query
  -> load KG
  -> KG retrieval
  -> vector retrieval
  -> merge candidates
  -> grounded synthesis
  -> JSON response
  -> UI renders procedure, actions, warnings, evidence, and answer
```

Verified smoke tests:

```text
/api/health -> {"status":"ok"}
smoke in cabin -> Cabin Fire
accidentally flew into clouds -> Inadvertent VFR Flight Into IMC
```

Run command:

```powershell
cd "E:\aviation project\aviation_prototype"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Good demo questions:

```text
accidentally flew into clouds
smoke in cabin
engine failure after takeoff
pilot incapacitated parachute
landing on snow whiteout
```

## 13. Current File Map

High-level repository files:

```text
aviation_presentation_summary.md
simple_shacl_linkml_ontogpt_summary.md
HANDOFF.md
SESSION_SUMMARY_4_17.md
SESSION_SUMMARY_4_20.md
SESSION_SUMMARY_4_21.md
SESSION_SUMMARY_4_22_hybrid_rag.md
SESSION_SUMMARY_4_27_ui_demo.md
PROJECT_SUMMARY_START_TO_NOW.md
aviation_ai_presentation.pptx
aviation_ai_v2.pptx
4.14.ppt
aviation_prototype/
```

Prototype structure:

```text
aviation_prototype/
  app/
  data/
  output/
  schema/
  scripts/
  shacl/
  README.md
  HYBRID_RAG_V1.md
  requirements.txt
```

Important generated outputs:

```text
output/extracted.json
output/kg.ttl
output/validation_report.txt
output/hybrid_eval_report.md
output/vector_index/
```

Important note:

`output/vector_index/` is generated locally and ignored by Git.

## 14. Current Git State

Recent commits:

```text
3a596b3 Add aviation advisor UI demo
669e9b3 Add step type classification to procedure KG
90e5cbb Add hybrid RAG evaluation harness
64ce19c Refine grounded synthesis sections
508d79c Add grounded synthesis mode to hybrid query
e5287c0 Add hybrid RAG retrieval prototype
b3922a7 Initial commit: aviation prototype and targeted re-extraction workflow
```

Current branch state at the time this document was created:

```text
main is ahead of origin/main by 5 commits
```

There is also an untracked `.vscode/` directory, which appears to be local editor configuration and has not been included in project commits.

## 15. Current Technical Stack

Core:

- Python
- OpenAI-compatible chat completions and embeddings
- ChatAnywhere-compatible `OPENAI_BASE_URL`
- rdflib
- pyshacl
- pdfplumber
- ChromaDB
- FastAPI
- Uvicorn

Data representation:

- LinkML-style YAML schema
- JSON extracted instances
- RDF Turtle knowledge graph
- SHACL validation shapes
- ChromaDB vector index

## 16. What Has Been Proven

The project has proven the following:

1. FAA handbook text can be split into procedure-level text chunks.
2. LLM extraction can produce structured emergency procedure instances.
3. Extracted data can be converted to RDF.
4. SHACL can validate the knowledge graph before it is used by the advisor.
5. Hybrid KG + vector retrieval improves natural-language recall.
6. The system can find the right procedure even when the user does not use the official FAA term.
7. Grounded synthesis can produce a concise advisor-style response from KG evidence.
8. A browser UI can demonstrate the pipeline end to end.

## 17. Current Limitations

Important limitations:

- The system is still a prototype, not an operational aviation safety product.
- English queries are more reliable because the FAA source data and KG fields are English.
- Cross-lingual queries may work through embeddings, but they are less stable.
- Synthesis is mostly grounded, but one EFATO training-note case still fails evaluation.
- Some FAA text is narrative or diagnostic and does not fit cleanly into the current `EmergencyProcedure` schema.
- The current graph is file/chunk based and does not yet include page-level or line-level provenance.
- There is no LangGraph orchestration layer yet.
- There is no aircraft-specific POH/AFM adaptation yet.
- There is no real-time aircraft state or sensor integration yet.

## 18. Recommended Next Steps

Near-term presentation path:

1. Use the UI demo to show the working system.
2. Demonstrate semantic retrieval with `accidentally flew into clouds`.
3. Demonstrate source-grounded actions, warnings, and evidence.
4. Explain that the UI currently wraps the existing Hybrid RAG backend.

Next engineering steps:

1. Fix EFATO synthesis so `practice turns` training notes are preserved in the correct section.
2. Create a high-quality EFATO golden instance.
3. Use the golden instance to tighten schema quality and synthesis evaluation.
4. Add LangGraph behind the existing `/api/query` endpoint.
5. Add an intent/safety gate:
   - aviation emergency / abnormal query
   - ambiguous query
   - out-of-scope query
6. Add better abstention behavior for unrelated queries.
7. Continue improving provenance quality.

LangGraph integration path:

```text
UI /api/query
  -> advisor_graph.invoke(...)
  -> classify intent
  -> retrieve via KG/vector
  -> safety gate
  -> grounded synthesis
  -> response formatting
```

The current UI was intentionally designed so this future backend swap can happen without redesigning the frontend.

## 19. One-Sentence Summary

This project has evolved from a conceptual presentation on LinkML, OntoGPT, SHACL, ontology, and Hybrid RAG into a runnable aviation advisory prototype that parses FAA emergency procedure text, builds a SHACL-validated knowledge graph, performs Hybrid KG/vector retrieval, generates grounded advisor responses, evaluates retrieval/synthesis quality, and exposes the workflow through a browser UI demo.
