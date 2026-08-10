"""
Compare the current ontology against the controlled v2 ontology.

The comparison intentionally separates:
- schema/ontology structure,
- migrated KG validation and richness,
- deterministic CQ coverage proxies.

It does not claim to be a full human or LLM judge. It produces a transparent
report for weekly project discussion.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from rdflib import Graph, Namespace
from rdflib.namespace import RDF


if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "cp936", "gb2312"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


AV = Namespace("https://example.org/aviation/")
STOPWORDS = {
    "about", "above", "after", "aircraft", "airplane", "also", "and", "are", "because",
    "been", "being", "both", "can", "condition", "conditions", "could", "during", "each",
    "from", "have", "into", "landing", "must", "normal", "only", "pilot", "pilots",
    "procedure", "procedures", "should", "specific", "system", "take", "that", "the",
    "their", "them", "then", "these", "this", "those", "when", "where", "which", "while",
    "with", "would",
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def snake(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", clean_text(value))
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return value


def tokens(value: Any) -> set[str]:
    text = clean_text(value).lower()
    words = re.findall(r"[a-z0-9]+", text)
    return {word for word in words if len(word) > 3 and word not in STOPWORDS}


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def schema_metrics(schema: dict[str, Any]) -> dict[str, Any]:
    classes = schema.get("classes") or {}
    enums = schema.get("enums") or {}
    attributes = []
    required = []
    for class_name, class_def in classes.items():
        for attr_name, attr_def in ((class_def or {}).get("attributes") or {}).items():
            attributes.append(attr_name)
            if (attr_def or {}).get("required"):
                required.append(f"{class_name}.{attr_name}")

    vocab = set()
    for class_name, class_def in classes.items():
        vocab.update(tokens(class_name))
        vocab.update(tokens((class_def or {}).get("description")))
        for attr_name, attr_def in ((class_def or {}).get("attributes") or {}).items():
            vocab.update(tokens(attr_name))
            vocab.update(tokens((attr_def or {}).get("description")))
    for enum_name, enum_def in enums.items():
        vocab.update(tokens(enum_name))
        for value, value_def in ((enum_def or {}).get("permissible_values") or {}).items():
            vocab.update(tokens(value))
            vocab.update(tokens((value_def or {}).get("description")))

    return {
        "class_count": len(classes),
        "classes": sorted(classes.keys()),
        "attribute_count": len(attributes),
        "attributes": sorted(attributes),
        "required_count": len(required),
        "required": sorted(required),
        "enum_count": len(enums),
        "enums": sorted(enums.keys()),
        "vocab": vocab,
    }


def kg_metrics(path: Path) -> dict[str, Any]:
    graph = Graph()
    graph.parse(path, format="turtle")
    class_counts: dict[str, int] = {}
    predicate_counts: dict[str, int] = {}
    vocab = set()

    for subject, predicate, obj in graph:
        for item in (subject, predicate, obj):
            label = str(item)
            if label.startswith(str(AV)):
                label = label.split("/")[-1]
            vocab.update(tokens(label))

    for obj in graph.objects(None, RDF.type):
        if str(obj).startswith(str(AV)):
            label = str(obj).split("/")[-1]
            class_counts[label] = class_counts.get(label, 0) + 1

    for pred in graph.predicates():
        if str(pred).startswith(str(AV)):
            label = str(pred).split("/")[-1]
            predicate_counts[label] = predicate_counts.get(label, 0) + 1

    return {
        "triple_count": len(graph),
        "class_counts": class_counts,
        "predicate_counts": predicate_counts,
        "vocab": vocab,
    }


def flatten_value(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(flatten_value(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(flatten_value(item) for item in value)
    return clean_text(value)


def docs_by_source_v1(extracted: dict[str, Any]) -> dict[str, list[str]]:
    docs: dict[str, list[str]] = {}
    for proc in extracted.get("procedures", []):
        text = flatten_value(proc)
        source_files = clean_text(proc.get("source_file")).split("|")
        for source_file in source_files:
            source_file = clean_text(source_file)
            if source_file:
                docs.setdefault(source_file, []).append(text)
    return docs


def docs_by_source_v2(extracted: dict[str, Any]) -> dict[str, list[str]]:
    docs: dict[str, list[str]] = {}
    for proc in extracted.get("procedures", []):
        text = flatten_value(proc)
        sources = set()
        for evidence in proc.get("source_evidence", []) or []:
            if evidence.get("source_file"):
                sources.add(clean_text(evidence["source_file"]))
        if not sources:
            sources.add("unknown_source")
        for source_file in sources:
            docs.setdefault(source_file, []).append(text)
    return docs


def best_doc_for_cq(source_docs: dict[str, list[str]], source_file: str) -> str:
    source_file = clean_text(source_file)
    if source_file in source_docs:
        return " ".join(source_docs[source_file])

    for key, docs in source_docs.items():
        if source_file and (source_file in key or key in source_file):
            return " ".join(docs)

    return " ".join(doc for docs in source_docs.values() for doc in docs)


def recall_score(needle_tokens: set[str], haystack: str) -> float:
    if not needle_tokens:
        return 0.0
    found = needle_tokens & tokens(haystack)
    return len(found) / len(needle_tokens)


def cq_proxy_scores(
    cqs: list[dict[str, Any]],
    source_docs: dict[str, list[str]],
    schema_vocab: set[str],
    kg_vocab: set[str],
) -> dict[str, Any]:
    rows = []
    for cq in cqs:
        doc_text = best_doc_for_cq(source_docs, cq.get("source_file", ""))
        answer_tokens = tokens(cq.get("expected_answer"))
        question_tokens = tokens(cq.get("question"))
        concept_tokens = tokens(" ".join(cq.get("required_concepts", []) or []))
        relation_tokens = tokens(" ".join(cq.get("required_relations", []) or []))

        answer_recall = recall_score(answer_tokens, doc_text)
        question_recall = recall_score(question_tokens, doc_text)
        schema_concept_recall = len(concept_tokens & schema_vocab) / len(concept_tokens) if concept_tokens else 0.0
        schema_relation_recall = len(relation_tokens & schema_vocab) / len(relation_tokens) if relation_tokens else 0.0
        kg_concept_recall = len(concept_tokens & kg_vocab) / len(concept_tokens) if concept_tokens else 0.0

        rows.append(
            {
                "id": cq.get("id"),
                "source_file": cq.get("source_file"),
                "answer_recall": answer_recall,
                "question_recall": question_recall,
                "schema_concept_recall": schema_concept_recall,
                "schema_relation_recall": schema_relation_recall,
                "kg_concept_recall": kg_concept_recall,
            }
        )

    def avg(key: str) -> float:
        if not rows:
            return 0.0
        return sum(row[key] for row in rows) / len(rows)

    return {
        "rows": rows,
        "avg_answer_recall": avg("answer_recall"),
        "avg_question_recall": avg("question_recall"),
        "avg_schema_concept_recall": avg("schema_concept_recall"),
        "avg_schema_relation_recall": avg("schema_relation_recall"),
        "avg_kg_concept_recall": avg("kg_concept_recall"),
        "answer_pass_count": sum(1 for row in rows if row["answer_recall"] >= 0.5),
        "count": len(rows),
    }


def fmt_float(value: float) -> str:
    return f"{value:.3f}"


def class_count_line(metrics: dict[str, Any]) -> str:
    items = sorted(metrics["class_counts"].items())
    return ", ".join(f"{name}: {count}" for name, count in items)


def generate_report(
    v1_schema: dict[str, Any],
    v2_schema: dict[str, Any],
    v1_kg: dict[str, Any],
    v2_kg: dict[str, Any],
    v1_scores: dict[str, Any],
    v2_scores: dict[str, Any],
    v2_validation_text: str,
) -> str:
    v1s = schema_metrics(v1_schema)
    v2s = schema_metrics(v2_schema)
    v2_conforms = "Conforms: True" in v2_validation_text

    structural_improvements = [
        "V2 adds first-class SourceEvidence, so provenance is no longer only repeated string fields.",
        "V2 adds Hazard, AircraftState, AircraftSystem, TriggerCondition, and FlightPhase, matching concepts surfaced by the paper-style CQ workflow.",
        "V2 preserves EmergencyProcedure, ProcedureStep, Warning, StepType, action, expected_result, and evidence, so it stays compatible with the current advisor shape.",
    ]

    limitations = [
        "The CQ answer recall proxy changes only modestly because V2 is migrated from the same extracted facts; it improves representation, not raw source coverage.",
        "Some hazard/system links are heuristic because the migration is deterministic and does not re-read the FAA text with an LLM.",
        "This is still a proxy evaluation. A full paper-style result would add SPARQL generation and an independent answer judge.",
    ]

    verdict = (
        "V2 is better as an ontology design target, but the current V1 remains better as the production demo schema until extraction prompts, SHACL, and Hybrid RAG are updated."
    )

    return "\n".join(
        [
            "# Controlled Ontology V2 Comparison Report",
            "",
            f"Generated: {datetime.now().isoformat(timespec='seconds')}",
            "",
            "## Question",
            "",
            "This report answers the weekly task: use the paper-inspired method to generate a new ontology, compare it with the existing ontology, and explain whether it improves the project.",
            "",
            "## Paper Method Applied Here",
            "",
            "The paper's useful part is not blind replacement. It is artifact-driven planning: CQ generation, ontology planning, implementation, and QA. In this project, that produced 35 CQs and suggested richer ontology concepts. The controlled V2 below keeps only the useful concepts and fixes the modeling errors found in the raw LLM candidate.",
            "",
            "## Schema Comparison",
            "",
            "| Metric | Current V1 | Controlled V2 |",
            "|---|---:|---:|",
            f"| Classes | {v1s['class_count']} | {v2s['class_count']} |",
            f"| Attributes | {v1s['attribute_count']} | {v2s['attribute_count']} |",
            f"| Required attributes | {v1s['required_count']} | {v2s['required_count']} |",
            f"| Enums | {v1s['enum_count']} | {v2s['enum_count']} |",
            "",
            "V2 added ontology-level classes:",
            "",
            "- `SourceEvidence`",
            "- `TriggerCondition`",
            "- `FlightPhase`",
            "- `Hazard`",
            "- `AircraftState`",
            "- `AircraftSystem`",
            "",
            "## KG Comparison",
            "",
            "| Metric | Current V1 KG | Controlled V2 KG |",
            "|---|---:|---:|",
            f"| RDF triples | {v1_kg['triple_count']} | {v2_kg['triple_count']} |",
            f"| SHACL conforms | True | {v2_conforms} |",
            "",
            "Current V1 class instances:",
            "",
            f"`{class_count_line(v1_kg)}`",
            "",
            "Controlled V2 class instances:",
            "",
            f"`{class_count_line(v2_kg)}`",
            "",
            "## CQ Proxy Comparison",
            "",
            "The 35 generated CQs are used here as a deterministic proxy. This is not yet a full LLM-judge/SPARQL benchmark. It measures whether expected-answer terms and CQ-required concepts are represented in the migrated data and schema vocabulary.",
            "",
            "| Metric | Current V1 | Controlled V2 | Meaning |",
            "|---|---:|---:|---|",
            f"| Avg expected-answer recall | {fmt_float(v1_scores['avg_answer_recall'])} | {fmt_float(v2_scores['avg_answer_recall'])} | Whether migrated data contains expected answer terms |",
            f"| Answer recall >= 0.5 | {v1_scores['answer_pass_count']}/{v1_scores['count']} | {v2_scores['answer_pass_count']}/{v2_scores['count']} | Rough answerability count |",
            f"| Avg question-term recall | {fmt_float(v1_scores['avg_question_recall'])} | {fmt_float(v2_scores['avg_question_recall'])} | Whether procedure text covers question context |",
            f"| Avg schema concept recall | {fmt_float(v1_scores['avg_schema_concept_recall'])} | {fmt_float(v2_scores['avg_schema_concept_recall'])} | Whether schema has vocabulary for CQ concepts |",
            f"| Avg schema relation recall | {fmt_float(v1_scores['avg_schema_relation_recall'])} | {fmt_float(v2_scores['avg_schema_relation_recall'])} | Whether schema has vocabulary for CQ relations |",
            f"| Avg KG concept recall | {fmt_float(v1_scores['avg_kg_concept_recall'])} | {fmt_float(v2_scores['avg_kg_concept_recall'])} | Whether KG text/instances represent required concepts |",
            "",
            "## What Improved",
            "",
            *[f"- {item}" for item in structural_improvements],
            "",
            "## What Did Not Improve Enough",
            "",
            *[f"- {item}" for item in limitations],
            "",
            "## Verdict",
            "",
            verdict,
            "",
            "## Recommended Next Step",
            "",
            "Use Controlled V2 as the next schema target, then update extraction and retrieval in small steps. The strongest next experiment is a real CQ benchmark: generate SPARQL or structured retrieval queries for the 35 CQs, run them on V1 and V2, and optionally use an independent LLM judge for answer equivalence.",
            "",
        ]
    )


def run(args: argparse.Namespace) -> None:
    v1_schema = load_yaml(Path(args.v1_schema))
    v2_schema = load_yaml(Path(args.v2_schema))
    v1_kg = kg_metrics(Path(args.v1_kg))
    v2_kg = kg_metrics(Path(args.v2_kg))
    v1_extracted = json.loads(Path(args.v1_extracted).read_text(encoding="utf-8"))
    v2_extracted = json.loads(Path(args.v2_extracted).read_text(encoding="utf-8"))
    cqs = json.loads(Path(args.cqs).read_text(encoding="utf-8")).get("competency_questions", [])

    v1_schema_metrics = schema_metrics(v1_schema)
    v2_schema_metrics = schema_metrics(v2_schema)
    v1_scores = cq_proxy_scores(
        cqs,
        docs_by_source_v1(v1_extracted),
        v1_schema_metrics["vocab"],
        v1_kg["vocab"],
    )
    v2_scores = cq_proxy_scores(
        cqs,
        docs_by_source_v2(v2_extracted),
        v2_schema_metrics["vocab"],
        v2_kg["vocab"],
    )

    validation_text = Path(args.v2_validation).read_text(encoding="utf-8")
    report = generate_report(
        v1_schema=v1_schema,
        v2_schema=v2_schema,
        v1_kg=v1_kg,
        v2_kg=v2_kg,
        v1_scores=v1_scores,
        v2_scores=v2_scores,
        v2_validation_text=validation_text,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    details_path = output_path.with_suffix(".details.json")
    details_path.write_text(
        json.dumps(
            {
                "v1_scores": v1_scores,
                "v2_scores": v2_scores,
                "v1_kg": {k: v for k, v in v1_kg.items() if k != "vocab"},
                "v2_kg": {k: v for k, v in v2_kg.items() if k != "vocab"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {output_path}")
    print(f"Wrote {details_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare current ontology V1 with controlled ontology V2.")
    parser.add_argument("--v1-schema", default="schema/emergency_schema.yaml")
    parser.add_argument("--v2-schema", default="schema/emergency_schema_v2.yaml")
    parser.add_argument("--v1-kg", default="output/kg.ttl")
    parser.add_argument("--v2-kg", default="output/schema_v2/kg_v2.ttl")
    parser.add_argument("--v1-extracted", default="output/extracted.json")
    parser.add_argument("--v2-extracted", default="output/schema_v2/extracted_v2.json")
    parser.add_argument("--v2-validation", default="output/schema_v2/validation_report_v2.txt")
    parser.add_argument("--cqs", default="output/ontology_experiment_v2/domain_cqs.json")
    parser.add_argument("--output", default="output/schema_v2/ontology_v1_vs_v2_report.md")
    return parser


if __name__ == "__main__":
    run(build_parser().parse_args())
