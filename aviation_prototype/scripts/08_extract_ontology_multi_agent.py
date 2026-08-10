"""
Multi-agent ontology extraction experiment.

This script follows the artifact-driven workflow described in the uploaded
ontology-generation paper:

1. Domain Expert: create competency questions and domain concepts.
2. Manager: create an ontology implementation plan.
3. Coder: generate a candidate ontology from the plan.
4. Quality Assurer: review the candidate ontology against the artifacts.

The experiment is intentionally isolated under output/ontology_experiment so it
does not overwrite the current production schema, SHACL shapes, KG, or UI demo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import OpenAI
from rdflib import Graph, Namespace
from rdflib.namespace import RDF


if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "cp936", "gb2312"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


AV = Namespace("https://example.org/aviation/")
DEFAULT_OUTPUT_DIR = "output/ontology_experiment"
DEFAULT_MODEL = "gpt-4o-mini"
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

JSON_OBJECT_HINT = {
    "type": "json_schema",
    "json_schema": {
        "name": "ontology_extraction_artifact",
        "schema": {
            "type": "object",
            "additionalProperties": True,
        },
    },
}


@dataclass
class LlmConfig:
    client: OpenAI
    provider: str
    model: str


def clean_space(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def safe_name(value: str) -> str:
    value = clean_space(value)
    if not value:
        return "unnamed"
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unnamed"


def snake_case(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", clean_space(value))
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return value or "unnamed"


def pascal_case(value: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", clean_space(value))
    return "".join(part[:1].upper() + part[1:] for part in parts if part) or "Unnamed"


def parse_json_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    return json.loads(cleaned)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def load_llm_config(model_override: str | None = None) -> LlmConfig:
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    configured_model = model_override or os.getenv("MODEL_NAME", "").strip()

    if provider and provider not in {"openai", "gemini"}:
        raise ValueError("LLM_PROVIDER must be 'openai' or 'gemini'.")

    if provider == "gemini" or (not provider and gemini_key and not openai_key):
        if not gemini_key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        return LlmConfig(
            client=OpenAI(api_key=gemini_key, base_url=GEMINI_OPENAI_BASE_URL),
            provider="gemini",
            model=configured_model or GEMINI_MODEL,
        )

    if provider == "openai" or openai_key:
        if not openai_key:
            raise ValueError("OPENAI_API_KEY is not configured.")
        client_kwargs: dict[str, Any] = {"api_key": openai_key}
        base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        if base_url:
            client_kwargs["base_url"] = base_url
        return LlmConfig(
            client=OpenAI(**client_kwargs),
            provider="openai",
            model=configured_model or DEFAULT_MODEL,
        )

    raise ValueError("No supported API key found. Configure OPENAI_API_KEY or GEMINI_API_KEY.")


def llm_json(config: LlmConfig, role: str, prompt: str, temperature: float = 0.1) -> dict[str, Any]:
    print(f"Calling {role} agent with {config.provider}:{config.model} ...")
    request: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are part of an auditable ontology engineering workflow. "
                    "Return strict JSON only. Do not wrap the response in markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    if config.provider == "openai":
        # Some OpenAI-compatible gateways support only json_object, so this is
        # deliberately simpler than a deeply nested response schema.
        request["response_format"] = {"type": "json_object"}

    response = config.client.chat.completions.create(**request)
    content = response.choices[0].message.content or "{}"
    return parse_json_response(content)


def load_input_documents(input_dir: Path, limit: int | None = None) -> list[tuple[str, str]]:
    index_path = input_dir / "index.txt"
    names: list[str] = []
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8", errors="replace")
        names = re.findall(r"\b\d{2}_[A-Za-z0-9_]+\.txt\b", index_text)

    if not names:
        names = sorted(
            path.name
            for path in input_dir.glob("*.txt")
            if path.name.lower() != "index.txt"
        )

    if limit is not None and limit > 0:
        names = names[:limit]

    documents: list[tuple[str, str]] = []
    for name in names:
        path = input_dir / name
        if path.exists():
            documents.append((name, path.read_text(encoding="utf-8", errors="replace")))
    return documents


def build_corpus(documents: list[tuple[str, str]], max_chars_per_file: int) -> str:
    parts: list[str] = []
    for name, text in documents:
        body = text.strip()
        if max_chars_per_file > 0 and len(body) > max_chars_per_file:
            body = body[:max_chars_per_file].rstrip() + "\n[TRUNCATED]"
        parts.append(f"[SOURCE_FILE: {name}]\n{body}")
    return "\n\n---\n\n".join(parts)


def build_corpus_digest(documents: list[tuple[str, str]]) -> list[dict[str, Any]]:
    digest = []
    for name, text in documents:
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        digest.append(
            {
                "source_file": name,
                "title_or_first_line": first_line,
                "characters": len(text),
            }
        )
    return digest


def build_domain_expert_prompt(corpus: str, max_cqs: int) -> str:
    return f"""
You are the Domain Expert agent in a multi-agent ontology generation workflow.

Task:
Read the FAA emergency procedure source text and derive ontology requirements.
Focus on what the ontology must be able to answer, not on implementing the ontology.

Return JSON with exactly these top-level keys:
- competency_questions: list of objects
- domain_concepts: list of objects
- scope_notes: list of strings

competency_questions objects must contain:
- id: CQ001 style identifier
- source_file: source filename
- question: precise competency question
- expected_answer: concise expected answer grounded in the text
- required_concepts: list of concept names
- required_relations: list of relation names
- odps: list of ontology design patterns such as Event Reification, Participation,
  Situation/State, Sequence, Quantity/Quality, Provenance, or Risk/Hazard.
- evidence_excerpt: short quote or close paraphrase from the source

domain_concepts objects must contain:
- name
- category: one of procedure, event, action, condition, aircraft_state, aircraft_system,
  flight_phase, hazard, warning, agent, resource, source_evidence, constraint
- definition
- source_files: list of source filenames

Rules:
- Produce at most {max_cqs} competency questions.
- Prefer questions that test executable queryability.
- Include coverage for fire, engine failure, landing/ditching, IMC, controls, systems,
  door opening, parachute/autoland, warnings, evidence, and training/caution separation.
- Do not invent aircraft-specific limits beyond source text.
- Return strict JSON only.

SOURCE TEXT:
{corpus}
"""


def compact_domain_artifact(
    domain_artifact: dict[str, Any],
    max_cqs: int,
    max_concepts: int = 45,
) -> dict[str, Any]:
    compact_cqs = []
    for cq in (domain_artifact.get("competency_questions") or [])[:max_cqs]:
        compact_cqs.append(
            {
                "id": cq.get("id"),
                "source_file": cq.get("source_file"),
                "question": cq.get("question"),
                "expected_answer": cq.get("expected_answer"),
                "required_concepts": cq.get("required_concepts", []),
                "required_relations": cq.get("required_relations", []),
                "odps": cq.get("odps", []),
            }
        )

    compact_concepts = []
    seen = set()
    for concept in domain_artifact.get("domain_concepts") or []:
        name = clean_space(concept.get("name"))
        key = snake_case(name)
        if not name or key in seen:
            continue
        seen.add(key)
        compact_concepts.append(
            {
                "name": name,
                "category": concept.get("category"),
                "definition": clean_space(concept.get("definition")),
            }
        )
        if len(compact_concepts) >= max_concepts:
            break

    return {
        "competency_questions": compact_cqs,
        "domain_concepts": compact_concepts,
        "scope_notes": (domain_artifact.get("scope_notes") or [])[:8],
    }


def compact_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "ontology_goal": plan.get("ontology_goal"),
        "modeling_principles": (plan.get("modeling_principles") or [])[:8],
        "classes": (plan.get("classes") or [])[:14],
        "object_properties": (plan.get("object_properties") or [])[:18],
        "data_properties": (plan.get("data_properties") or [])[:22],
        "enums": (plan.get("enums") or [])[:8],
        "validation_rules": (plan.get("validation_rules") or [])[:18],
        "cq_alignment": (plan.get("cq_alignment") or [])[:24],
        "implementation_notes": (plan.get("implementation_notes") or [])[:8],
    }


def candidate_summary_for_qa(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "metadata": candidate.get("metadata", {}),
        "classes": [
            {
                "name": cls.get("name"),
                "description": cls.get("description") or cls.get("definition"),
                "attributes": [
                    {
                        "name": attr.get("name"),
                        "range": attr.get("range"),
                        "required": attr.get("required"),
                        "multivalued": attr.get("multivalued"),
                        "description": attr.get("description") or attr.get("definition"),
                    }
                    for attr in (cls.get("attributes") or [])
                ],
            }
            for cls in candidate.get("classes", [])
        ],
        "object_properties": [
            {
                "name": prop.get("name"),
                "domain": prop.get("domain"),
                "range": prop.get("range"),
                "description": prop.get("description") or prop.get("definition"),
            }
            for prop in candidate.get("object_properties", [])
        ],
        "data_properties": [
            {
                "name": prop.get("name"),
                "domain": prop.get("domain"),
                "range": prop.get("range"),
                "description": prop.get("description") or prop.get("definition"),
            }
            for prop in candidate.get("data_properties", [])
        ],
        "enums": [
            {
                "name": enum.get("name"),
                "values": [value.get("value") for value in enum.get("values", [])],
            }
            for enum in candidate.get("enums", [])
        ],
        "validation_rules": candidate.get("validation_rules", [])[:18],
        "competency_question_coverage": candidate.get("competency_question_coverage", [])[:24],
    }


def merge_domain_artifacts(artifacts: list[dict[str, Any]], max_cqs: int) -> dict[str, Any]:
    merged_cqs = []
    merged_concepts = []
    scope_notes = []
    concept_seen = set()

    for artifact in artifacts:
        for cq in artifact.get("competency_questions") or []:
            if len(merged_cqs) >= max_cqs:
                break
            cq = dict(cq)
            cq["id"] = f"CQ{len(merged_cqs) + 1:03d}"
            merged_cqs.append(cq)

        for concept in artifact.get("domain_concepts") or []:
            name = clean_space(concept.get("name"))
            key = snake_case(name)
            if not name or key in concept_seen:
                continue
            concept_seen.add(key)
            merged_concepts.append(concept)

        scope_notes.extend(artifact.get("scope_notes") or [])

    return {
        "competency_questions": merged_cqs,
        "domain_concepts": merged_concepts,
        "scope_notes": scope_notes[:20],
    }


def run_domain_expert_by_document(
    config: LlmConfig,
    documents: list[tuple[str, str]],
    max_chars_per_file: int,
    max_cqs: int,
) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    cqs_per_doc = 1 if len(documents) >= max_cqs else max(1, min(3, max_cqs // max(1, len(documents))))

    for idx, (name, text) in enumerate(documents, start=1):
        print(f"Domain Expert chunk {idx}/{len(documents)}: {name}")
        doc_corpus = build_corpus([(name, text)], max_chars_per_file)
        prompt = build_domain_expert_prompt(doc_corpus, cqs_per_doc)
        artifacts.append(llm_json(config, f"Domain Expert ({name})", prompt, temperature=0.1))

    return merge_domain_artifacts(artifacts, max_cqs=max_cqs)


def build_manager_prompt(domain_artifact: dict[str, Any], corpus_digest: list[dict[str, Any]]) -> str:
    return f"""
You are the Manager agent in an artifact-driven ontology engineering workflow.

Task:
Create an ontology implementation plan for an aviation emergency advisor.
Use the Domain Expert artifact as the functional requirements. Do not copy an existing
schema; design the ontology needed to answer the competency questions.

Return JSON with exactly these top-level keys:
- ontology_goal
- modeling_principles
- classes
- object_properties
- data_properties
- enums
- validation_rules
- cq_alignment
- implementation_notes

Class objects must include:
- name: PascalCase
- definition
- responsibilities: list of strings
- design_pattern
- source_cqs: list of CQ ids

Property objects must include:
- name: snake_case
- domain
- range
- definition
- required: boolean
- multivalued: boolean
- source_cqs: list of CQ ids

Validation rule objects must include:
- id
- target_class
- rule
- severity: required, warning, or advisory

CQ alignment objects must include:
- cq_id
- required_classes
- required_properties
- query_strategy: SPARQL, graph traversal, hybrid retrieval, or synthesis

Design priorities:
- Make procedures, events, actions, warnings, hazards, aircraft state, source evidence,
  flight phase, and step type explicit.
- Preserve provenance.
- Separate immediate actions from training notes, cautions, and background.
- Keep the ontology implementable as LinkML/SHACL/RDF in this project.
- Keep the plan compact: target 8-12 core classes, 10-18 object properties,
  12-22 data properties, and only validation rules that matter for this prototype.
- Do not model only emergency landings. The FAA corpus includes fire, system failure,
  IMC, landing gear, door opening, parachute/autoland, flight control, and landing cases.
- The plan must include, at minimum, classes equivalent to EmergencyProcedure,
  ProcedureStep, Warning, SourceEvidence, TriggerCondition, FlightPhase, Hazard,
  AircraftState, and AircraftSystem. Add EmergencyEvent or PilotAction if useful.
- Do not collapse ordered procedure steps into plain strings. Ordered steps must be
  first-class queryable objects with order, action text, step type, and evidence.
- Do not omit source evidence; provenance is a core requirement, not an optional note.

CORPUS DIGEST:
{json.dumps(corpus_digest, ensure_ascii=False, indent=2)}

DOMAIN EXPERT ARTIFACT:
{json.dumps(compact_domain_artifact(domain_artifact, max_cqs=24), ensure_ascii=False, indent=2)}
"""


def build_coder_prompt(plan: dict[str, Any], domain_artifact: dict[str, Any]) -> str:
    return f"""
You are the Coder agent in an ontology generation workflow.

Task:
Convert the Manager's plan into a normalized candidate ontology JSON artifact.
The artifact must be easy to export to LinkML YAML, OWL/Turtle, and SHACL.

Return JSON with exactly these top-level keys:
- metadata
- classes
- object_properties
- data_properties
- enums
- validation_rules
- competency_question_coverage

metadata must include:
- name
- description
- namespace
- generated_from

classes objects must include:
- name
- description
- parent: string or null
- attributes: list of attribute objects

attribute objects must include:
- name
- range
- kind: data_property, object_property, enum, or literal
- required: boolean
- multivalued: boolean
- description

object_properties and data_properties objects must include:
- name
- domain
- range
- description
- required
- multivalued

enums objects must include:
- name
- description
- values: list of objects with value and description

validation_rules objects must include:
- id
- target_class
- property
- rule
- severity

competency_question_coverage objects must include:
- cq_id
- covered: boolean
- classes
- properties
- notes

Rules:
- Use stable PascalCase class names and snake_case property names.
- Do not generate individual FAA procedure instances.
- Do not include raw source text except short descriptions.
- Keep the ontology broad enough for the CQs but not so broad that it becomes unimplementable.
- Include non-empty descriptions for every class, property, enum, and attribute.
- Include classes for EmergencyProcedure, ProcedureStep, Warning, SourceEvidence,
  TriggerCondition, FlightPhase, Hazard, AircraftState, and AircraftSystem unless the
  Manager plan provides an exactly equivalent name.
- Include a StepType enum with immediate_action, caution, training_note, and background.
- ProcedureStep must be an object/class, not a string attribute.
- Source provenance must support source_file, source_section, source_excerpt, and
  evidence_for relationships.
- Return strict JSON only.

MANAGER PLAN:
{json.dumps(compact_plan(plan), ensure_ascii=False, indent=2)}

DOMAIN EXPERT ARTIFACT:
{json.dumps(compact_domain_artifact(domain_artifact, max_cqs=24), ensure_ascii=False, indent=2)}
"""


def build_qa_prompt(
    candidate: dict[str, Any],
    plan: dict[str, Any],
    domain_artifact: dict[str, Any],
) -> str:
    return f"""
You are the Quality Assurer agent in a multi-agent ontology generation workflow.

Task:
Review the candidate ontology against the competency questions and Manager plan.
Return a concise QA artifact and, if needed, a revised ontology.

Return JSON with exactly these top-level keys:
- qa_summary
- issues
- recommendations
- revised_ontology

issues objects must include:
- severity: blocker, major, minor, or note
- artifact_area
- description
- suggested_fix

revised_ontology:
- Return the full corrected ontology JSON using the same structure as candidate.
- If no correction is required, return the candidate unchanged.

Review criteria:
- Can the ontology answer the CQs?
- Are source evidence and provenance explicit?
- Are immediate actions separated from warnings, cautions, training notes, and background?
- Are Event Reification, Participation, Situation/State, Sequence, Risk/Hazard,
  and Provenance patterns represented where useful?
- Is the model implementable with LinkML, SHACL, and RDF?
- Is it too complex for the current aviation prototype?
- Keep revised_ontology null unless a small correction is essential. Prefer issues
  and recommendations over rewriting the whole ontology in this QA step.
- snake_case property names are preferred for this project. Do not flag snake_case as
  inconsistent merely because a planning artifact used camelCase.

CANDIDATE ONTOLOGY:
{json.dumps(candidate_summary_for_qa(candidate), ensure_ascii=False, indent=2)}

MANAGER PLAN:
{json.dumps(compact_plan(plan), ensure_ascii=False, indent=2)}

DOMAIN EXPERT ARTIFACT:
{json.dumps(compact_domain_artifact(domain_artifact, max_cqs=16), ensure_ascii=False, indent=2)}
"""


def class_lookup(ontology: dict[str, Any]) -> set[str]:
    return {clean_space(item.get("name")) for item in ontology.get("classes", []) if item.get("name")}


def normalize_ontology(ontology: dict[str, Any]) -> dict[str, Any]:
    class_names = class_lookup(ontology)
    normalized = dict(ontology)
    normalized.setdefault("metadata", {})
    normalized.setdefault("classes", [])
    normalized.setdefault("object_properties", [])
    normalized.setdefault("data_properties", [])
    normalized.setdefault("enums", [])
    normalized.setdefault("validation_rules", [])
    normalized.setdefault("competency_question_coverage", [])

    for cls in normalized["classes"]:
        cls["name"] = pascal_case(cls.get("name", ""))
        cls["description"] = clean_space(cls.get("description")) or clean_space(cls.get("definition"))
        cls["parent"] = pascal_case(cls["parent"]) if cls.get("parent") else None
        attrs = []
        for attr in cls.get("attributes", []) or []:
            name = snake_case(attr.get("name", ""))
            attr_range = clean_space(attr.get("range")) or "string"
            attrs.append(
                {
                    "name": name,
                    "range": attr_range,
                    "kind": attr.get("kind") or ("object_property" if attr_range in class_names else "literal"),
                    "required": bool(attr.get("required")),
                    "multivalued": bool(attr.get("multivalued")),
                    "description": clean_space(attr.get("description")) or clean_space(attr.get("definition")),
                }
            )
        cls["attributes"] = attrs

    for key in ("object_properties", "data_properties"):
        normalized_props = []
        for prop in normalized[key]:
            normalized_props.append(
                {
                    "name": snake_case(prop.get("name", "")),
                    "domain": pascal_case(prop.get("domain", "")),
                    "range": clean_space(prop.get("range")) or "string",
                    "description": clean_space(prop.get("description")) or clean_space(prop.get("definition")),
                    "required": bool(prop.get("required")),
                    "multivalued": bool(prop.get("multivalued")),
                }
            )
        normalized[key] = normalized_props

    return normalized


def ontology_to_linkml(ontology: dict[str, Any]) -> dict[str, Any]:
    enums: dict[str, Any] = {}
    for enum in ontology.get("enums", []):
        enum_name = pascal_case(enum.get("name", ""))
        permissible_values = {}
        for value in enum.get("values", []) or []:
            label = snake_case(value.get("value", ""))
            permissible_values[label] = {"description": clean_space(value.get("description"))}
        enums[enum_name] = {
            "description": clean_space(enum.get("description")),
            "permissible_values": permissible_values,
        }

    classes: dict[str, Any] = {}
    for cls in ontology.get("classes", []):
        attrs: dict[str, Any] = {}
        for attr in cls.get("attributes", []) or []:
            attr_def: dict[str, Any] = {
                "description": attr.get("description", ""),
                "range": attr.get("range", "string"),
            }
            if attr.get("required"):
                attr_def["required"] = True
            if attr.get("multivalued"):
                attr_def["multivalued"] = True
                attr_def["inlined"] = True
                attr_def["inlined_as_list"] = True
            attrs[attr["name"]] = attr_def

        cls_def: dict[str, Any] = {
            "description": cls.get("description", ""),
            "attributes": attrs,
        }
        if cls.get("parent"):
            cls_def["is_a"] = cls["parent"]
        classes[cls["name"]] = cls_def

    for prop in ontology.get("object_properties", []) + ontology.get("data_properties", []):
        domain = pascal_case(prop.get("domain", ""))
        if domain not in classes:
            continue
        prop_name = snake_case(prop.get("name", ""))
        if prop_name in classes[domain].setdefault("attributes", {}):
            continue
        prop_def: dict[str, Any] = {
            "description": prop.get("description", ""),
            "range": prop.get("range", "string"),
        }
        if prop.get("required"):
            prop_def["required"] = True
        if prop.get("multivalued"):
            prop_def["multivalued"] = True
            prop_def["inlined"] = True
            prop_def["inlined_as_list"] = True
        classes[domain]["attributes"][prop_name] = prop_def

    return {
        "id": ontology.get("metadata", {}).get("namespace", "https://example.org/aviation/candidate"),
        "name": ontology.get("metadata", {}).get("name", "CandidateAviationOntology"),
        "description": ontology.get("metadata", {}).get("description", ""),
        "prefixes": {
            "linkml": "https://w3id.org/linkml/",
            "av": "https://example.org/aviation/",
        },
        "default_range": "string",
        "default_prefix": "av",
        "imports": ["linkml:types"],
        "classes": classes,
        "enums": enums,
    }


def turtle_escape(value: str) -> str:
    return clean_space(value).replace("\\", "\\\\").replace('"', '\\"')


def ontology_to_turtle(ontology: dict[str, Any]) -> str:
    lines = [
        "@prefix av: <https://example.org/aviation/> .",
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
        "av:CandidateAviationOntology a owl:Ontology .",
        "",
    ]

    class_names = {cls["name"] for cls in ontology.get("classes", [])}
    for cls in ontology.get("classes", []):
        name = safe_name(cls["name"])
        lines.append(f"av:{name} a owl:Class ;")
        if cls.get("parent"):
            lines.append(f"    rdfs:subClassOf av:{safe_name(cls['parent'])} ;")
        lines.append(f'    rdfs:comment "{turtle_escape(cls.get("description", ""))}" .')
        lines.append("")

    properties = list(ontology.get("object_properties", [])) + list(ontology.get("data_properties", []))
    seen_props: set[str] = set()
    for cls in ontology.get("classes", []):
        for attr in cls.get("attributes", []) or []:
            prop_name = attr["name"]
            if prop_name in seen_props:
                continue
            seen_props.add(prop_name)
            prop_type = "owl:ObjectProperty" if attr.get("range") in class_names else "owl:DatatypeProperty"
            properties.append(
                {
                    "name": prop_name,
                    "domain": cls["name"],
                    "range": attr.get("range", "string"),
                    "description": attr.get("description", ""),
                    "kind": prop_type,
                }
            )

    range_map = {
        "string": "xsd:string",
        "integer": "xsd:integer",
        "int": "xsd:integer",
        "float": "xsd:decimal",
        "decimal": "xsd:decimal",
        "boolean": "xsd:boolean",
        "date": "xsd:date",
        "datetime": "xsd:dateTime",
    }
    emitted: set[str] = set()
    for prop in properties:
        name = snake_case(prop.get("name", ""))
        if name in emitted:
            continue
        emitted.add(name)
        prop_range = clean_space(prop.get("range")) or "string"
        is_object = prop_range in class_names or prop.get("kind") == "owl:ObjectProperty"
        prop_type = "owl:ObjectProperty" if is_object else "owl:DatatypeProperty"
        range_ref = f"av:{safe_name(prop_range)}" if is_object else range_map.get(prop_range.lower(), "xsd:string")
        lines.append(f"av:{name} a {prop_type} ;")
        if prop.get("domain"):
            lines.append(f"    rdfs:domain av:{safe_name(prop['domain'])} ;")
        lines.append(f"    rdfs:range {range_ref} ;")
        lines.append(f'    rdfs:comment "{turtle_escape(prop.get("description", ""))}" .')
        lines.append("")

    return "\n".join(lines)


def load_current_schema(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def schema_class_attribute_sets(schema: dict[str, Any]) -> tuple[set[str], set[str]]:
    classes = set()
    attributes = set()
    for class_name, class_def in (schema.get("classes") or {}).items():
        classes.add(snake_case(class_name))
        for attr_name in ((class_def or {}).get("attributes") or {}):
            attributes.add(snake_case(attr_name))
    return classes, attributes


def ontology_class_attribute_sets(ontology: dict[str, Any]) -> tuple[set[str], set[str]]:
    classes = set()
    attributes = set()
    for cls in ontology.get("classes", []):
        classes.add(snake_case(cls.get("name", "")))
        for attr in cls.get("attributes", []) or []:
            attributes.add(snake_case(attr.get("name", "")))
    for prop in ontology.get("object_properties", []) + ontology.get("data_properties", []):
        attributes.add(snake_case(prop.get("name", "")))
    return classes, attributes


def summarize_current_kg(path: Path) -> dict[str, Any]:
    summary = {
        "exists": path.exists(),
        "triples": 0,
        "classes": {},
        "predicates": {},
    }
    if not path.exists():
        return summary

    graph = Graph()
    graph.parse(path, format="turtle")
    summary["triples"] = len(graph)

    for obj in graph.objects(None, RDF.type):
        if str(obj).startswith(str(AV)):
            label = str(obj).split("/")[-1]
            summary["classes"][label] = summary["classes"].get(label, 0) + 1

    for pred in graph.predicates():
        if str(pred).startswith(str(AV)):
            label = str(pred).split("/")[-1]
            summary["predicates"][label] = summary["predicates"].get(label, 0) + 1

    return summary


def summarize_candidate(ontology: dict[str, Any]) -> dict[str, Any]:
    classes = ontology.get("classes", [])
    attrs = [attr for cls in classes for attr in cls.get("attributes", []) or []]
    required_attrs = [attr for attr in attrs if attr.get("required")]
    coverage = ontology.get("competency_question_coverage", [])
    covered = [item for item in coverage if item.get("covered")]
    return {
        "classes": len(classes),
        "attributes": len(attrs),
        "required_attributes": len(required_attrs),
        "object_properties": len(ontology.get("object_properties", [])),
        "data_properties": len(ontology.get("data_properties", [])),
        "enums": len(ontology.get("enums", [])),
        "validation_rules": len(ontology.get("validation_rules", [])),
        "cq_coverage": f"{len(covered)}/{len(coverage)}" if coverage else "0/0",
    }


def bullet_lines(items: list[str], max_items: int = 12) -> list[str]:
    if not items:
        return ["- None"]
    shown = items[:max_items]
    lines = [f"- `{item}`" for item in shown]
    if len(items) > max_items:
        lines.append(f"- ... and {len(items) - max_items} more")
    return lines


def generate_comparison_report(
    domain_artifact: dict[str, Any],
    plan: dict[str, Any],
    candidate: dict[str, Any],
    qa_artifact: dict[str, Any],
    current_schema: dict[str, Any],
    current_kg_summary: dict[str, Any],
) -> str:
    current_classes, current_attrs = schema_class_attribute_sets(current_schema)
    candidate_classes, candidate_attrs = ontology_class_attribute_sets(candidate)
    candidate_summary = summarize_candidate(candidate)
    current_required = 0
    for class_def in (current_schema.get("classes") or {}).values():
        for attr_def in ((class_def or {}).get("attributes") or {}).values():
            if (attr_def or {}).get("required"):
                current_required += 1

    cqs = domain_artifact.get("competency_questions", []) or []
    qa_issues = qa_artifact.get("issues", []) or []
    major_issues = [issue for issue in qa_issues if issue.get("severity") in {"blocker", "major"}]

    candidate_only_classes = sorted(candidate_classes - current_classes)
    current_only_classes = sorted(current_classes - candidate_classes)
    candidate_only_attrs = sorted(candidate_attrs - current_attrs)
    current_only_attrs = sorted(current_attrs - candidate_attrs)

    lines = [
        "# Ontology Extraction Comparison Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Method",
        "",
        "This experiment follows the paper's artifact-driven multi-agent workflow:",
        "",
        "1. Domain Expert generated competency questions and domain concepts.",
        "2. Manager generated an ontology implementation plan.",
        "3. Coder generated a candidate ontology artifact.",
        "4. Quality Assurer reviewed and revised the candidate.",
        "",
        "## Current Project Ontology",
        "",
        f"- LinkML classes: `{len(current_classes)}`",
        f"- LinkML attributes: `{len(current_attrs)}`",
        f"- Required attributes: `{current_required}`",
        f"- Current KG triples: `{current_kg_summary.get('triples', 0)}`",
        f"- Current KG class instances: `{current_kg_summary.get('classes', {})}`",
        "",
        "## Candidate Ontology",
        "",
        f"- Classes: `{candidate_summary['classes']}`",
        f"- Class attributes: `{candidate_summary['attributes']}`",
        f"- Required attributes: `{candidate_summary['required_attributes']}`",
        f"- Object properties: `{candidate_summary['object_properties']}`",
        f"- Data properties: `{candidate_summary['data_properties']}`",
        f"- Enums: `{candidate_summary['enums']}`",
        f"- Validation rules: `{candidate_summary['validation_rules']}`",
        f"- CQ coverage declared by candidate: `{candidate_summary['cq_coverage']}`",
        f"- Domain Expert CQs generated: `{len(cqs)}`",
        f"- QA major/blocker issues: `{len(major_issues)}`",
        "",
        "## Structural Differences",
        "",
        "### Classes Added By Candidate",
        "",
        *bullet_lines(candidate_only_classes),
        "",
        "### Classes Only In Current Schema",
        "",
        *bullet_lines(current_only_classes),
        "",
        "### Properties Added By Candidate",
        "",
        *bullet_lines(candidate_only_attrs),
        "",
        "### Properties Only In Current Schema",
        "",
        *bullet_lines(current_only_attrs),
        "",
        "## QA Findings",
        "",
    ]

    if qa_issues:
        for issue in qa_issues:
            lines.append(
                f"- `{issue.get('severity', 'note')}` {issue.get('artifact_area', '')}: "
                f"{issue.get('description', '')} Fix: {issue.get('suggested_fix', '')}"
            )
    else:
        lines.append("- No QA issues returned.")

    lines.extend(
        [
            "",
            "## Practical Judgment",
            "",
            "The current ontology is better for the running demo because it is compact, already SHACL-validated, "
            "and already connected to extraction, KG retrieval, Hybrid RAG, synthesis, and the UI.",
            "",
            "The candidate ontology is better as a next design target if its additional classes and properties "
            "improve CQ answerability without making extraction unstable. In particular, it should be considered "
            "useful if it makes events, hazards, source evidence, aircraft states, and step/note/warning separation "
            "more explicit than the current schema.",
            "",
            "Recommended next step: manually review the candidate-only classes/properties, then promote only the "
            "smallest useful subset into the production LinkML schema and SHACL shapes. Do not replace the current "
            "schema wholesale until extraction and Hybrid RAG regression tests pass.",
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    input_dir = Path(args.input_dir)
    documents = load_input_documents(input_dir, args.limit)
    if not documents:
        raise FileNotFoundError(f"No input .txt files found in {input_dir}")

    print(f"Loaded {len(documents)} source documents from {input_dir}")
    corpus = build_corpus(documents, args.max_chars_per_file)
    corpus_digest = build_corpus_digest(documents)
    write_json(output_dir / "source_corpus_digest.json", corpus_digest)

    config = load_llm_config(args.model)
    metadata = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_dir": str(input_dir),
        "documents": [name for name, _ in documents],
        "provider": config.provider,
        "model": config.model,
        "max_chars_per_file": args.max_chars_per_file,
        "max_cqs": args.max_cqs,
    }
    write_json(output_dir / "run_metadata.json", metadata)

    domain_path = output_dir / "domain_cqs.json"
    if args.reuse_existing and domain_path.exists():
        print(f"Reusing existing Domain Expert artifact: {domain_path}")
        domain_artifact = json.loads(domain_path.read_text(encoding="utf-8"))
    else:
        domain_artifact = run_domain_expert_by_document(
            config=config,
            documents=documents,
            max_chars_per_file=args.max_chars_per_file,
            max_cqs=args.max_cqs,
        )
    write_json(output_dir / "domain_cqs.json", domain_artifact)

    plan = llm_json(
        config,
        "Manager",
        build_manager_prompt(domain_artifact, corpus_digest),
        temperature=0.1,
    )
    write_json(output_dir / "ontology_plan.json", plan)

    candidate = llm_json(
        config,
        "Coder",
        build_coder_prompt(plan, domain_artifact),
        temperature=0.05,
    )
    candidate = normalize_ontology(candidate)
    write_json(output_dir / "candidate_ontology.raw.json", candidate)

    qa_artifact = llm_json(
        config,
        "Quality Assurer",
        build_qa_prompt(candidate, plan, domain_artifact),
        temperature=0.05,
    )
    write_json(output_dir / "qa_review.json", qa_artifact)

    revised = qa_artifact.get("revised_ontology") or candidate
    revised = normalize_ontology(revised)
    write_json(output_dir / "candidate_ontology.json", revised)

    linkml_schema = ontology_to_linkml(revised)
    write_yaml(output_dir / "candidate_schema.yaml", linkml_schema)

    turtle = ontology_to_turtle(revised)
    ttl_path = output_dir / "candidate_ontology.ttl"
    ttl_path.write_text(turtle, encoding="utf-8")

    # Parse the generated TTL as a local syntax check.
    Graph().parse(ttl_path, format="turtle")

    current_schema = load_current_schema(Path(args.current_schema))
    current_kg_summary = summarize_current_kg(Path(args.current_kg))
    report = generate_comparison_report(
        domain_artifact=domain_artifact,
        plan=plan,
        candidate=revised,
        qa_artifact=qa_artifact,
        current_schema=current_schema,
        current_kg_summary=current_kg_summary,
    )
    report_path = output_dir / "comparison_report.md"
    report_path.write_text(report, encoding="utf-8")

    print("\nOntology experiment complete.")
    print(f"Artifacts written to: {output_dir}")
    print(f"Comparison report: {report_path}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract a candidate aviation ontology with a paper-inspired multi-agent workflow."
    )
    parser.add_argument("--input-dir", default="data/procedures")
    parser.add_argument("--current-schema", default="schema/emergency_schema.yaml")
    parser.add_argument("--current-kg", default="output/kg.ttl")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model", default=None, help="Override MODEL_NAME for this experiment.")
    parser.add_argument("--limit", type=int, default=None, help="Only process first N source files.")
    parser.add_argument("--max-chars-per-file", type=int, default=2600)
    parser.add_argument("--max-cqs", type=int, default=40)
    parser.add_argument(
        "--no-reuse-existing",
        dest="reuse_existing",
        action="store_false",
        help="Regenerate artifacts even if files already exist in the output directory.",
    )
    parser.set_defaults(reuse_existing=True)
    return parser


if __name__ == "__main__":
    run(build_arg_parser().parse_args())
