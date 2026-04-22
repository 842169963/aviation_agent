"""
Step 7: Evaluate Hybrid RAG
===========================
Run a small regression suite over the Hybrid RAG retriever and optional
grounded synthesis layer.

The goal is not to prove aviation correctness. It is to catch retrieval
regressions and obvious answer-format drift while the prototype evolves.

Usage:
    python scripts/07_eval_hybrid_rag.py
    python scripts/07_eval_hybrid_rag.py --include-synthesis
"""

import argparse
import importlib.util
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "cp936", "gb2312"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HYBRID_QUERY_FILE = PROJECT_ROOT / "scripts" / "06_hybrid_query.py"
REPORT_FILE = PROJECT_ROOT / "output" / "hybrid_eval_report.md"


@dataclass
class EvalCase:
    case_id: str
    question: str
    expected_procedure: str | None
    category: str
    notes: str = ""
    expect_abstain: bool = False
    run_synthesis: bool = True


@dataclass
class EvalResult:
    case: EvalCase
    top1: str | None
    top3: list[str]
    top1_score: int | None
    top1_distance: float | None
    retrieval_pass: bool
    abstain_decision: bool
    synthesis_pass: bool | None = None
    synthesis_model: str | None = None
    synthesis_issues: list[str] = field(default_factory=list)
    error: str | None = None


EVAL_CASES = [
    EvalCase(
        "happy_imc_semantic",
        "accidentally flew into clouds",
        "Inadvertent VFR Flight Into IMC",
        "happy_path",
        "Pure semantic phrasing; KG keyword score was previously 0.",
    ),
    EvalCase(
        "happy_cabin_smoke",
        "smoke in cabin",
        "Cabin Fire",
        "happy_path",
    ),
    EvalCase(
        "happy_parachute",
        "pilot incapacitated parachute",
        "Ballistic Parachute Deployment",
        "happy_path",
    ),
    EvalCase(
        "happy_snow_whiteout",
        "landing on snow whiteout",
        "Snow Landing",
        "happy_path",
    ),
    EvalCase(
        "happy_efato",
        "engine failure after takeoff",
        "Engine Failure After Takeoff (Single-Engine)",
        "happy_path",
        "Also checks that training notes are not treated as operational actions in synthesis.",
    ),
    EvalCase(
        "synonym_electrical_fire",
        "burning insulation smell in cockpit",
        "Electrical Fire",
        "semantic_variant",
    ),
    EvalCase(
        "synonym_landing_gear",
        "gear will not come down for landing",
        "Landing Gear Malfunction",
        "semantic_variant",
    ),
    EvalCase(
        "synonym_open_door",
        "door popped open after takeoff",
        "Inadvertent Door Opening In-Flight",
        "semantic_variant",
    ),
    EvalCase(
        "synonym_emergency_descent",
        "rapid descent due to sudden pressurization loss",
        "Emergency Descent",
        "semantic_variant",
    ),
    EvalCase(
        "synonym_split_flap",
        "one flap is stuck and the airplane rolls",
        "Asymmetric Split Flap",
        "semantic_variant",
    ),
    EvalCase(
        "cross_fire_smoke",
        "fire and smoke during flight",
        None,
        "ambiguous",
        "Ambiguous by design; useful for inspecting competing top candidates.",
        run_synthesis=False,
    ),
    EvalCase(
        "cross_fire_descent",
        "need to descend rapidly because of fire or pressurization",
        None,
        "ambiguous",
        "Ambiguous by design; current top result may be a fire procedure rather than Emergency Descent.",
        run_synthesis=False,
    ),
    EvalCase(
        "unrelated_restaurant",
        "what is the best restaurant near the airport",
        None,
        "out_of_scope",
        "Should ideally abstain instead of forcing an emergency procedure.",
        expect_abstain=True,
        run_synthesis=False,
    ),
    EvalCase(
        "unrelated_fuel_planning",
        "how much fuel should I plan for a cross country trip",
        None,
        "out_of_scope",
        "Should ideally abstain; current retrieval may still force a candidate.",
        expect_abstain=True,
        run_synthesis=False,
    ),
]

REQUIRED_SYNTHESIS_HEADINGS = [
    "Likely relevant procedure",
    "Operational actions from the KG",
    "Training/preparation/background notes from the KG",
    "Procedure-specific warnings from the KG",
    "Source/evidence note and safety disclaimer",
]


def load_hybrid_module() -> Any:
    spec = importlib.util.spec_from_file_location("hybrid_query", HYBRID_QUERY_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {HYBRID_QUERY_FILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def should_abstain(candidate: dict | None, min_final_score: int, max_vector_distance: float) -> bool:
    if not candidate:
        return True

    final_score = candidate.get("final_score") or 0
    distance = candidate.get("distance")

    if final_score < min_final_score:
        return True
    if isinstance(distance, float) and distance > max_vector_distance:
        return True
    return False


def check_synthesis(answer: str, case: EvalCase) -> list[str]:
    issues = []
    lower_answer = answer.lower()

    for heading in REQUIRED_SYNTHESIS_HEADINGS:
        if heading.lower() not in lower_answer:
            issues.append(f"missing heading: {heading}")

    if "poh/afm" not in lower_answer:
        issues.append("missing POH/AFM disclaimer")

    if case.expected_procedure and case.expected_procedure.lower() not in lower_answer:
        issues.append("expected procedure name missing from synthesis")

    warnings_pos = lower_answer.find("procedure-specific warnings")
    source_pos = lower_answer.find("source/evidence note")
    if warnings_pos != -1 and source_pos != -1:
        warning_section = lower_answer[warnings_pos:source_pos]
        if "poh/afm" in warning_section:
            issues.append("POH/AFM disclaimer appears inside warnings section")

    if case.case_id == "happy_snow_whiteout":
        if "no procedure-specific warning was retrieved" not in lower_answer:
            issues.append("snow case should state no procedure-specific warning was retrieved")

    if case.case_id == "happy_efato":
        operational_pos = lower_answer.find("operational actions")
        training_pos = lower_answer.find("training/preparation/background notes")
        if operational_pos != -1 and training_pos != -1:
            operational_section = lower_answer[operational_pos:training_pos]
            if "practice turns" in operational_section:
                issues.append("practice turns leaked into operational actions")
        if "practice turns" not in lower_answer:
            issues.append("practice turns training note missing entirely")

    return issues


def evaluate_case(
    module: Any,
    records: dict[str, dict],
    case: EvalCase,
    include_synthesis: bool,
    min_final_score: int,
    max_vector_distance: float,
) -> EvalResult:
    try:
        kg_hits = module.kg_retrieve(case.question, records)
        vector_hits = module.vector_retrieve(case.question, n_results=5)
        candidates = module.merge_candidates(kg_hits, vector_hits, top_k=3)
        top = candidates[0] if candidates else None

        top1 = top["procedure_name"] if top else None
        top3 = [candidate["procedure_name"] for candidate in candidates]
        top1_score = top["final_score"] if top else None
        top1_distance = top["distance"] if top else None
        abstain_decision = should_abstain(top, min_final_score, max_vector_distance)

        if case.expect_abstain:
            retrieval_pass = abstain_decision
        elif case.expected_procedure:
            retrieval_pass = case.expected_procedure == top1
        else:
            retrieval_pass = True

        result = EvalResult(
            case=case,
            top1=top1,
            top3=top3,
            top1_score=top1_score,
            top1_distance=top1_distance,
            retrieval_pass=retrieval_pass,
            abstain_decision=abstain_decision,
        )

        if include_synthesis and case.run_synthesis and not case.expect_abstain:
            answer, model = module.synthesize_answer(case.question, records, candidates[:1])
            issues = check_synthesis(answer, case)
            result.synthesis_model = model
            result.synthesis_issues = issues
            result.synthesis_pass = not issues

        return result
    except Exception as exc:
        return EvalResult(
            case=case,
            top1=None,
            top3=[],
            top1_score=None,
            top1_distance=None,
            retrieval_pass=False,
            abstain_decision=False,
            error=str(exc),
        )


def fmt_bool(value: bool | None) -> str:
    if value is None:
        return "SKIP"
    return "PASS" if value else "FAIL"


def fmt_distance(value: float | None) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return "N/A"


def build_report(
    results: list[EvalResult],
    include_synthesis: bool,
    min_final_score: int,
    max_vector_distance: float,
) -> str:
    retrieval_passes = sum(1 for result in results if result.retrieval_pass)
    synthesis_results = [result for result in results if result.synthesis_pass is not None]
    synthesis_passes = sum(1 for result in synthesis_results if result.synthesis_pass)
    failures = [result for result in results if not result.retrieval_pass or result.synthesis_pass is False or result.error]

    lines = [
        "# Hybrid RAG Evaluation Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Configuration",
        "",
        f"- Cases: `{len(results)}`",
        f"- Include synthesis: `{include_synthesis}`",
        f"- Abstain minimum final score: `{min_final_score}`",
        f"- Abstain maximum vector distance: `{max_vector_distance}`",
        "",
        "## Summary",
        "",
        f"- Retrieval pass: `{retrieval_passes}/{len(results)}`",
        f"- Synthesis pass: `{synthesis_passes}/{len(synthesis_results)}`" if synthesis_results else "- Synthesis pass: `SKIP`",
        f"- Total flagged cases: `{len(failures)}`",
        "",
        "## Results",
        "",
        "| Case | Category | Expected | Top 1 | Top 3 | Score | Distance | Abstain | Retrieval | Synthesis | Notes |",
        "|---|---|---|---|---|---:|---:|---|---|---|---|",
    ]

    for result in results:
        expected = result.case.expected_procedure or ("ABSTAIN" if result.case.expect_abstain else "N/A")
        top3 = "<br>".join(result.top3) if result.top3 else "N/A"
        score = str(result.top1_score) if result.top1_score is not None else "N/A"
        notes = result.case.notes
        if result.error:
            notes = f"ERROR: {result.error}"
        elif result.synthesis_issues:
            notes = "; ".join(result.synthesis_issues)

        lines.append(
            "| "
            f"`{result.case.case_id}` | "
            f"{result.case.category} | "
            f"{expected} | "
            f"{result.top1 or 'N/A'} | "
            f"{top3} | "
            f"{score} | "
            f"{fmt_distance(result.top1_distance)} | "
            f"{'YES' if result.abstain_decision else 'NO'} | "
            f"{fmt_bool(result.retrieval_pass)} | "
            f"{fmt_bool(result.synthesis_pass)} | "
            f"{notes} |"
        )

    if failures:
        lines.extend(["", "## Flagged Cases", ""])
        for result in failures:
            lines.extend([
                f"### `{result.case.case_id}`",
                "",
                f"- Question: `{result.case.question}`",
                f"- Expected: `{result.case.expected_procedure or ('ABSTAIN' if result.case.expect_abstain else 'N/A')}`",
                f"- Top 1: `{result.top1}`",
                f"- Top 3: `{', '.join(result.top3) if result.top3 else 'N/A'}`",
                f"- Score / distance: `{result.top1_score}` / `{fmt_distance(result.top1_distance)}`",
                f"- Retrieval: `{fmt_bool(result.retrieval_pass)}`",
                f"- Synthesis: `{fmt_bool(result.synthesis_pass)}`",
            ])
            if result.synthesis_issues:
                lines.append(f"- Synthesis issues: `{'; '.join(result.synthesis_issues)}`")
            if result.error:
                lines.append(f"- Error: `{result.error}`")
            if result.case.notes:
                lines.append(f"- Notes: {result.case.notes}")
            lines.append("")

    lines.extend([
        "",
        "## Interpretation",
        "",
        "- Happy-path failures usually indicate retrieval regression or stale vector index.",
        "- Out-of-scope failures indicate the system needs an abstention gate before production use.",
        "- Synthesis failures indicate prompt drift or missing KG structure.",
        "",
    ])

    return "\n".join(lines)


def print_console_summary(results: list[EvalResult], report_file: Path) -> None:
    retrieval_passes = sum(1 for result in results if result.retrieval_pass)
    synthesis_results = [result for result in results if result.synthesis_pass is not None]
    synthesis_passes = sum(1 for result in synthesis_results if result.synthesis_pass)

    print("Hybrid RAG evaluation")
    print("-" * 60)
    print(f"Retrieval: {retrieval_passes}/{len(results)}")
    if synthesis_results:
        print(f"Synthesis: {synthesis_passes}/{len(synthesis_results)}")
    else:
        print("Synthesis: SKIP")
    print(f"Report: {report_file}")
    print()

    for result in results:
        status = "PASS" if result.retrieval_pass and result.synthesis_pass is not False and not result.error else "FAIL"
        expected = result.case.expected_procedure or ("ABSTAIN" if result.case.expect_abstain else "N/A")
        print(
            f"{status} {result.case.case_id}: expected={expected} "
            f"top1={result.top1} score={result.top1_score} "
            f"distance={fmt_distance(result.top1_distance)}"
        )
        if result.synthesis_issues:
            print(f"  synthesis issues: {'; '.join(result.synthesis_issues)}")
        if result.error:
            print(f"  error: {result.error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Hybrid RAG retrieval and grounded synthesis")
    parser.add_argument("--include-synthesis", action="store_true", help="Also call the LLM synthesis layer")
    parser.add_argument("--min-final-score", type=int, default=3, help="Abstain below this merged score")
    parser.add_argument("--max-vector-distance", type=float, default=0.62, help="Abstain above this vector distance")
    parser.add_argument("--report-file", default=str(REPORT_FILE), help="Markdown report output path")
    args = parser.parse_args()

    module = load_hybrid_module()
    graph = module.load_kg()
    records = module.load_procedure_records(graph)

    results = [
        evaluate_case(
            module=module,
            records=records,
            case=case,
            include_synthesis=args.include_synthesis,
            min_final_score=args.min_final_score,
            max_vector_distance=args.max_vector_distance,
        )
        for case in EVAL_CASES
    ]

    report = build_report(
        results=results,
        include_synthesis=args.include_synthesis,
        min_final_score=args.min_final_score,
        max_vector_distance=args.max_vector_distance,
    )
    report_file = Path(args.report_file)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(report, encoding="utf-8")

    print_console_summary(results, report_file)

    failed = any(
        (not result.retrieval_pass) or result.synthesis_pass is False or result.error
        for result in results
    )
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
