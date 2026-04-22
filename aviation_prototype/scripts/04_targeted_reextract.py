"""
Step 4: Targeted Re-Extraction
==============================
对少数抽取质量不佳或完全缺失的 source_file 做定点重抽，
并将结果合并回 output/extracted.json，而不重跑整个语料库。

适用场景：
- 某个 procedure 步骤数明显过少
- 某个 source_file 中的 procedure 完全漏抽
- provenance 已接入后，希望用更聚焦的 prompt 修复局部 recall
- 某个 procedure 实际跨多个拆分文件，需要按“分组目标”重抽

使用方法:
    python scripts/04_targeted_reextract.py
    python scripts/04_targeted_reextract.py --targets snow_and_water ballistic
    python scripts/04_targeted_reextract.py --files 33_ballistic_parachutes.txt
    python scripts/04_targeted_reextract.py --dry-run
"""

import argparse
import importlib.util
import json
from pathlib import Path


INPUT_DIR = Path("data/procedures")
SCHEMA_FILE = Path("schema/emergency_schema.yaml")
OUTPUT_FILE = Path("output/extracted.json")

TARGET_SPECS = {
    "snow_and_water": {
        "label": "Snow / Water landing repair",
        "files": ["11_water_ditching_and_snow.txt"],
        "focus": (
            "如果同一文件中同时包含 Water Ditching 和 Snow Landing，应拆成两个 procedure。"
            " Snow Landing 不能只剩一句泛化描述，要把“像 ditching 一样落地”“保持相同构型”"
            " 以及“注意 white out / loss of depth perception”的可执行要点抽出来。"
        ),
        "rename_map": {
            "water landing": "Water Ditching",
            "water landing (ditching)": "Water Ditching",
        },
    },
    "imc_bundle": {
        "label": "IMC control bundle",
        "files": [
            "24_inadvertent_vfr_flight_into_imc.txt",
            "25_maintaining_airplane_control.txt",
            "26_attitude_control.txt",
            "27_turns.txt",
            "28_climbs.txt",
            "29_descents.txt",
            "30_combined_maneuvers.txt",
            "31_transition_to_visual_flight.txt",
        ],
        "focus": (
            "这些文件共同描述同一个高价值 procedure：Inadvertent VFR Flight Into IMC。"
            " 请优先输出一个主 procedure，而不是按子标题拆成多个独立 procedure。"
            " 需要覆盖：识别紧急情况、保持飞机控制、trim / attitude indicator、浅坡度转弯、"
            " 爬升、下降、避免组合机动、向视觉飞行过渡、必要时请求 ATC 协助。"
        ),
        "preferred_name": "Inadvertent VFR Flight Into IMC",
        "force_merged_source_files": True,
    },
    "ballistic": {
        "label": "Ballistic parachute recovery",
        "files": ["33_ballistic_parachutes.txt"],
        "focus": (
            "如果文本描述了部署条件、乘客 brief、部署动作和落地后的撤离风险，"
            "应整理成可执行 procedure，不要因为原文偏说明性就完全漏抽。"
        ),
        "rename_map": {
            "ballistic parachute deployment procedures": "Ballistic Parachute Deployment",
        },
    },
}
DEFAULT_TARGETS = list(TARGET_SPECS.keys())


def load_extract_module():
    """动态加载 01_extract.py，复用其 provider / provenance / normalize 逻辑。"""
    script_path = Path(__file__).with_name("01_extract.py")
    spec = importlib.util.spec_from_file_location("extract_script", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_source_texts(file_paths: list[Path]) -> dict[str, str]:
    """读取目标文件文本。"""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in file_paths
    }


def build_combined_text(file_paths: list[Path]) -> str:
    """将多个文件拼成单次重抽的输入文本。"""
    parts = []
    for idx, path in enumerate(file_paths, start=1):
        text = path.read_text(encoding="utf-8").strip()
        parts.append(f"[文档 {idx}: {path.name}]\n{text}")
    return "\n\n" + ("\n\n" + ("-" * 60) + "\n\n").join(parts)


def build_targeted_prompt(
    text: str,
    schema_desc: str,
    source_files: list[str],
    target_label: str,
    focus: str = "",
) -> str:
    """构建更偏 recall 的局部重抽 prompt。"""
    file_scope = "、".join(source_files)
    source_file_rule = (
        f"7. source_file 必须是以下文件之一，或它们的 ` | ` 合并值：{file_scope}。"
        if len(source_files) > 1
        else f"7. source_file 必须填写 `{source_files[0]}`。"
    )

    grouping_rule = (
        "8. 如果多个文件共同描述同一个 procedure，应合并成一个主 procedure，"
        "而不是机械按小节标题拆散。"
        if len(source_files) > 1
        else "8. 如果同一 source_file 中明显包含两个 procedure（例如 Water + Snow），要拆成两个。"
    )

    return f"""你是一个航空应急程序抽取专家。现在只处理目标 `{target_label}`。

目标：
从下面 FAA 文本中尽可能完整地提取“真正可执行”的 emergency / abnormal procedure。

{schema_desc}

严格要求：
1. 只输出 JSON，不要解释。
2. 如果一个段落包含明确的执行动作、控制策略、应对步骤、训练步骤或处置步骤，就应抽成 procedure。
3. 不要因为段落里带有解释性文字就放弃抽取；很多 FAA procedure 是“说明 + 步骤”混合写法。
4. 对于步骤，优先提取原文中明确的动作、目标动作、控制动作、注意事项对应的可执行 action。
5. 每个 step 必须有：
   - step_number
   - step_type（immediate_action / training_note / caution / background 之一）
   - action
   - source_excerpt
6. 每个 procedure 必须有：
   - name
   - source_file
   - source_section
   - source_excerpt
{source_file_rule}
{grouping_rule}
9. 如果文本中出现“first steps are...”之类的列表，必须完整保留这些步骤，不要只抽 1-3 条。
10. 不要凭空编造 POH 中不存在的步骤；但可以把原文动作改写成简洁祈使句。
11. 如果某段真的完全没有可执行步骤，就不要输出该 procedure。

特别提醒：
{focus or "尽量保留 FAA 原文中的核心控制动作和可执行要点。"}

文本内容：
---
{text}
---

请输出 JSON："""


def request_targeted_extraction(module, prompt: str) -> tuple[list[dict], str]:
    """调用 LLM 做定点重抽，返回 procedures 和 provider。"""
    client, model, provider = module.create_llm_client()
    request_kwargs = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是航空应急程序抽取专家。输出严格 JSON，并优先保证可执行步骤完整。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.0,
    }

    if provider == "openai":
        request_kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**request_kwargs)
    raw_json = response.choices[0].message.content
    extracted = module.parse_json_response(raw_json)
    return extracted.get("procedures", []), provider


def best_source_match(module, source_text_by_file: dict[str, str], query: str) -> tuple[str, str]:
    """在多个来源文件里为 query 找最佳摘录和对应文件。"""
    query = module.clean_text(query)
    if not source_text_by_file:
        return "", ""

    if not query:
        first_file = next(iter(source_text_by_file))
        first_excerpt = module.best_matching_excerpt(source_text_by_file[first_file], "")
        return first_file, first_excerpt

    query_keywords = module.extract_keywords(query)
    best_file = next(iter(source_text_by_file))
    best_excerpt = ""
    best_score = -1

    for file_name, source_text in source_text_by_file.items():
        excerpt = module.best_matching_excerpt(source_text, query)
        excerpt_keywords = module.extract_keywords(excerpt)
        source_keywords = module.extract_keywords(source_text)
        score = (len(query_keywords & excerpt_keywords) * 10) + len(query_keywords & source_keywords)
        if score > best_score or (score == best_score and len(excerpt) > len(best_excerpt)):
            best_file = file_name
            best_excerpt = excerpt
            best_score = score

    return best_file, best_excerpt


def attach_targeted_provenance(module, procedures: list[dict], source_text_by_file: dict[str, str]) -> list[dict]:
    """
    为定点重抽结果补 provenance。

    和 01_extract.py 中的 attach_provenance 不同，这里允许一个 procedure
    覆盖多个文件，因此 step 的摘录会在全部候选文件中匹配，再把 procedure 的
    source_file 合并成 `a.txt | b.txt` 形式。
    """
    attached = []
    available_files = list(source_text_by_file.keys())

    for proc in procedures:
        proc = dict(proc)
        proc["name"] = module.clean_text(proc.get("name"))
        proc["trigger_condition"] = module.clean_text(proc.get("trigger_condition"))
        proc["aircraft_phase"] = module.clean_text(proc.get("aircraft_phase"))
        proc["source_section"] = module.clean_text(proc.get("source_section")) or proc["name"]

        matched_files = []
        hydrated_steps = []
        for step in proc.get("steps") or []:
            step = dict(step)
            step["action"] = module.clean_text(step.get("action"))
            if not step["action"]:
                continue

            query = module.clean_text(step.get("source_excerpt")) or step["action"]
            step_file, step_excerpt = best_source_match(module, source_text_by_file, query)
            if step_file:
                matched_files.append(step_file)
                step["source_file"] = step_file
            step["source_excerpt"] = module.clean_text(step.get("source_excerpt")) or step_excerpt
            hydrated_steps.append(step)

        proc_query_parts = [
            proc.get("source_section"),
            proc.get("name"),
            proc.get("trigger_condition"),
            " ".join(step.get("action", "") for step in hydrated_steps),
        ]
        proc_query = " ".join(part for part in proc_query_parts if part)
        proc_file, proc_excerpt = best_source_match(module, source_text_by_file, proc_query)
        if proc_file:
            matched_files.append(proc_file)

        raw_source_file = module.clean_source_file(proc.get("source_file"))
        if raw_source_file:
            for token in [part.strip() for part in raw_source_file.split("|")]:
                if token in available_files:
                    matched_files.append(token)

        if not matched_files and len(available_files) == 1:
            matched_files = available_files[:]

        proc["source_file"] = module.merge_source_files(matched_files)
        proc["source_excerpt"] = module.clean_text(proc.get("source_excerpt")) or proc_excerpt
        proc["steps"] = hydrated_steps
        attached.append(proc)

    return attached


def run_target_spec(module, spec_name: str, spec: dict) -> tuple[list[dict], list[str]]:
    """执行一个命名目标或分组目标。"""
    source_files = spec["files"]
    file_paths = [INPUT_DIR / file_name for file_name in source_files]
    missing = [str(path) for path in file_paths if not path.exists()]
    if missing:
        missing_str = "\n".join(missing)
        raise FileNotFoundError(f"未找到以下目标文件:\n{missing_str}")

    schema_desc = module.load_schema_description(str(SCHEMA_FILE))
    source_text_by_file = read_source_texts(file_paths)
    input_text = build_combined_text(file_paths)
    prompt = build_targeted_prompt(
        input_text,
        schema_desc,
        source_files,
        spec.get("label", spec_name),
        spec.get("focus", ""),
    )
    procedures, provider = request_targeted_extraction(module, prompt)

    preferred_name = spec.get("preferred_name")
    if preferred_name:
        for proc in procedures:
            proc["name"] = preferred_name

    procedures = attach_targeted_provenance(module, procedures, source_text_by_file)
    procedures = apply_name_overrides(module, procedures, spec.get("rename_map", {}))
    procedures = module.normalize_procedures(procedures)

    if spec.get("force_merged_source_files"):
        merged_source_files = module.merge_source_files(source_files)
        for proc in procedures:
            proc["source_file"] = merged_source_files

    print(f"🎯 定点重抽: {spec_name}")
    print(f"   provider: {provider}")
    print(f"   覆盖文件: {', '.join(source_files)}")
    print(f"   抽取到 {len(procedures)} 个 procedure")
    for proc in procedures:
        print(f"   • {proc.get('name')} ({len(proc.get('steps') or [])} steps)")
    print()

    return procedures, source_files


def build_file_spec(file_name: str) -> dict:
    """将 --files 里的裸文件名包装成单文件目标。"""
    return {
        "label": file_name,
        "files": [file_name],
        "focus": "",
        "rename_map": {},
    }


def apply_name_overrides(module, procedures: list[dict], rename_map: dict[str, str]) -> list[dict]:
    """按规范名修正少量可预测的标题漂移。"""
    if not rename_map:
        return procedures

    normalized_map = {
        module.canonical_text_key(key): value
        for key, value in rename_map.items()
    }

    updated = []
    for proc in procedures:
        proc = dict(proc)
        key = module.canonical_text_key(proc.get("name"))
        if key in normalized_map:
            proc["name"] = normalized_map[key]
        updated.append(proc)
    return updated


def procedure_source_files(proc: dict) -> set[str]:
    """把 procedure 的 source_file 拆成文件集合。"""
    raw = proc.get("source_file") or ""
    return {
        token.strip()
        for token in raw.split("|")
        if token.strip()
    }


def merge_targeted_results(existing: list[dict], target_files: list[str], replacements: list[dict]) -> list[dict]:
    """将目标文件覆盖到现有 extracted.json。"""
    target_set = set(target_files)
    preserved = [
        proc for proc in existing
        if procedure_source_files(proc).isdisjoint(target_set)
    ]
    return preserved + replacements


def main():
    parser = argparse.ArgumentParser(description="对指定 source_file / 文件分组做定点重抽并合并到 extracted.json")
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=sorted(TARGET_SPECS.keys()),
        default=DEFAULT_TARGETS,
        help="要执行的内置目标名"
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="额外按单文件执行的 source_file 文件名列表"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印结果，不写回 extracted.json"
    )
    args = parser.parse_args()

    module = load_extract_module()

    if not OUTPUT_FILE.exists():
        raise FileNotFoundError(f"未找到现有提取结果: {OUTPUT_FILE}")

    existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    existing_procedures = existing.get("procedures", [])

    replacements = []
    touched_files = []

    for spec_name in args.targets:
        procedures, files = run_target_spec(module, spec_name, TARGET_SPECS[spec_name])
        replacements.extend(procedures)
        touched_files.extend(files)

    for file_name in args.files:
        procedures, files = run_target_spec(module, file_name, build_file_spec(file_name))
        replacements.extend(procedures)
        touched_files.extend(files)

    merged_procedures = merge_targeted_results(existing_procedures, touched_files, replacements)
    merged_procedures = module.normalize_procedures(merged_procedures)

    print(f"📦 合并后 procedure 总数: {len(merged_procedures)}")

    if args.dry_run:
        print("🧪 dry-run 模式，不写回 output/extracted.json")
        return

    existing["procedures"] = merged_procedures
    OUTPUT_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾 已写回: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
