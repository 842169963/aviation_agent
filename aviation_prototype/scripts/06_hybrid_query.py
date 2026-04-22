"""
Step 6: Hybrid RAG Query
========================
Run a KG + vector retrieval query over the validated aviation procedure data.

Hybrid RAG v1 rule:
- Vector search finds semantic candidate procedures.
- KG search finds structured keyword candidates.
- Final steps, warnings, and provenance are read from output/kg.ttl.
- Optional LLM synthesis may rewrite retrieved KG content, but must not invent new steps.

Usage:
    python scripts/06_hybrid_query.py --question "accidentally flew into clouds"
    python scripts/06_hybrid_query.py --question "accidentally flew into clouds" --synthesize
    python scripts/06_hybrid_query.py --question "accidentally flew into clouds" --synthesis-only
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI
from rdflib import Graph, Namespace
from rdflib.namespace import RDF


if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "cp936", "gb2312"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KG_FILE = PROJECT_ROOT / "output" / "kg.ttl"
VECTOR_DIR = PROJECT_ROOT / "output" / "vector_index"
COLLECTION_NAME = "aviation_procedures"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_SYNTHESIS_MODEL = "gpt-4o-mini"
AV = Namespace("https://example.org/aviation/")


def load_embedding_client() -> tuple[OpenAI, str]:
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    base_url = os.getenv("OPENAI_BASE_URL") or None
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    model = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)

    if provider == "gemini" and not base_url:
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

    if not api_key:
        raise RuntimeError("No API key found. Set OPENAI_API_KEY or GEMINI_API_KEY in .env.")

    return OpenAI(api_key=api_key, base_url=base_url), model


def load_synthesis_client() -> tuple[OpenAI, str]:
    """Load an OpenAI-compatible chat client for grounded answer synthesis."""
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    base_url = os.getenv("OPENAI_BASE_URL") or None
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    model = (
        os.getenv("SYNTHESIS_MODEL")
        or os.getenv("MODEL_NAME")
        or DEFAULT_SYNTHESIS_MODEL
    )

    if provider == "gemini" and not base_url:
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

    if not api_key:
        raise RuntimeError("No API key found. Set OPENAI_API_KEY or GEMINI_API_KEY in .env.")

    return OpenAI(api_key=api_key, base_url=base_url), model


def embed_query(question: str) -> list[float]:
    client, model = load_embedding_client()
    response = client.embeddings.create(model=model, input=question)
    return response.data[0].embedding


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def tokenize(question: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9]+", question.lower())
    stopwords = {
        "a", "an", "and", "are", "as", "at", "be", "do", "for", "from", "how",
        "i", "if", "in", "into", "is", "it", "my", "of", "on", "or", "should",
        "the", "to", "what", "when", "with",
    }
    return [word for word in words if len(word) > 2 and word not in stopwords]


def text_match_score(question: str, value: str) -> int:
    if not value:
        return 0

    q = question.lower()
    v = value.lower()
    tokens = tokenize(question)
    score = 0

    if q and q in v:
        score += 2

    for token in tokens:
        if token in v:
            score += 1

    return score


def load_kg() -> Graph:
    if not KG_FILE.exists():
        raise FileNotFoundError(f"Missing KG file: {KG_FILE}")
    graph = Graph()
    graph.bind("av", AV)
    graph.parse(KG_FILE, format="turtle")
    return graph


def literal(graph: Graph, subject, predicate) -> str:
    value = graph.value(subject, predicate)
    return str(value) if value is not None else ""


def load_procedure_records(graph: Graph) -> dict[str, dict]:
    records = {}

    for proc in graph.subjects(RDF.type, AV.EmergencyProcedure):
        name = literal(graph, proc, AV.name)
        if not name:
            continue

        steps = []
        for step in graph.objects(proc, AV.hasStep):
            step_number = literal(graph, step, AV.step_number)
            try:
                number = int(step_number)
            except ValueError:
                number = 0
            steps.append({
                "num": number,
                "action": literal(graph, step, AV.action),
                "result": literal(graph, step, AV.expected_result),
                "source_excerpt": literal(graph, step, AV.source_excerpt),
            })

        warnings = []
        for warning in graph.objects(proc, AV.hasWarning):
            desc = literal(graph, warning, AV.description)
            if desc:
                warnings.append(desc)

        records[name] = {
            "name": name,
            "trigger": literal(graph, proc, AV.trigger_condition) or "N/A",
            "aircraft_phase": literal(graph, proc, AV.aircraft_phase),
            "source_file": literal(graph, proc, AV.source_file),
            "source_section": literal(graph, proc, AV.source_section),
            "proc_excerpt": literal(graph, proc, AV.source_excerpt),
            "steps": sorted(steps, key=lambda item: item["num"]),
            "warnings": warnings,
        }

    return records


def kg_retrieve(question: str, records: dict[str, dict]) -> dict[str, dict]:
    weights = {
        "name": 3,
        "trigger": 2,
        "aircraft_phase": 1,
        "source_section": 2,
        "proc_excerpt": 1,
        "step.action": 2,
        "step.source_excerpt": 1,
        "warning.description": 1,
    }
    results = {}

    for name, record in records.items():
        score = 0
        fields = []

        field_values = {
            "name": record["name"],
            "trigger": record["trigger"],
            "aircraft_phase": record["aircraft_phase"],
            "source_section": record["source_section"],
            "proc_excerpt": record["proc_excerpt"],
        }

        for field, value in field_values.items():
            if text_match_score(question, value):
                score += weights[field]
                fields.append(field)

        if any(text_match_score(question, step["action"]) for step in record["steps"]):
            score += weights["step.action"]
            fields.append("step.action")

        if any(text_match_score(question, step["source_excerpt"]) for step in record["steps"]):
            score += weights["step.source_excerpt"]
            fields.append("step.source_excerpt")

        if any(text_match_score(question, warning) for warning in record["warnings"]):
            score += weights["warning.description"]
            fields.append("warning.description")

        if score:
            results[name] = {
                "procedure_name": name,
                "kg_score": score,
                "matched_fields": fields,
            }

    return results


def vector_retrieve(question: str, n_results: int = 5) -> dict[str, dict]:
    if not VECTOR_DIR.exists():
        raise FileNotFoundError(
            f"Missing vector index: {VECTOR_DIR}. Run scripts/05_build_vector_index.py first."
        )

    chroma_client = chromadb.PersistentClient(path=str(VECTOR_DIR))
    collection = chroma_client.get_collection(COLLECTION_NAME)
    query_embedding = embed_query(question)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["metadatas", "distances", "documents"],
    )

    vector_hits = {}
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for idx, metadata in enumerate(metadatas):
        name = metadata.get("procedure_name", "")
        if not name:
            continue
        rank = idx + 1
        if rank == 1:
            score = 3
        elif rank <= 3:
            score = 2
        else:
            score = 1

        vector_hits[name] = {
            "procedure_name": name,
            "vector_score": score,
            "vector_rank": rank,
            "distance": distances[idx] if idx < len(distances) else None,
        }

    return vector_hits


def merge_candidates(kg_hits: dict[str, dict], vector_hits: dict[str, dict], top_k: int) -> list[dict]:
    merged = defaultdict(lambda: {
        "procedure_name": "",
        "final_score": 0,
        "kg_score": 0,
        "vector_score": 0,
        "matched_fields": [],
        "vector_rank": None,
        "distance": None,
    })

    for name, hit in kg_hits.items():
        item = merged[name]
        item["procedure_name"] = name
        item["kg_score"] = hit["kg_score"]
        item["matched_fields"] = hit["matched_fields"]

    for name, hit in vector_hits.items():
        item = merged[name]
        item["procedure_name"] = name
        item["vector_score"] = hit["vector_score"]
        item["vector_rank"] = hit["vector_rank"]
        item["distance"] = hit["distance"]

    candidates = []
    for item in merged.values():
        item["final_score"] = item["kg_score"] + item["vector_score"]
        candidates.append(item)

    return sorted(
        candidates,
        key=lambda item: (
            -item["final_score"],
            item["vector_rank"] if item["vector_rank"] is not None else 999,
            item["procedure_name"],
        ),
    )[:top_k]


def print_debug(candidates: list[dict]) -> None:
    print("\nRetrieval candidates")
    print("-" * 60)
    for item in candidates:
        distance = item["distance"]
        distance_text = f"{distance:.4f}" if isinstance(distance, float) else "N/A"
        fields = ", ".join(item["matched_fields"]) if item["matched_fields"] else "none"
        print(
            f"- {item['procedure_name']} | final={item['final_score']} "
            f"kg={item['kg_score']} vector={item['vector_score']} "
            f"rank={item['vector_rank'] or 'N/A'} distance={distance_text} fields={fields}"
        )


def format_advisory(records: dict[str, dict], candidates: list[dict], question: str) -> None:
    if not candidates:
        print(f"\nNo procedure found for: {question}")
        print("Try running scripts/03_query.py --list to inspect available procedures.")
        return

    print("\n" + "=" * 72)
    print("AVIATION HYBRID RAG QUERY RESULT")
    print("=" * 72)
    print(f"Question: {question}")

    for candidate in candidates:
        record = records.get(candidate["procedure_name"])
        if not record:
            continue

        print("\n" + "-" * 72)
        print(f"Procedure: {record['name']}")
        print(f"Final score: {candidate['final_score']} "
              f"(KG {candidate['kg_score']} + Vector {candidate['vector_score']})")
        print(f"Trigger: {record['trigger']}")
        if record["source_file"]:
            print(f"Source file: {record['source_file']}")
        if record["source_section"]:
            print(f"Source section: {record['source_section']}")
        if record["proc_excerpt"]:
            excerpt = normalize_space(record["proc_excerpt"])
            if len(excerpt) > 180:
                excerpt = excerpt[:180] + "..."
            print(f"Procedure evidence: {excerpt}")

        print("\nSteps:")
        for step in record["steps"]:
            print(f"  [{step['num']}] {step['action']}")
            if step["result"]:
                print(f"      Expected result: {step['result']}")
            if step["source_excerpt"]:
                excerpt = normalize_space(step["source_excerpt"])
                if len(excerpt) > 160:
                    excerpt = excerpt[:160] + "..."
                print(f"      Evidence: {excerpt}")

        if record["warnings"]:
            print("\nWarnings:")
            for warning in record["warnings"]:
                warning_text = normalize_space(warning)
                if len(warning_text) > 180:
                    warning_text = warning_text[:180] + "..."
                print(f"  - {warning_text}")

    print("\n" + "=" * 72)
    print("Source policy: retrieval is hybrid; final procedure content is read from the validated KG.")
    print("Always follow aircraft POH/AFM, ATC instructions, and pilot judgment.")
    print("=" * 72)


def is_training_or_preparation_step(step: dict) -> bool:
    """Heuristic split for synthesis only; KG schema does not yet encode step type."""
    text = " ".join([
        step.get("action", ""),
        step.get("result", ""),
        step.get("source_excerpt", ""),
    ]).lower()
    patterns = (
        "practice",
        "training",
        "student pilot",
        "brief passenger",
        "brief passengers",
        "instruct passengers",
        "study the information",
        "should know",
        "know the evacuation",
        "conditions for safe deployment",
        "basic sequence of steps for deployment",
    )
    return any(pattern in text for pattern in patterns)


def append_step_lines(lines: list[str], step: dict) -> None:
    lines.append(f"[{step['num']}] Action: {normalize_space(step['action'])}")
    if step["result"]:
        lines.append(f"    Expected result: {normalize_space(step['result'])}")
    if step["source_excerpt"]:
        lines.append(f"    Evidence: {normalize_space(step['source_excerpt'])}")


def build_synthesis_context(records: dict[str, dict], candidates: list[dict]) -> str:
    """Build compact, auditable context for the synthesis model."""
    sections = []

    for candidate in candidates:
        record = records.get(candidate["procedure_name"])
        if not record:
            continue

        lines = [
            f"Procedure: {record['name']}",
            f"Retrieval score: final={candidate['final_score']} "
            f"kg={candidate['kg_score']} vector={candidate['vector_score']}",
            f"Trigger: {record['trigger']}",
            f"Phase: {record['aircraft_phase']}",
            f"Source file: {record['source_file']}",
            f"Source section: {record['source_section']}",
            f"Procedure evidence: {normalize_space(record['proc_excerpt'])}",
            "Operational actions from KG:",
        ]

        operational_steps = []
        training_or_preparation_steps = []
        for step in record["steps"]:
            if is_training_or_preparation_step(step):
                training_or_preparation_steps.append(step)
            else:
                operational_steps.append(step)

        if operational_steps:
            for step in operational_steps:
                append_step_lines(lines, step)
        else:
            lines.append("NONE_EXPLICITLY_IDENTIFIED_IN_KG")

        lines.append("Training/preparation/background notes from KG:")
        if training_or_preparation_steps:
            for step in training_or_preparation_steps:
                append_step_lines(lines, step)
        else:
            lines.append("NONE_RETRIEVED")

        lines.append("Procedure-specific KG warnings:")
        if record["warnings"]:
            for warning in record["warnings"]:
                lines.append(f"- {normalize_space(warning)}")
        else:
            lines.append("NONE_RETRIEVED")

        sections.append("\n".join(lines))

    return "\n\n---\n\n".join(sections)


def synthesize_answer(question: str, records: dict[str, dict], candidates: list[dict]) -> tuple[str, str]:
    """Generate a grounded advisor response from retrieved KG context."""
    if not candidates:
        return "No retrieved procedure is available to synthesize from.", ""

    client, model = load_synthesis_client()
    context = build_synthesis_context(records, candidates)

    system_prompt = (
        "You are a cautious aviation emergency procedure response formatter. "
        "Use only the retrieved KG context provided by the user. "
        "Do not invent procedures, checklist steps, speeds, altitudes, frequencies, aircraft-specific limits, or causal claims. "
        "If the retrieved context is insufficient, say what is missing. "
        "Do not treat the general POH/AFM disclaimer as a procedure-specific warning. "
        "Write in the same language as the user's question when possible. "
        "Keep the answer concise, operational, and clearly grounded. "
        "Always remind that aircraft POH/AFM, ATC instructions, and pilot judgment take priority."
    )
    user_prompt = (
        f"User question:\n{question}\n\n"
        "Retrieved KG context:\n"
        f"{context}\n\n"
        "Write a grounded advisor response with these sections:\n"
        "1. Likely relevant procedure\n"
        "2. Operational actions from the KG\n"
        "3. Training/preparation/background notes from the KG\n"
        "4. Procedure-specific warnings from the KG\n"
        "5. Source/evidence note and safety disclaimer\n"
        "Use only the items listed under the matching context headings. "
        "If Procedure-specific KG warnings is NONE_RETRIEVED, say no procedure-specific warning was retrieved. "
        "Never put the POH/AFM disclaimer in the warnings section. "
        "Do not add any step that is not present in the KG context."
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )
    answer = response.choices[0].message.content or ""
    return answer.strip(), model


def print_synthesis(answer: str, model: str) -> None:
    print("\n" + "=" * 72)
    print("GROUNDED LLM SYNTHESIS")
    print("=" * 72)
    if model:
        print(f"Model: {model}")
        print("-" * 72)
    print(answer)
    print("=" * 72)


def run_query(
    question: str,
    top_k: int,
    vector_top_k: int,
    debug: bool,
    synthesize: bool,
    synthesis_only: bool,
) -> None:
    graph = load_kg()
    records = load_procedure_records(graph)

    kg_hits = kg_retrieve(question, records)
    vector_hits = vector_retrieve(question, n_results=vector_top_k)
    candidates = merge_candidates(kg_hits, vector_hits, top_k=top_k)

    if debug and not synthesis_only:
        print_debug(candidates)

    if not synthesis_only:
        format_advisory(records, candidates, question)

    if synthesize or synthesis_only:
        answer, model = synthesize_answer(question, records, candidates)
        print_synthesis(answer, model)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid KG + vector query for aviation procedures")
    parser.add_argument("--question", "-q", required=True, help="Natural language question")
    parser.add_argument("--top-k", type=int, default=3, help="Number of final procedures to show")
    parser.add_argument("--vector-top-k", type=int, default=5, help="Number of vector candidates to retrieve")
    parser.add_argument("--no-debug", action="store_true", help="Hide retrieval candidate scores")
    parser.add_argument("--synthesize", action="store_true", help="Generate a grounded LLM advisor response")
    parser.add_argument("--synthesis-only", action="store_true", help="Only print the grounded LLM advisor response")
    args = parser.parse_args()

    run_query(
        question=args.question,
        top_k=args.top_k,
        vector_top_k=args.vector_top_k,
        debug=not args.no_debug,
        synthesize=args.synthesize,
        synthesis_only=args.synthesis_only,
    )


if __name__ == "__main__":
    main()
