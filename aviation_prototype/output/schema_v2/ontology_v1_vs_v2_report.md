# Controlled Ontology V2 Comparison Report

Generated: 2026-05-12T14:39:17

## Question

This report answers the weekly task: use the paper-inspired method to generate a new ontology, compare it with the existing ontology, and explain whether it improves the project.

## Paper Method Applied Here

The paper's useful part is not blind replacement. It is artifact-driven planning: CQ generation, ontology planning, implementation, and QA. In this project, that produced 35 CQs and suggested richer ontology concepts. The controlled V2 below keeps only the useful concepts and fixes the modeling errors found in the raw LLM candidate.

## Schema Comparison

| Metric | Current V1 | Controlled V2 |
|---|---:|---:|
| Classes | 4 | 10 |
| Attributes | 15 | 33 |
| Required attributes | 7 | 14 |
| Enums | 1 | 1 |

V2 added ontology-level classes:

- `SourceEvidence`
- `TriggerCondition`
- `FlightPhase`
- `Hazard`
- `AircraftState`
- `AircraftSystem`

## KG Comparison

| Metric | Current V1 KG | Controlled V2 KG |
|---|---:|---:|
| RDF triples | 818 | 2611 |
| SHACL conforms | True | True |

Current V1 class instances:

`EmergencyProcedure: 18, ProcedureStep: 89, Warning: 23`

Controlled V2 class instances:

`AircraftState: 18, AircraftSystem: 101, EmergencyProcedure: 18, FlightPhase: 18, Hazard: 70, ProcedureStep: 89, SourceEvidence: 218, TriggerCondition: 18, Warning: 23`

## CQ Proxy Comparison

The 35 generated CQs are used here as a deterministic proxy. This is not yet a full LLM-judge/SPARQL benchmark. It measures whether expected-answer terms and CQ-required concepts are represented in the migrated data and schema vocabulary.

| Metric | Current V1 | Controlled V2 | Meaning |
|---|---:|---:|---|
| Avg expected-answer recall | 0.611 | 0.619 | Whether migrated data contains expected answer terms |
| Answer recall >= 0.5 | 23/35 | 23/35 | Rough answerability count |
| Avg question-term recall | 0.480 | 0.480 | Whether procedure text covers question context |
| Avg schema concept recall | 0.237 | 0.203 | Whether schema has vocabulary for CQ concepts |
| Avg schema relation recall | 0.041 | 0.056 | Whether schema has vocabulary for CQ relations |
| Avg KG concept recall | 0.754 | 0.754 | Whether KG text/instances represent required concepts |

## What Improved

- V2 adds first-class SourceEvidence, so provenance is no longer only repeated string fields.
- V2 adds Hazard, AircraftState, AircraftSystem, TriggerCondition, and FlightPhase, matching concepts surfaced by the paper-style CQ workflow.
- V2 preserves EmergencyProcedure, ProcedureStep, Warning, StepType, action, expected_result, and evidence, so it stays compatible with the current advisor shape.

## What Did Not Improve Enough

- The CQ answer recall proxy changes only modestly because V2 is migrated from the same extracted facts; it improves representation, not raw source coverage.
- Some hazard/system links are heuristic because the migration is deterministic and does not re-read the FAA text with an LLM.
- This is still a proxy evaluation. A full paper-style result would add SPARQL generation and an independent answer judge.

## Verdict

V2 is better as an ontology design target, but the current V1 remains better as the production demo schema until extraction prompts, SHACL, and Hybrid RAG are updated.

## Recommended Next Step

Use Controlled V2 as the next schema target, then update extraction and retrieval in small steps. The strongest next experiment is a real CQ benchmark: generate SPARQL or structured retrieval queries for the 35 CQs, run them on V1 and V2, and optionally use an independent LLM judge for answer equivalence.
