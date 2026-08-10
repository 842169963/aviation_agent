"""
Migrate the current extracted.json into the controlled v2 ontology shape.

This is intentionally deterministic: it does not call an LLM. The goal is to
compare ontology design, not introduce a new extraction variable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from pyshacl import validate
from rdflib import BNode, Graph, Literal, Namespace
from rdflib.namespace import RDF, XSD


if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "cp936", "gb2312"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


AV = Namespace("https://example.org/aviation/")
VALID_STEP_TYPES = {"immediate_action", "training_note", "caution", "background"}

SYSTEM_KEYWORDS = {
    "engine": ("Engine", "Powerplant and related engine controls or instruments"),
    "fuel": ("Fuel System", "Fuel supply, selector, mixture, and related components"),
    "electrical": ("Electrical System", "Battery, alternator, generator, wiring, and electrical loads"),
    "battery": ("Electrical System", "Battery, alternator, generator, wiring, and electrical loads"),
    "alternator": ("Electrical System", "Battery, alternator, generator, wiring, and electrical loads"),
    "generator": ("Electrical System", "Battery, alternator, generator, wiring, and electrical loads"),
    "landing gear": ("Landing Gear", "Retractable or fixed landing gear system"),
    "gear": ("Landing Gear", "Retractable or fixed landing gear system"),
    "flap": ("Flap System", "Wing flap system and related controls"),
    "elevator": ("Elevator Control", "Elevator and pitch-control system"),
    "pitch control": ("Elevator Control", "Elevator and pitch-control system"),
    "pitot": ("Pitot-Static System", "Pitot-static instruments and pressure lines"),
    "static": ("Pitot-Static System", "Pitot-static instruments and pressure lines"),
    "airspeed indicator": ("Pitot-Static System", "Pitot-static instruments and pressure lines"),
    "altimeter": ("Pitot-Static System", "Pitot-static instruments and pressure lines"),
    "door": ("Cabin Door", "Cabin door and latching system"),
    "cabin": ("Cabin", "Cabin environment and ventilation"),
    "parachute": ("Ballistic Parachute System", "Airframe parachute emergency response system"),
    "autoland": ("Emergency Autoland System", "Automated emergency landing system"),
    "instrument": ("Flight Instruments", "Flight instruments used for attitude and navigation"),
}

HAZARD_KEYWORDS = {
    "fire": "Fire",
    "smoke": "Smoke or fumes",
    "stall": "Stall risk",
    "spatial disorientation": "Spatial disorientation",
    "loss of control": "Loss of control",
    "control loss": "Loss of control",
    "collision": "Collision risk",
    "obstacle": "Obstacle hazard",
    "tree": "Terrain or obstacle impact",
    "water": "Ditching hazard",
    "snow": "Whiteout or snow landing hazard",
    "gear": "Landing gear malfunction",
    "electrical": "Electrical failure",
    "engine": "Engine failure or fire",
    "fuel": "Fuel-related hazard",
    "imc": "Inadvertent IMC",
    "cloud": "Inadvertent IMC",
    "distraction": "Pilot distraction",
    "parachute": "Parachute deployment hazard",
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def normalize_step_type(value: str | None) -> str:
    normalized = clean_text(value).lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in VALID_STEP_TYPES else "immediate_action"


def slug(value: str) -> str:
    cleaned = clean_text(value).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")
    return cleaned or "unnamed"


def source_evidence(
    source_file: str,
    source_section: str,
    source_excerpt: str,
) -> dict[str, str]:
    return {
        "source_file": clean_text(source_file) or "unknown_source",
        "source_section": clean_text(source_section),
        "source_excerpt": clean_text(source_excerpt) or "No source excerpt was available in the migrated v1 data.",
    }


def combined_text(proc: dict[str, Any]) -> str:
    parts = [
        proc.get("name"),
        proc.get("trigger_condition"),
        proc.get("aircraft_phase"),
        proc.get("source_excerpt"),
    ]
    for step in proc.get("steps", []) or []:
        parts.extend([step.get("action"), step.get("expected_result"), step.get("source_excerpt")])
    for warning in proc.get("warnings", []) or []:
        parts.append(warning.get("description"))
    return clean_text(" ".join(clean_text(part) for part in parts)).lower()


def infer_systems(proc: dict[str, Any]) -> list[dict[str, str]]:
    text = combined_text(proc)
    systems: dict[str, dict[str, str]] = {}
    for keyword, (name, description) in SYSTEM_KEYWORDS.items():
        if keyword in text:
            systems[name] = {"name": name, "description": description}
    return list(systems.values())


def infer_aircraft_state(proc: dict[str, Any]) -> dict[str, str]:
    trigger = clean_text(proc.get("trigger_condition"))
    if trigger:
        return {"description": trigger}
    return {"description": f"Aircraft is in the condition requiring {clean_text(proc.get('name'))}"}


def infer_hazards(proc: dict[str, Any], systems: list[dict[str, str]]) -> list[dict[str, Any]]:
    text = combined_text(proc)
    hazards: dict[str, dict[str, Any]] = {}
    default_system = systems[0] if systems else None
    evidence = source_evidence(
        proc.get("source_file", ""),
        proc.get("source_section", ""),
        proc.get("source_excerpt", ""),
    )

    for keyword, name in HAZARD_KEYWORDS.items():
        if keyword in text:
            hazards[name] = {
                "name": name,
                "description": f"{name} associated with {clean_text(proc.get('name'))}.",
                "affected_system": default_system,
                "evidence": evidence,
            }

    for warning in proc.get("warnings", []) or []:
        warning_text = clean_text(warning.get("description"))
        if not warning_text:
            continue
        name = "Procedure-specific warning"
        for keyword, hazard_name in HAZARD_KEYWORDS.items():
            if keyword in warning_text.lower():
                name = hazard_name
                break
        hazards.setdefault(
            name,
            {
                "name": name,
                "description": warning_text,
                "affected_system": default_system,
                "evidence": evidence,
            },
        )

    return list(hazards.values())


def migrate_procedure(proc: dict[str, Any]) -> dict[str, Any]:
    source_file = proc.get("source_file", "")
    source_section = proc.get("source_section", "") or proc.get("name", "")
    proc_evidence = source_evidence(source_file, source_section, proc.get("source_excerpt", ""))
    systems = infer_systems(proc)
    hazards = infer_hazards(proc, systems)

    trigger_description = clean_text(proc.get("trigger_condition")) or f"Condition requiring {clean_text(proc.get('name'))}"
    trigger = {
        "description": trigger_description,
        "aircraft_state": infer_aircraft_state(proc),
        "evidence": proc_evidence,
    }

    flight_phase_name = clean_text(proc.get("aircraft_phase")) or "unspecified"

    migrated_steps = []
    for step in proc.get("steps", []) or []:
        step_evidence = source_evidence(
            source_file,
            source_section,
            step.get("source_excerpt") or proc.get("source_excerpt", ""),
        )
        migrated_steps.append(
            {
                "step_number": int(step.get("step_number") or len(migrated_steps) + 1),
                "step_type": normalize_step_type(step.get("step_type")),
                "action": clean_text(step.get("action")),
                "expected_result": clean_text(step.get("expected_result")),
                "evidence": step_evidence,
            }
        )

    migrated_warnings = []
    for warning in proc.get("warnings", []) or []:
        description = clean_text(warning.get("description"))
        if not description:
            continue
        warning_hazard = infer_hazards(
            {
                **proc,
                "warnings": [warning],
                "steps": [],
                "source_excerpt": description,
            },
            systems,
        )
        migrated_warnings.append(
            {
                "description": description,
                "hazard": warning_hazard[0] if warning_hazard else None,
                "evidence": proc_evidence,
            }
        )

    return {
        "name": clean_text(proc.get("name")),
        "trigger_condition_text": trigger_description,
        "trigger_condition": trigger,
        "aircraft_phase": flight_phase_name,
        "flight_phase": {"name": flight_phase_name},
        "source_evidence": [proc_evidence],
        "steps": migrated_steps,
        "warnings": migrated_warnings,
        "hazards": hazards,
        "aircraft_systems": systems,
    }


def migrate_extracted(extracted: dict[str, Any]) -> dict[str, Any]:
    return {
        "procedures": [
            migrate_procedure(proc)
            for proc in extracted.get("procedures", [])
            if clean_text(proc.get("name"))
        ]
    }


def add_evidence(graph: Graph, parent: Any, evidence: dict[str, Any]) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, AV.SourceEvidence))
    graph.add((parent, AV.hasEvidence, node))
    graph.add((node, AV.source_file, Literal(evidence.get("source_file", ""), datatype=XSD.string)))
    if evidence.get("source_section"):
        graph.add((node, AV.source_section, Literal(evidence["source_section"], datatype=XSD.string)))
    graph.add((node, AV.source_excerpt, Literal(evidence.get("source_excerpt", ""), datatype=XSD.string)))
    return node


def add_system(graph: Graph, system: dict[str, Any]) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, AV.AircraftSystem))
    graph.add((node, AV.name, Literal(system.get("name", ""), datatype=XSD.string)))
    if system.get("description"):
        graph.add((node, AV.description, Literal(system["description"], datatype=XSD.string)))
    return node


def add_hazard(graph: Graph, hazard: dict[str, Any]) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, AV.Hazard))
    graph.add((node, AV.name, Literal(hazard.get("name", ""), datatype=XSD.string)))
    graph.add((node, AV.description, Literal(hazard.get("description", ""), datatype=XSD.string)))
    if hazard.get("affected_system"):
        system_node = add_system(graph, hazard["affected_system"])
        graph.add((node, AV.affectedSystem, system_node))
    if hazard.get("evidence"):
        add_evidence(graph, node, hazard["evidence"])
    return node


def json_to_rdf_v2(extracted_v2: dict[str, Any]) -> Graph:
    graph = Graph()
    graph.bind("av", AV)
    graph.bind("xsd", XSD)

    for idx, proc in enumerate(extracted_v2.get("procedures", [])):
        proc_uri = AV[f"v2_proc_{idx}_{slug(proc.get('name', ''))[:36]}"]
        graph.add((proc_uri, RDF.type, AV.EmergencyProcedure))
        graph.add((proc_uri, AV.name, Literal(proc["name"], datatype=XSD.string)))
        graph.add((proc_uri, AV.trigger_condition_text, Literal(proc["trigger_condition_text"], datatype=XSD.string)))
        graph.add((proc_uri, AV.aircraft_phase, Literal(proc["aircraft_phase"], datatype=XSD.string)))

        for evidence in proc.get("source_evidence", []) or []:
            add_evidence(graph, proc_uri, evidence)

        if proc.get("flight_phase"):
            phase = BNode()
            graph.add((phase, RDF.type, AV.FlightPhase))
            graph.add((phase, AV.name, Literal(proc["flight_phase"].get("name", ""), datatype=XSD.string)))
            graph.add((proc_uri, AV.hasFlightPhase, phase))

        trigger = proc.get("trigger_condition") or {}
        trigger_node = BNode()
        graph.add((trigger_node, RDF.type, AV.TriggerCondition))
        graph.add((trigger_node, AV.description, Literal(trigger.get("description", ""), datatype=XSD.string)))
        graph.add((proc_uri, AV.hasTriggerCondition, trigger_node))
        if trigger.get("aircraft_state"):
            state = BNode()
            graph.add((state, RDF.type, AV.AircraftState))
            graph.add((state, AV.description, Literal(trigger["aircraft_state"].get("description", ""), datatype=XSD.string)))
            graph.add((trigger_node, AV.hasAircraftState, state))
        if trigger.get("evidence"):
            add_evidence(graph, trigger_node, trigger["evidence"])

        for system in proc.get("aircraft_systems", []) or []:
            graph.add((proc_uri, AV.relatesToSystem, add_system(graph, system)))

        for hazard in proc.get("hazards", []) or []:
            graph.add((proc_uri, AV.hasHazard, add_hazard(graph, hazard)))

        for step in proc.get("steps", []) or []:
            step_node = BNode()
            graph.add((step_node, RDF.type, AV.ProcedureStep))
            graph.add((proc_uri, AV.hasStep, step_node))
            graph.add((step_node, AV.step_number, Literal(int(step["step_number"]), datatype=XSD.integer)))
            graph.add((step_node, AV.step_type, Literal(step["step_type"], datatype=XSD.string)))
            graph.add((step_node, AV.action, Literal(step["action"], datatype=XSD.string)))
            if step.get("expected_result"):
                graph.add((step_node, AV.expected_result, Literal(step["expected_result"], datatype=XSD.string)))
            add_evidence(graph, step_node, step["evidence"])

        for warning in proc.get("warnings", []) or []:
            warning_node = BNode()
            graph.add((warning_node, RDF.type, AV.Warning))
            graph.add((proc_uri, AV.hasWarning, warning_node))
            graph.add((warning_node, AV.description, Literal(warning["description"], datatype=XSD.string)))
            if warning.get("hazard"):
                graph.add((warning_node, AV.hasHazard, add_hazard(graph, warning["hazard"])))
            if warning.get("evidence"):
                add_evidence(graph, warning_node, warning["evidence"])

    return graph


def run_shacl(graph: Graph, shacl_path: Path) -> tuple[bool, str]:
    shacl_graph = Graph()
    shacl_graph.parse(shacl_path, format="turtle")
    conforms, _, results_text = validate(
        data_graph=graph,
        shacl_graph=shacl_graph,
        inference="rdfs",
        abort_on_first=False,
    )
    return conforms, results_text


def migration_summary(extracted_v2: dict[str, Any], graph: Graph, conforms: bool) -> str:
    procedures = extracted_v2.get("procedures", [])
    step_count = sum(len(proc.get("steps", [])) for proc in procedures)
    warning_count = sum(len(proc.get("warnings", [])) for proc in procedures)
    hazard_count = sum(len(proc.get("hazards", [])) for proc in procedures)
    evidence_count = len(list(graph.subjects(RDF.type, AV.SourceEvidence)))
    system_count = len(list(graph.subjects(RDF.type, AV.AircraftSystem)))

    return "\n".join(
        [
            "# Controlled Ontology V2 Migration Summary",
            "",
            f"- Procedures: `{len(procedures)}`",
            f"- Steps: `{step_count}`",
            f"- Warnings: `{warning_count}`",
            f"- Explicit hazards: `{hazard_count}`",
            f"- SourceEvidence nodes: `{evidence_count}`",
            f"- AircraftSystem nodes: `{system_count}`",
            f"- RDF triples: `{len(graph)}`",
            f"- SHACL conforms: `{conforms}`",
            "",
            "This migration is deterministic and uses the current extracted.json as input.",
            "It is intended to compare ontology design rather than LLM extraction variance.",
            "",
        ]
    )


def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    shacl_path = Path(args.shacl)

    extracted = json.loads(input_path.read_text(encoding="utf-8"))
    extracted_v2 = migrate_extracted(extracted)

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "extracted_v2.json"
    kg_path = output_dir / "kg_v2.ttl"
    report_path = output_dir / "validation_report_v2.txt"
    summary_path = output_dir / "migration_summary.md"

    json_path.write_text(json.dumps(extracted_v2, ensure_ascii=False, indent=2), encoding="utf-8")

    graph = json_to_rdf_v2(extracted_v2)
    graph.serialize(destination=kg_path, format="turtle")

    conforms, results_text = run_shacl(graph, shacl_path)
    report_path.write_text(
        f"SHACL Validation Report V2\n{'=' * 40}\nConforms: {conforms}\n\n{results_text}",
        encoding="utf-8",
    )
    summary_path.write_text(migration_summary(extracted_v2, graph, conforms), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {kg_path}")
    print(f"Wrote {report_path}")
    print(f"Wrote {summary_path}")
    print(f"SHACL conforms: {conforms}")

    if not conforms:
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate v1 extracted aviation data into controlled ontology v2.")
    parser.add_argument("--input", default="output/extracted.json")
    parser.add_argument("--output-dir", default="output/schema_v2")
    parser.add_argument("--shacl", default="shacl/procedure_shapes_v2.ttl")
    return parser


if __name__ == "__main__":
    run(build_parser().parse_args())
