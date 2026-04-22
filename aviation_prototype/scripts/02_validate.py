"""
Step 2: SHACL Validation
========================
将提取结果转换为 RDF 知识图谱，然后用 SHACL 验证数据质量。

流程:
    output/extracted.json
        → RDF 图谱 (rdflib)
        → SHACL 验证 (pyshacl)
        → output/kg.ttl          (存储的图谱)
        → output/validation_report.txt

使用方法:
    python scripts/02_validate.py
"""

import json
import sys
from pathlib import Path
from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import RDF, XSD
from pyshacl import validate

# Windows GBK 终端兼容
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "cp936", "gb2312"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── 配置 ────────────────────────────────────────────────────────
EXTRACTED_FILE  = "output/extracted.json"
SHACL_FILE      = "shacl/procedure_shapes.ttl"
KG_OUTPUT       = "output/kg.ttl"
REPORT_OUTPUT   = "output/validation_report.txt"

# 定义命名空间（和 SHACL shapes 保持一致）
AV = Namespace("https://example.org/aviation/")

VALID_STEP_TYPES = {"immediate_action", "training_note", "caution", "background"}
TRAINING_NOTE_PATTERNS = (
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
CAUTION_PATTERNS = (
    "do not",
    "should not",
    "must not",
    "warning",
    "caution",
    "hazard",
    "risk",
)


def normalize_step_type(value: str | None) -> str:
    """Normalize model output to the controlled StepType vocabulary."""
    if not value:
        return ""
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in VALID_STEP_TYPES else ""


def infer_step_type(step: dict) -> str:
    """
    Conservative fallback for legacy extracted.json files.

    Most extracted steps are operational actions. Only classify as training_note
    or caution when the text carries strong lexical evidence.
    """
    explicit = normalize_step_type(step.get("step_type"))
    if explicit:
        return explicit

    text = " ".join(
        str(step.get(field) or "")
        for field in ("action", "expected_result", "source_excerpt")
    ).lower()

    if any(pattern in text for pattern in TRAINING_NOTE_PATTERNS):
        return "training_note"
    if any(pattern in text for pattern in CAUTION_PATTERNS):
        return "caution"
    return "immediate_action"


def json_to_rdf(extracted: dict) -> Graph:
    """
    将提取的 JSON 转换为 RDF 图谱。

    核心思路：
    - 每个 EmergencyProcedure → 一个 URI 节点
    - 每个 ProcedureStep      → 一个 blank node，挂在 procedure 下
    - 每个 Warning            → 一个 blank node，挂在 procedure 下
    """
    g = Graph()
    g.bind("av", AV)
    g.bind("xsd", XSD)

    procedures = extracted.get("procedures", [])

    for i, proc in enumerate(procedures):
        # 为每个 procedure 创建 URI
        # 例如: av:procedure_0, av:procedure_1
        safe_name = proc.get("name", f"procedure_{i}") \
                        .replace(" ", "_") \
                        .replace("/", "_") \
                        .lower()
        proc_uri = AV[f"proc_{i}_{safe_name[:20]}"]

        # 声明类型
        g.add((proc_uri, RDF.type, AV.EmergencyProcedure))

        # 添加名称
        if proc.get("name"):
            g.add((proc_uri, AV.name, Literal(proc["name"], datatype=XSD.string)))

        # 添加触发条件
        if proc.get("trigger_condition"):
            g.add((proc_uri, AV.trigger_condition,
                   Literal(proc["trigger_condition"], datatype=XSD.string)))

        # 添加飞行阶段
        if proc.get("aircraft_phase"):
            g.add((proc_uri, AV.aircraft_phase,
                   Literal(proc["aircraft_phase"], datatype=XSD.string)))

        # 添加来源信息
        if proc.get("source_file"):
            g.add((proc_uri, AV.source_file,
                   Literal(proc["source_file"], datatype=XSD.string)))

        if proc.get("source_section"):
            g.add((proc_uri, AV.source_section,
                   Literal(proc["source_section"], datatype=XSD.string)))

        if proc.get("source_excerpt"):
            g.add((proc_uri, AV.source_excerpt,
                   Literal(proc["source_excerpt"], datatype=XSD.string)))

        # 添加步骤
        for step in proc.get("steps", []):
            step_node = BNode()   # 匿名节点
            g.add((step_node, RDF.type, AV.ProcedureStep))
            g.add((proc_uri, AV.hasStep, step_node))

            if step.get("step_number") is not None:
                g.add((step_node, AV.step_number,
                       Literal(int(step["step_number"]), datatype=XSD.integer)))

            g.add((step_node, AV.step_type,
                   Literal(infer_step_type(step), datatype=XSD.string)))

            if step.get("action"):
                g.add((step_node, AV.action,
                       Literal(step["action"], datatype=XSD.string)))

            if step.get("expected_result"):
                g.add((step_node, AV.expected_result,
                       Literal(step["expected_result"], datatype=XSD.string)))

            if step.get("source_excerpt"):
                g.add((step_node, AV.source_excerpt,
                       Literal(step["source_excerpt"], datatype=XSD.string)))

        # 添加警告
        for warning in proc.get("warnings", []):
            warn_node = BNode()
            g.add((warn_node, RDF.type, AV.Warning))
            g.add((proc_uri, AV.hasWarning, warn_node))

            desc = warning.get("description", "")
            if desc:
                g.add((warn_node, AV.description,
                       Literal(desc, datatype=XSD.string)))

    return g


def run_shacl_validation(kg: Graph, shacl_file: str):
    """
    运行 SHACL 验证。
    返回: (通过?, 结果图, 报告文本)
    """
    shacl_graph = Graph()
    shacl_graph.parse(shacl_file, format="turtle")

    conforms, results_graph, results_text = validate(
        data_graph=kg,
        shacl_graph=shacl_graph,
        inference="rdfs",   # 启用 RDFS 推理
        abort_on_first=False,  # 找出所有问题，不在第一个错误停止
    )
    return conforms, results_graph, results_text


def print_validation_summary(kg: Graph, conforms: bool, results_text: str):
    """打印可读的验证摘要"""

    # 统计图谱内容
    n_procedures = len(list(kg.subjects(RDF.type, AV.EmergencyProcedure)))
    n_steps      = len(list(kg.subjects(RDF.type, AV.ProcedureStep)))
    n_warnings   = len(list(kg.subjects(RDF.type, AV.Warning)))
    n_triples    = len(kg)
    step_type_counts = {}
    for step_type in kg.objects(None, AV.step_type):
        label = str(step_type)
        step_type_counts[label] = step_type_counts.get(label, 0) + 1

    print("\n" + "="*55)
    print("📊 知识图谱统计")
    print("="*55)
    print(f"  RDF 三元组总数:  {n_triples}")
    print(f"  紧急程序数量:    {n_procedures}")
    print(f"  步骤总数:        {n_steps}")
    print(f"  警告总数:        {n_warnings}")
    if step_type_counts:
        print("  步骤类型:")
        for label in sorted(step_type_counts):
            print(f"    - {label}: {step_type_counts[label]}")

    print("\n" + "="*55)
    print("🔍 SHACL 验证结果")
    print("="*55)

    if conforms:
        print("  ✅ PASS — 所有数据满足约束条件")
        print("  知识图谱已通过验证，可以进入 AI advisor 查询层")
    else:
        print("  ❌ FAIL — 发现约束违规")
        print("  以下数据问题会阻止其进入 AI advisor:\n")

        # 解析失败信息
        for line in results_text.split("\n"):
            if "Constraint Violation" in line or "sh:message" in line \
               or "sh:resultMessage" in line or "Severity" in line:
                print(f"  {line.strip()}")

    print("="*55)


if __name__ == "__main__":
    print("🔄 Step 2: SHACL 验证")
    print("-"*55)

    # 检查提取结果存在
    if not Path(EXTRACTED_FILE).exists():
        print(f"❌ 未找到提取结果文件: {EXTRACTED_FILE}")
        print("   请先运行 python scripts/01_extract.py")
        sys.exit(1)

    # 读取提取结果
    print(f"📂 读取提取结果: {EXTRACTED_FILE}")
    with open(EXTRACTED_FILE, encoding="utf-8") as f:
        extracted = json.load(f)

    # 转换为 RDF
    print("🔗 将 JSON 转换为 RDF 知识图谱...")
    kg = json_to_rdf(extracted)

    # 保存 KG
    Path(KG_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    kg.serialize(destination=KG_OUTPUT, format="turtle")
    print(f"💾 知识图谱已保存到: {KG_OUTPUT}")

    # 运行 SHACL 验证
    print(f"✅ 运行 SHACL 验证 (shapes: {SHACL_FILE})...")
    conforms, results_graph, results_text = run_shacl_validation(kg, SHACL_FILE)

    # 打印摘要
    print_validation_summary(kg, conforms, results_text)

    # 保存验证报告
    with open(REPORT_OUTPUT, "w", encoding="utf-8") as f:
        f.write(f"SHACL Validation Report\n{'='*40}\n")
        f.write(f"Conforms: {conforms}\n\n")
        f.write(results_text)
    print(f"\n📄 完整验证报告: {REPORT_OUTPUT}")

    if not conforms:
        print("\n⚠️  请修复数据问题后再进行下一步")
        sys.exit(1)
    else:
        print("\n→ 下一步: python scripts/03_query.py")
