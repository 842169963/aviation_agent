"""
Step 1: Knowledge Extraction
============================
从航空手册文本中提取结构化知识。

流程:
    原始 FAA 文本
        → LLM (OpenAI / Gemini, 按 LinkML schema 结构提取)
        → output/extracted.json  (结构化 JSON)

使用方法:
    # 单文件模式（原有）
    python scripts/01_extract.py
    python scripts/01_extract.py --input data/my_other_text.txt

    # 批量模式（处理 00_pdf_parse.py 生成的程序文件）
    python scripts/01_extract.py --input-dir data/procedures
"""

import os
import json
import argparse
import sys
import time
import re
import yaml
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Windows GBK 终端兼容
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "cp936", "gb2312"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

# ── 配置 ────────────────────────────────────────────────────────
INPUT_FILE  = "data/efato_sample.txt"
SCHEMA_FILE = "schema/emergency_schema.yaml"
OUTPUT_FILE = "output/extracted.json"
OPENAI_MODEL = "gpt-4o-mini"
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip()
GEMINI_BATCH_DELAY_SECONDS = float(os.getenv("GEMINI_BATCH_DELAY_SECONDS", "13"))
MAX_RATE_LIMIT_RETRIES = int(os.getenv("MAX_RATE_LIMIT_RETRIES", "5"))
OPENAI_BATCH_FILES_PER_REQUEST = int(os.getenv("OPENAI_BATCH_FILES_PER_REQUEST", "1"))
GEMINI_BATCH_FILES_PER_REQUEST = int(os.getenv("GEMINI_BATCH_FILES_PER_REQUEST", "5"))


def load_schema_description(schema_path: str) -> str:
    """读取 LinkML schema，转成给 LLM 看的说明文字"""
    with open(schema_path, encoding="utf-8") as f:
        schema = yaml.safe_load(f)

    # 提取类和字段描述
    classes = schema.get("classes", {})
    desc_lines = ["目标 JSON 结构（严格按照以下 schema）:\n"]

    for cls_name, cls_def in classes.items():
        if cls_def is None:
            continue
        desc_lines.append(f"类 {cls_name}:")
        attrs = cls_def.get("attributes", {})
        if attrs:
            for attr_name, attr_def in attrs.items():
                if attr_def is None:
                    attr_def = {}
                req = " [必填]" if attr_def.get("required") else ""
                multi = " [列表]" if attr_def.get("multivalued") else ""
                desc = attr_def.get("description", "")
                desc_lines.append(f"  - {attr_name}{req}{multi}: {desc}")
        desc_lines.append("")

    enums = schema.get("enums", {})
    if enums:
        desc_lines.append("枚举值:")
        for enum_name, enum_def in enums.items():
            desc_lines.append(f"枚举 {enum_name}:")
            values = (enum_def or {}).get("permissible_values", {})
            for value, value_def in values.items():
                desc = (value_def or {}).get("description", "")
                desc_lines.append(f"  - {value}: {desc}")
            desc_lines.append("")

    return "\n".join(desc_lines)


def build_prompt(text: str, schema_desc: str) -> str:
    """构建提取 prompt"""
    return f"""你是一个航空知识提取专家。请从下面的航空手册文本中，提取所有的紧急程序（Emergency Procedures）。

{schema_desc}

要求：
1. 严格按照上面的 JSON 结构输出
2. 每个步骤必须有 step_number（从1开始）和 action
3. 警告（warnings）单独提取，不要混入步骤
4. 如果文本中有多个程序，全部提取到 procedures 列表中
5. action 使用祈使句，简洁清晰（例如："Lower nose to maintain 65 KIAS"）
6. 只输出 JSON，不要任何解释文字
7. 每个 procedure 必须包含 provenance：
   - source_file：来源文件名
   - source_section：来源标题或小节名
   - source_excerpt：支持该 procedure 的简短原文摘录
8. 每个 step 必须包含 source_excerpt，表示这一步对应的原文依据
9. source_excerpt 应尽量贴近原文，可做轻微清理，但不要编造
10. 每个 step 必须包含 step_type，取值只能是：
    - immediate_action：应急/异常处置中要执行的动作
    - training_note：训练、乘客 brief、练习、预先学习或准备事项
    - caution：风险控制、禁止事项或注意事项
    - background：解释性背景，不是直接动作
11. 如果文本只是说明性介绍，没有明确可执行步骤，不要硬造 procedure

文本内容：
---
{text}
---

请输出 JSON："""


def create_llm_client() -> tuple[OpenAI, str, str]:
    """
    创建 LLM 客户端。

    支持两种 provider：
    - OpenAI: 读取 OPENAI_API_KEY
    - Gemini: 读取 GEMINI_API_KEY，并通过 Gemini 的 OpenAI 兼容接口访问

    选择规则：
    1. 如果设置了 LLM_PROVIDER，则按显式配置选择
    2. 否则优先使用 OPENAI_API_KEY
    3. 如果没有 OpenAI key，则回退到 GEMINI_API_KEY
    """
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    model_override = os.getenv("MODEL_NAME", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if provider and provider not in {"openai", "gemini"}:
        raise ValueError("LLM_PROVIDER 仅支持 'openai' 或 'gemini'")

    if provider == "gemini" or (not provider and gemini_key and not openai_key):
        if not gemini_key:
            raise ValueError("未找到 GEMINI_API_KEY。请在 .env 文件中设置。")
        return (
            OpenAI(api_key=gemini_key, base_url=GEMINI_OPENAI_BASE_URL),
            model_override or GEMINI_MODEL,
            "gemini",
        )

    if provider == "openai" or openai_key:
        if not openai_key:
            raise ValueError("未找到 OPENAI_API_KEY。请在 .env 文件中设置。")
        client_kwargs = {"api_key": openai_key}
        if OPENAI_BASE_URL:
            client_kwargs["base_url"] = OPENAI_BASE_URL
        return OpenAI(**client_kwargs), model_override or OPENAI_MODEL, "openai"

    raise ValueError("未找到可用的 API Key。请设置 OPENAI_API_KEY 或 GEMINI_API_KEY。")


def parse_json_response(raw_text: str) -> dict:
    """从模型返回文本中提取 JSON。"""
    cleaned = raw_text.strip()

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
        cleaned = cleaned[start:end + 1]

    return json.loads(cleaned)


def usage_totals(usage) -> tuple[int, int, int]:
    """兼容不同 provider 的 usage 对象。"""
    if usage is None:
        return 0, 0, 0

    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    total_tokens = getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
    return prompt_tokens, completion_tokens, total_tokens


def clean_text(value: str | None) -> str:
    """清理字符串中的多余空白。"""
    if not value:
        return ""
    return " ".join(str(value).split()).strip()


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
    normalized = clean_text(value).lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in VALID_STEP_TYPES else ""


def infer_step_type(step: dict) -> str:
    """Fallback classifier for extracted steps that lack step_type."""
    explicit = normalize_step_type(step.get("step_type"))
    if explicit:
        return explicit

    text = " ".join(
        clean_text(step.get(field)).lower()
        for field in ("action", "expected_result", "source_excerpt")
    )
    if any(pattern in text for pattern in TRAINING_NOTE_PATTERNS):
        return "training_note"
    if any(pattern in text for pattern in CAUTION_PATTERNS):
        return "caution"
    return "immediate_action"


def clean_source_file(value: str | None) -> str:
    """标准化来源文件名。"""
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    cleaned = cleaned.replace("\\", "/")
    return cleaned.split("/")[-1]


def canonical_text_key(value: str | None) -> str:
    """生成大小写不敏感、弱标点敏感的比较键。"""
    cleaned = clean_text(value).lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


def extract_keywords(value: str | None) -> set[str]:
    """从文本中提取用于粗匹配的关键词。"""
    cleaned = canonical_text_key(value)
    return {token for token in cleaned.split() if len(token) >= 4}


def merge_trigger_conditions(trigger_conditions: list[str]) -> str:
    """合并多个 trigger_condition，尽量保留信息但避免重复。"""
    unique = []
    seen = set()
    for trigger in trigger_conditions:
        cleaned = clean_text(trigger)
        key = canonical_text_key(cleaned)
        if cleaned and key and key not in seen:
            seen.add(key)
            unique.append(cleaned)

    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]

    longest = max(unique, key=len)
    longest_key = canonical_text_key(longest)
    if all(canonical_text_key(item) in longest_key for item in unique):
        return longest

    return " OR ".join(unique)


def merge_aircraft_phases(phases: list[str]) -> str:
    """合并多个 aircraft_phase，优先保留具体阶段。"""
    unique = []
    seen = set()
    for phase in phases:
        cleaned = clean_text(phase)
        key = canonical_text_key(cleaned)
        if cleaned and key and key not in seen:
            seen.add(key)
            unique.append(cleaned)

    if not unique:
        return ""

    specific = [phase for phase in unique if canonical_text_key(phase) != "any"]
    if len(specific) == 1:
        return specific[0]
    if len(specific) > 1:
        return " / ".join(specific)
    return unique[0]


def merge_source_files(source_files: list[str]) -> str:
    """合并来源文件列表。"""
    unique = []
    seen = set()
    for source_file in source_files:
        cleaned = clean_source_file(source_file)
        key = canonical_text_key(cleaned)
        if cleaned and key and key not in seen:
            seen.add(key)
            unique.append(cleaned)

    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    return " | ".join(unique)


def merge_source_sections(source_sections: list[str]) -> str:
    """合并来源章节描述。"""
    unique = []
    seen = set()
    for section in source_sections:
        cleaned = clean_text(section)
        key = canonical_text_key(cleaned)
        if cleaned and key and key not in seen:
            seen.add(key)
            unique.append(cleaned)

    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    return " / ".join(unique)


def merge_source_excerpts(excerpts: list[str]) -> str:
    """合并来源摘录，优先保留信息量更高的版本。"""
    unique = []
    seen = set()
    for excerpt in excerpts:
        cleaned = clean_text(excerpt)
        key = canonical_text_key(cleaned)
        if cleaned and key and key not in seen:
            seen.add(key)
            unique.append(cleaned)

    if not unique:
        return ""
    return max(unique, key=len)


def sentence_candidates(source_text: str) -> list[str]:
    """将原文切成适合做 provenance 的候选片段。"""
    normalized = " ".join(source_text.split())
    if not normalized:
        return []

    candidates = re.split(r"(?<=[.!?])\s+", normalized)
    candidates = [candidate.strip() for candidate in candidates if len(candidate.strip()) >= 20]
    if candidates:
        return candidates

    return [normalized[:240]]


def best_matching_excerpt(source_text: str, query: str) -> str:
    """从原文中找一个与 query 最接近的短摘录。"""
    candidates = sentence_candidates(source_text)
    if not candidates:
        return ""

    query_keywords = extract_keywords(query)
    if not query_keywords:
        return candidates[0][:240]

    best_candidate = candidates[0]
    best_score = -1

    for candidate in candidates:
        candidate_keywords = extract_keywords(candidate)
        score = len(query_keywords & candidate_keywords)
        if score > best_score or (score == best_score and len(candidate) < len(best_candidate)):
            best_candidate = candidate
            best_score = score

    return best_candidate[:240]


def infer_best_source_file(proc: dict, source_text_by_file: dict[str, str]) -> str:
    """在多文件 chunk 场景下，为 procedure 推断最可能的来源文件。"""
    if not source_text_by_file:
        return ""

    query_parts = [
        proc.get("name"),
        proc.get("trigger_condition"),
        " ".join(clean_text(step.get("action")) for step in (proc.get("steps") or [])),
    ]
    query_keywords = set()
    for part in query_parts:
        query_keywords.update(extract_keywords(part))

    best_file = next(iter(source_text_by_file))
    best_score = -1
    for file_name, source_text in source_text_by_file.items():
        score = len(query_keywords & extract_keywords(source_text))
        if score > best_score:
            best_file = file_name
            best_score = score

    return best_file


def attach_provenance(procedures: list[dict], source_text_by_file: dict[str, str]) -> list[dict]:
    """为 procedure 和 step 补充 provenance 信息。"""
    available_files = set(source_text_by_file.keys())
    attached = []

    for proc in procedures:
        proc = dict(proc)
        source_file = clean_source_file(proc.get("source_file"))
        if not source_file or source_file not in available_files:
            if len(available_files) == 1:
                source_file = next(iter(available_files))
            else:
                source_file = infer_best_source_file(proc, source_text_by_file)

        source_text = source_text_by_file.get(source_file, "")

        proc["source_file"] = source_file
        proc["source_section"] = clean_text(proc.get("source_section")) or clean_text(proc.get("name"))
        proc["source_excerpt"] = clean_text(proc.get("source_excerpt")) or best_matching_excerpt(
            source_text,
            proc.get("source_section") or proc.get("name") or proc.get("trigger_condition"),
        )

        hydrated_steps = []
        for step in proc.get("steps", []) or []:
            step = dict(step)
            step["step_type"] = infer_step_type(step)
            step["source_excerpt"] = clean_text(step.get("source_excerpt")) or best_matching_excerpt(
                source_text,
                step.get("action"),
            )
            hydrated_steps.append(step)

        proc["steps"] = hydrated_steps
        attached.append(proc)

    return attached


def merge_steps(steps: list[dict]) -> list[dict]:
    """去重并重编号步骤，优先保留更完整的 expected_result。"""
    merged = []
    seen = {}

    for step in steps:
        action = clean_text(step.get("action"))
        if not action:
            continue

        key = canonical_text_key(action)
        expected_result = clean_text(step.get("expected_result"))
        source_excerpt = clean_text(step.get("source_excerpt"))
        step_type = infer_step_type(step)

        if key in seen:
            existing = merged[seen[key]]
            if not existing.get("expected_result") and expected_result:
                existing["expected_result"] = expected_result
            if (not existing.get("source_excerpt")) or len(source_excerpt) > len(existing.get("source_excerpt") or ""):
                existing["source_excerpt"] = source_excerpt
            if existing.get("step_type") == "immediate_action" and step_type != "immediate_action":
                existing["step_type"] = step_type
            continue

        merged.append(
            {
                "step_number": len(merged) + 1,
                "step_type": step_type,
                "action": action,
                "expected_result": expected_result or None,
                "source_excerpt": source_excerpt,
            }
        )
        seen[key] = len(merged) - 1

    return merged


def merge_warnings(warnings: list[dict]) -> list[dict]:
    """去重 warning。"""
    merged = []
    seen = set()
    for warning in warnings:
        description = clean_text(warning.get("description"))
        key = canonical_text_key(description)
        if not description or not key or key in seen:
            continue
        seen.add(key)
        merged.append({"description": description})
    return merged


def normalize_procedures(procedures: list[dict]) -> list[dict]:
    """
    清洗提取结果。

    当前查询层和 SHACL 都要求 procedure 至少包含一个 step。
    因此这里过滤掉只有标题说明、没有可执行步骤的条目；
    同时按 procedure name 合并重复项，并重新整理 step / warning。
    """
    grouped: dict[str, list[dict]] = {}
    order: list[str] = []

    for proc in procedures:
        name = clean_text(proc.get("name"))
        if not name:
            continue

        cleaned_proc = {
            "name": name,
            "trigger_condition": clean_text(proc.get("trigger_condition")),
            "aircraft_phase": clean_text(proc.get("aircraft_phase")),
            "source_file": clean_source_file(proc.get("source_file")),
            "source_section": clean_text(proc.get("source_section")),
            "source_excerpt": clean_text(proc.get("source_excerpt")),
            "steps": proc.get("steps") or [],
            "warnings": proc.get("warnings") or [],
        }

        key = canonical_text_key(name)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(cleaned_proc)

    normalized = []
    for key in order:
        proc_group = grouped[key]

        # 先让“信息更丰富”的条目作为主条目，减少差质量重复项主导合并结果
        proc_group = sorted(
            proc_group,
            key=lambda proc: (
                -(len(proc.get("steps") or [])),
                -(len(proc.get("warnings") or [])),
                -len(proc.get("trigger_condition") or ""),
            ),
        )

        all_steps = []
        all_warnings = []
        for proc in proc_group:
            sorted_steps = sorted(
                [step for step in (proc.get("steps") or []) if step.get("action")],
                key=lambda step: (
                    step.get("step_number") if step.get("step_number") is not None else 10**9,
                    clean_text(step.get("action")),
                ),
            )
            all_steps.extend(sorted_steps)
            all_warnings.extend(proc.get("warnings") or [])

        merged_proc = {
            "name": proc_group[0]["name"],
            "trigger_condition": merge_trigger_conditions(
                [proc.get("trigger_condition", "") for proc in proc_group]
            ),
            "aircraft_phase": merge_aircraft_phases(
                [proc.get("aircraft_phase", "") for proc in proc_group]
            ),
            "source_file": merge_source_files(
                [proc.get("source_file", "") for proc in proc_group]
            ),
            "source_section": merge_source_sections(
                [proc.get("source_section", "") for proc in proc_group]
            ),
            "source_excerpt": merge_source_excerpts(
                [proc.get("source_excerpt", "") for proc in proc_group]
            ),
            "steps": merge_steps(all_steps),
            "warnings": merge_warnings(all_warnings),
        }

        if not merged_proc["steps"]:
            continue

        if not merged_proc["trigger_condition"]:
            merged_proc.pop("trigger_condition")
        if not merged_proc["aircraft_phase"]:
            merged_proc.pop("aircraft_phase")
        if not merged_proc["source_section"]:
            merged_proc.pop("source_section")
        if not merged_proc["source_excerpt"]:
            merged_proc.pop("source_excerpt")
        if not merged_proc["warnings"]:
            merged_proc["warnings"] = []

        normalized.append(merged_proc)

    return normalized


def parse_retry_delay_seconds(error_text: str) -> float | None:
    """从报错文本中提取建议重试等待时间。"""
    retry_match = re.search(r"Please retry in ([0-9.]+)s", error_text, re.IGNORECASE)
    if retry_match:
        return float(retry_match.group(1))

    delay_match = re.search(r"'retryDelay': '([0-9.]+)s'", error_text, re.IGNORECASE)
    if delay_match:
        return float(delay_match.group(1))

    return None


def is_transient_gemini_rate_limit(error_text: str) -> bool:
    """判断是否是 Gemini 免费层的瞬时速率限制。"""
    lowered = error_text.lower()
    return (
        "resource_exhausted" in lowered
        and "generate_content_free_tier_requests" in lowered
        and "please retry in" in lowered
    )


def load_batch_input_files(input_dir: str) -> list[Path]:
    """
    读取批量模式的输入文件列表。

    优先使用 index.txt 中登记的正式文件顺序，避免目录中遗留的旧 txt
    被误加入提取流程；如果没有 index.txt，则回退到扫描目录。
    """
    input_path = Path(input_dir)
    index_path = input_path / "index.txt"

    if index_path.exists():
        txt_files = []
        missing_files = []

        for line in index_path.read_text(encoding="utf-8").splitlines():
            if "→" not in line:
                continue

            filename = line.split("→", 1)[1].strip()
            if not filename:
                continue

            file_path = input_path / filename
            if file_path.exists():
                txt_files.append(file_path)
            else:
                missing_files.append(filename)

        if missing_files:
            missing_str = "\n".join(f"  - {name}" for name in missing_files)
            raise FileNotFoundError(
                "index.txt 中登记的以下文件不存在：\n"
                f"{missing_str}\n"
                "请先重新运行 00_pdf_parse.py，或修复 data/procedures 目录。"
            )

        if txt_files:
            print(f"📚 使用 index.txt 中登记的 {len(txt_files)} 个正式程序文件")
            return txt_files

    txt_files = sorted(
        p for p in input_path.glob("*.txt")
        if p.name != "index.txt"
    )

    if txt_files:
        print("⚠️  未找到 index.txt，回退为扫描目录中的全部 txt 文件")

    return txt_files


def chunk_paths(paths: list[Path], chunk_size: int) -> list[list[Path]]:
    """把文件列表按固定大小切块。"""
    if chunk_size <= 0:
        chunk_size = 1
    return [paths[i:i + chunk_size] for i in range(0, len(paths), chunk_size)]


def build_chunk_text(file_paths: list[Path]) -> str:
    """将多个 procedure 文件合并成一次提取请求的文本。"""
    parts = []
    for idx, path in enumerate(file_paths, start=1):
        text = path.read_text(encoding="utf-8").strip()
        parts.append(f"[文档 {idx}: {path.name}]\n{text}")
    return "\n\n" + ("\n\n" + ("-" * 60) + "\n\n").join(parts)


def extract_from_text(text: str, schema_desc: str, client: OpenAI, model: str, provider: str) -> tuple[list, object]:
    """
    调用 LLM API 从文本提取程序列表。
    返回 (procedures_list, usage_object)
    """
    prompt = build_prompt(text, schema_desc)
    request_kwargs = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是航空安全专家，专门将航空手册转化为结构化知识。输出严格的 JSON 格式。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.1,
    }

    # Gemini 的 OpenAI 兼容接口支持 chat completions，但这里不强依赖
    # json_object 参数，以避免不同 provider 的行为差异导致失败。
    if provider == "openai":
        request_kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
        try:
            response = client.chat.completions.create(**request_kwargs)
            break
        except Exception as e:
            error_text = str(e)

            if provider == "gemini" and is_transient_gemini_rate_limit(error_text) and attempt < MAX_RATE_LIMIT_RETRIES:
                retry_after = parse_retry_delay_seconds(error_text) or 15.0
                wait_seconds = max(retry_after, GEMINI_BATCH_DELAY_SECONDS)
                print(f"        ⏳ Gemini 触发速率限制，{wait_seconds:.1f}s 后自动重试（第 {attempt}/{MAX_RATE_LIMIT_RETRIES} 次）")
                time.sleep(wait_seconds)
                continue

            raise

    raw_json = response.choices[0].message.content
    extracted = parse_json_response(raw_json)
    return extracted.get("procedures", []), response.usage


def extract_procedures(input_file: str, schema_file: str, output_file: str):
    """单文件提取（保持原有接口不变）"""
    client, model, provider = create_llm_client()

    print(f"📖 读取文本: {input_file}")
    with open(input_file, encoding="utf-8") as f:
        text = f.read()
    print(f"   文本长度: {len(text)} 字符")

    print(f"📐 读取 schema: {schema_file}")
    schema_desc = load_schema_description(schema_file)

    print(f"🤖 调用 {provider}:{model} 进行知识提取...")
    procedures, usage = extract_from_text(text, schema_desc, client, model, provider)
    procedures = attach_provenance(procedures, {Path(input_file).name: text})
    procedures = normalize_procedures(procedures)

    extracted = {"procedures": procedures}

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 提取完成!")
    print(f"   提取到 {len(procedures)} 个紧急程序:")
    for proc in procedures:
        name = proc.get("name", "未命名")
        steps = proc.get("steps", [])
        warnings = proc.get("warnings", [])
        print(f"   • {name}")
        print(f"     步骤数: {len(steps)}  |  警告数: {len(warnings)}")

    prompt_tokens, completion_tokens, total_tokens = usage_totals(usage)
    print(f"\n💾 结果已保存到: {output_file}")
    print(f"\n📊 Token 使用: 输入 {prompt_tokens} + 输出 {completion_tokens} = {total_tokens}")

    return extracted


def extract_batch(input_dir: str, schema_file: str, output_file: str):
    """批量提取：处理目录下所有 .txt 文件（排除 index.txt），合并结果。"""
    client, model, provider = create_llm_client()

    # 收集所有 txt 文件（按文件名排序，排除索引文件）
    txt_files = load_batch_input_files(input_dir)

    if not txt_files:
        raise FileNotFoundError(
            f"目录 {input_dir} 中未找到 .txt 文件。\n"
            "请先运行: python scripts/00_pdf_parse.py --pdf data/airplane_flying_handbook.pdf"
        )

    print(f"📐 读取 schema: {schema_file}")
    schema_desc = load_schema_description(schema_file)

    total = len(txt_files)
    files_per_request = GEMINI_BATCH_FILES_PER_REQUEST if provider == "gemini" else OPENAI_BATCH_FILES_PER_REQUEST
    chunks = chunk_paths(txt_files, files_per_request)
    all_procedures = []
    total_in = total_out = 0
    quota_exhausted = False

    print(f"📁 找到 {total} 个程序文件，开始批量提取...")
    print(f"   provider: {provider}:{model}")
    print(f"   每次请求处理文件数: {files_per_request}")
    print(f"   总请求批次: {len(chunks)}\n")

    for idx, file_chunk in enumerate(chunks, start=1):
        chunk_names = ", ".join(path.name for path in file_chunk)
        text = build_chunk_text(file_chunk)
        source_text_by_file = {
            path.name: path.read_text(encoding="utf-8")
            for path in file_chunk
        }

        print(f"[批次 {idx}/{len(chunks)}] 处理 {len(file_chunk)} 个文件")
        print(f"        文件: {chunk_names}")
        print(f"        合并文本长度: {len(text)} 字符")

        try:
            procedures, usage = extract_from_text(text, schema_desc, client, model, provider)
            procedures = attach_provenance(procedures, source_text_by_file)
            procedures = normalize_procedures(procedures)
            all_procedures.extend(procedures)
            prompt_tokens, completion_tokens, _ = usage_totals(usage)
            total_in += prompt_tokens
            total_out += completion_tokens

            print(f"        ✓ 本批次提取到 {len(procedures)} 个程序")
            for proc in procedures[:5]:
                name = proc.get("name", "未命名")
                steps = proc.get("steps", [])
                print(f"        ✓ {name}（{len(steps)} 步）")
            if len(procedures) > 5:
                print(f"        … 其余 {len(procedures) - 5} 个程序已省略显示")

        except Exception as e:
            error_text = str(e).lower()
            if "insufficient_quota" in error_text:
                quota_exhausted = True
                print(f"        ❌ {provider} API 额度不足，停止批量提取")
                break
            print(f"        ⚠️  提取失败: {e}，跳过此文件")

        if provider == "gemini" and idx < len(chunks):
            print(f"        🕒 Gemini 免费层限速保护，等待 {GEMINI_BATCH_DELAY_SECONDS:.1f}s...")
            time.sleep(GEMINI_BATCH_DELAY_SECONDS)

        print()

    if quota_exhausted:
        raise RuntimeError(
            f"{provider} API 返回额度不足错误，批量提取已停止。"
            "为避免覆盖已有结果，本次不会写入 output/extracted.json。"
        )

    if not all_procedures:
        raise RuntimeError(
            "未提取到任何程序，本次不会覆盖已有 output/extracted.json。"
        )

    # 合并并保存
    merged = {"procedures": normalize_procedures(all_procedures)}
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"✅ 批量提取完成!")
    print(f"   处理文件: {total} 个")
    print(f"   提取程序: {len(merged['procedures'])} 个")
    print(f"\n💾 结果已保存到: {output_file}")
    print(f"\n📊 Token 合计: 输入 {total_in} + 输出 {total_out} = {total_in + total_out}")

    return merged


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从航空文本提取结构化知识")
    parser.add_argument("--input",     default=INPUT_FILE,  help="单文件模式：输入文本文件路径")
    parser.add_argument("--input-dir", default=None,        help="批量模式：包含程序 txt 文件的目录")
    parser.add_argument("--schema",    default=SCHEMA_FILE, help="LinkML schema 路径")
    parser.add_argument("--output",    default=OUTPUT_FILE, help="输出 JSON 路径")
    args = parser.parse_args()

    if args.input_dir:
        extract_batch(args.input_dir, args.schema, args.output)
    else:
        extract_procedures(args.input, args.schema, args.output)
