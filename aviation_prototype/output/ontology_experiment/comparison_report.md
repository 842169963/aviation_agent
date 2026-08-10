# Ontology Extraction Comparison Report

Generated: 2026-05-12T13:55:38

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

- Classes: `8`
- Class attributes: `8`
- Required attributes: `8`
- Object properties: `8`
- Data properties: `8`
- Enums: `0`
- Validation rules: `3`
- CQ coverage declared by candidate: `7/7`
- Domain Expert CQs generated: `35`
- QA major/blocker issues: `9`

## Structural Differences

### Classes Added By Candidate

- `aircraft_state`
- `emergency_landing`
- `emergency_landing_site`
- `hazard`
- `pilot_action`
- `procedure`
- `psychological_hazard`
- `terrain`

### Classes Only In Current Schema

- `emergency_procedure`
- `extraction_result`
- `procedure_step`
- `warning`

### Properties Added By Candidate

- `affects`
- `aircraft_condition`
- `governed_by`
- `has_procedure`
- `impairs`
- `indicates`
- `is_suitable_for`
- `landing_outcome`
- `pilot_experience`
- `procedure_steps`
- `psychological_impact`
- `requires`
- ... and 3 more

### Properties Only In Current Schema

- `action`
- `aircraft_phase`
- `expected_result`
- `name`
- `procedures`
- `source_excerpt`
- `source_file`
- `source_section`
- `step_number`
- `step_type`
- `steps`
- `trigger_condition`
- ... and 1 more

## QA Findings

- `major` classes: The class 'EmergencyLanding' lacks a definition, which is essential for clarity. Fix: Add a definition for the 'EmergencyLanding' class.
- `major` object_properties: The property 'governed_by' does not have a definition, which is necessary for understanding its role. Fix: Include a definition for the 'governed_by' property.
- `major` data_properties: The data property 'risk_level' is incorrectly named as 'riskLevel' in the manager plan, leading to inconsistency. Fix: Rename 'risk_level' to 'riskLevel' to maintain consistency with the manager plan.
- `major` data_properties: The data property 'terrain_type' is incorrectly named as 'terrainType' in the manager plan, leading to inconsistency. Fix: Rename 'terrain_type' to 'terrainType' to maintain consistency with the manager plan.
- `major` data_properties: The data property 'psychological_impact' is incorrectly named as 'psychologicalImpact' in the manager plan, leading to inconsistency. Fix: Rename 'psychological_impact' to 'psychologicalImpact' to maintain consistency with the manager plan.
- `major` data_properties: The data property 'procedure_steps' is incorrectly named as 'procedureSteps' in the manager plan, leading to inconsistency. Fix: Rename 'procedure_steps' to 'procedureSteps' to maintain consistency with the manager plan.
- `major` data_properties: The data property 'aircraft_condition' is incorrectly named as 'aircraftCondition' in the manager plan, leading to inconsistency. Fix: Rename 'aircraft_condition' to 'aircraftCondition' to maintain consistency with the manager plan.
- `major` data_properties: The data property 'pilot_experience' is incorrectly named as 'pilotExperience' in the manager plan, leading to inconsistency. Fix: Rename 'pilot_experience' to 'pilotExperience' to maintain consistency with the manager plan.
- `major` data_properties: The data property 'landing_outcome' is incorrectly named as 'landingOutcome' in the manager plan, leading to inconsistency. Fix: Rename 'landing_outcome' to 'landingOutcome' to maintain consistency with the manager plan.

## Practical Judgment

The current ontology is better for the running demo because it is compact, already SHACL-validated, and already connected to extraction, KG retrieval, Hybrid RAG, synthesis, and the UI.

The candidate ontology is better as a next design target if its additional classes and properties improve CQ answerability without making extraction unstable. In particular, it should be considered useful if it makes events, hazards, source evidence, aircraft states, and step/note/warning separation more explicit than the current schema.

Recommended next step: manually review the candidate-only classes/properties, then promote only the smallest useful subset into the production LinkML schema and SHACL shapes. Do not replace the current schema wholesale until extraction and Hybrid RAG regression tests pass.
