# Ontology Extraction Comparison Report

Generated: 2026-05-12T14:00:21

## Method

This experiment follows the paper's artifact-driven multi-agent workflow:

1. Domain Expert generated competency questions and domain concepts.
2. Manager generated an ontology implementation plan.
3. Coder generated a candidate ontology artifact.
4. Quality Assurer reviewed and revised the candidate.

## Current Project Ontology

- LinkML classes: `4`
- LinkML attributes: `14`
- Required attributes: `7`
- Current KG triples: `818`
- Current KG class instances: `{'EmergencyProcedure': 18, 'ProcedureStep': 89, 'Warning': 23}`

## Candidate Ontology

- Classes: `11`
- Class attributes: `11`
- Required attributes: `11`
- Object properties: `9`
- Data properties: `0`
- Enums: `1`
- Validation rules: `3`
- CQ coverage declared by candidate: `8/8`
- Domain Expert CQs generated: `35`
- QA major/blocker issues: `1`

## Structural Differences

### Classes Added By Candidate

- `aircraft_state`
- `aircraft_system`
- `emergency_event`
- `flight_phase`
- `hazard`
- `pilot_action`
- `source_evidence`
- `trigger_condition`

### Classes Only In Current Schema

- `extraction_result`

### Properties Added By Candidate

- `action_text`
- `affects`
- `aircraft_condition`
- `associated_with`
- `describes`
- `event_description`
- `evidence_source`
- `evidenced_by`
- `flight_phase_name`
- `has_step`
- `hazard_description`
- `occurs_during`
- ... and 7 more

### Properties Only In Current Schema

- `action`
- `aircraft_phase`
- `description`
- `expected_result`
- `name`
- `procedures`
- `source_excerpt`
- `source_file`
- `source_section`
- `step_number`
- `steps`
- `trigger_condition`
- ... and 1 more

## QA Findings

- `major` classes: The ontology does not clearly separate immediate actions from warnings, cautions, training notes, and background information. Fix: Introduce a clear distinction in the class structure or documentation to separate immediate actions from other types of information.
- `minor` object_properties: The 'associated_with' property is not marked as required, which may lead to incomplete links between hazards and emergency procedures. Fix: Consider making the 'associated_with' property required to ensure that every hazard is linked to at least one emergency procedure.
- `note` enums: The StepType enum includes values that may not be fully aligned with the Manager Plan's emphasis on clear categorization of actions. Fix: Review the StepType enum values to ensure they align with the intended design patterns and responsibilities outlined in the Manager Plan.

## Practical Judgment

The current ontology is better for the running demo because it is compact, already SHACL-validated, and already connected to extraction, KG retrieval, Hybrid RAG, synthesis, and the UI.

The candidate ontology is better as a next design target if its additional classes and properties improve CQ answerability without making extraction unstable. In particular, it should be considered useful if it makes events, hazards, source evidence, aircraft states, and step/note/warning separation more explicit than the current schema.

Recommended next step: manually review the candidate-only classes/properties, then promote only the smallest useful subset into the production LinkML schema and SHACL shapes. Do not replace the current schema wholesale until extraction and Hybrid RAG regression tests pass.
