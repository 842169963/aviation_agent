"""
Step 3: Query the Knowledge Graph
==================================
从已验证的知识图谱中检索信息，模拟 AI advisor 的查询层。

这是整个流水线的终点：飞行员提问 → 系统从 KG 检索 → 返回步骤

使用方法:
    python scripts/03_query.py
    python scripts/03_query.py --question "发动机失效怎么办"
"""

import argparse
import sys
from pathlib import Path
from rdflib import Graph, Namespace
from rdflib.namespace import RDF, XSD

# Windows GBK 终端兼容
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "cp936", "gb2312"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── 配置 ────────────────────────────────────────────────────────
KG_FILE = "output/kg.ttl"
AV = Namespace("https://example.org/aviation/")


def load_kg(kg_file: str) -> Graph:
    """加载知识图谱"""
    g = Graph()
    g.bind("av", AV)
    g.parse(kg_file, format="turtle")
    return g


def list_all_procedures(g: Graph):
    """列出图谱中所有紧急程序"""
    query = """
    PREFIX av: <https://example.org/aviation/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    SELECT ?proc ?name ?trigger ?source_file ?source_section WHERE {
        ?proc a av:EmergencyProcedure ;
              av:name ?name .
        OPTIONAL { ?proc av:trigger_condition ?trigger . }
        OPTIONAL { ?proc av:source_file ?source_file . }
        OPTIONAL { ?proc av:source_section ?source_section . }
    }
    ORDER BY ?name
    """
    return g.query(query)


def get_procedure_steps(g: Graph, procedure_name_keyword: str):
    """
    按名称关键字检索程序的所有步骤。
    模拟飞行员问: "发动机失效怎么办？"
    """
    query = """
    PREFIX av: <https://example.org/aviation/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    SELECT ?name ?trigger ?source_file ?source_section ?proc_excerpt ?step_num ?action ?expected_result ?step_excerpt WHERE {
        ?proc a av:EmergencyProcedure ;
              av:name ?name ;
              av:hasStep ?step .
        ?step av:step_number ?step_num ;
              av:action ?action .
        OPTIONAL { ?proc av:trigger_condition ?trigger . }
        OPTIONAL { ?proc av:source_file ?source_file . }
        OPTIONAL { ?proc av:source_section ?source_section . }
        OPTIONAL { ?proc av:source_excerpt ?proc_excerpt . }
        OPTIONAL { ?step av:expected_result ?expected_result . }
        OPTIONAL { ?step av:source_excerpt ?step_excerpt . }

        FILTER(CONTAINS(LCASE(STR(?name)), LCASE("%s")))
    }
    ORDER BY ?name ?step_num
    """ % procedure_name_keyword

    return g.query(query)


def get_procedure_warnings(g: Graph, procedure_name_keyword: str):
    """检索程序的安全警告"""
    query = """
    PREFIX av: <https://example.org/aviation/>

    SELECT ?name ?warning_desc WHERE {
        ?proc a av:EmergencyProcedure ;
              av:name ?name ;
              av:hasWarning ?warn .
        ?warn av:description ?warning_desc .

        FILTER(CONTAINS(LCASE(STR(?name)), LCASE("%s")))
    }
    ORDER BY ?name
    """ % procedure_name_keyword

    return g.query(query)


def format_advisory_response(steps_results, warnings_results, keyword: str):
    """
    将 SPARQL 查询结果格式化为飞行员友好的建议输出。
    这模拟了 AI advisor 的最终输出层。
    """
    # 整理步骤
    procedures = {}
    for row in steps_results:
        name = str(row.name)
        if name not in procedures:
            procedures[name] = {
                "trigger": str(row.trigger) if row.trigger else "N/A",
                "source_file": str(row.source_file) if row.source_file else None,
                "source_section": str(row.source_section) if row.source_section else None,
                "proc_excerpt": str(row.proc_excerpt) if row.proc_excerpt else None,
                "steps": []
            }
        step = {
            "num": int(row.step_num),
            "action": str(row.action),
            "result": str(row.expected_result) if row.expected_result else None,
            "source_excerpt": str(row.step_excerpt) if row.step_excerpt else None,
        }
        procedures[name]["steps"].append(step)

    # 整理警告
    warnings = {}
    for row in warnings_results:
        name = str(row.name)
        if name not in warnings:
            warnings[name] = []
        warnings[name].append(str(row.warning_desc))

    if not procedures:
        print(f"\n❌ 未找到与 '{keyword}' 相关的程序")
        print("   可用程序请运行: python scripts/03_query.py --list")
        return

    # 输出格式化建议
    print("\n" + "="*60)
    print("✈️  AVIATION ADVISORY SYSTEM — 查询结果")
    print("="*60)

    for proc_name, data in procedures.items():
        print(f"\n📋 程序: {proc_name}")
        print(f"   触发条件: {data['trigger']}")
        if data.get("source_file"):
            print(f"   来源文件: {data['source_file']}")
        if data.get("source_section"):
            print(f"   来源章节: {data['source_section']}")
        if data.get("proc_excerpt"):
            display = data["proc_excerpt"] if len(data["proc_excerpt"]) <= 140 else data["proc_excerpt"][:140] + "..."
            print(f"   程序依据: {display}")
        print(f"\n   立即执行以下步骤:")
        print("   " + "-"*40)

        # 按步骤编号排序
        sorted_steps = sorted(data["steps"], key=lambda x: x["num"])
        for step in sorted_steps:
            print(f"\n   [{step['num']}] {step['action']}")
            if step["result"]:
                print(f"       → 预期结果: {step['result']}")
            if step.get("source_excerpt"):
                display = step["source_excerpt"] if len(step["source_excerpt"]) <= 140 else step["source_excerpt"][:140] + "..."
                print(f"       → 依据: {display}")

        # 显示警告
        if proc_name in warnings and warnings[proc_name]:
            print(f"\n   ⚠️  安全警告:")
            for w in warnings[proc_name]:
                print(f"   {'─'*40}")
                # 截断过长的警告显示
                display = w if len(w) <= 120 else w[:120] + "..."
                print(f"   {display}")

    print("\n" + "="*60)
    print("ℹ️  以上建议来自已验证的 FAA 知识图谱")
    print("   始终以飞行员判断和实际 POH 为准")
    print("="*60)


def run_interactive_query(g: Graph):
    """简单的交互式查询界面"""
    print("\n✈️  Aviation Advisory — 交互式查询")
    print("   输入关键词查询程序，输入 'quit' 退出\n")

    while True:
        keyword = input("请输入查询关键词 (例如: engine, takeoff, cruise): ").strip()
        if keyword.lower() in ("quit", "exit", "q"):
            print("退出。")
            break
        if not keyword:
            continue

        steps = get_procedure_steps(g, keyword)
        warnings = get_procedure_warnings(g, keyword)
        format_advisory_response(steps, warnings, keyword)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="查询航空知识图谱")
    parser.add_argument("--question", "-q", help="查询关键词 (例如: 'engine failure')")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用程序")
    parser.add_argument("--interactive", "-i", action="store_true", help="启动交互式查询")
    args = parser.parse_args()

    # 检查 KG 文件
    if not Path(KG_FILE).exists():
        print(f"❌ 未找到知识图谱: {KG_FILE}")
        print("   请先运行:")
        print("   python scripts/01_extract.py")
        print("   python scripts/02_validate.py")
        sys.exit(1)

    print(f"📂 加载知识图谱: {KG_FILE}")
    g = load_kg(KG_FILE)
    print(f"   三元组数量: {len(g)}")

    if args.list:
        # 列出所有程序
        print("\n📋 图谱中的所有紧急程序:")
        print("-"*50)
        for row in list_all_procedures(g):
            print(f"  • {row.name}")
            if row.trigger:
                print(f"    触发: {row.trigger}")
            if row.source_file:
                print(f"    文件: {row.source_file}")
            if row.source_section:
                print(f"    章节: {row.source_section}")

    elif args.interactive:
        run_interactive_query(g)

    elif args.question:
        steps = get_procedure_steps(g, args.question)
        warnings = get_procedure_warnings(g, args.question)
        format_advisory_response(steps, warnings, args.question)

    else:
        # 默认：运行演示查询
        print("\n🔍 演示查询: 'engine' 相关程序")
        steps = get_procedure_steps(g, "engine")
        warnings = get_procedure_warnings(g, "engine")
        format_advisory_response(steps, warnings, "engine")

        print("\n💡 使用方法:")
        print("   python scripts/03_query.py --question 'takeoff'")
        print("   python scripts/03_query.py --list")
        print("   python scripts/03_query.py --interactive")
