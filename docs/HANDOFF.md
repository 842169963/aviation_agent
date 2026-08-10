# Aviation Agentic AI — Handoff Document

> 给 Claude Code 的交接文档。记录了本次 Cowork 会话完成的所有工作，以及下一步建议。

---

## 一、项目背景

**目标**：为私人飞行员构建一个 AI 决策辅助系统。不是替代飞行员，而是在紧急或异常情况下提供有根据的、上下文感知的分步骤建议。

**核心问题**：私人飞行员飞行频率低，在压力下容易忘记检查单和应急程序；航空手册是静态文档，飞行情况是动态变化的。

**系统四层架构**：
```
FAA 航空手册 / 检查单
    ↓ 知识提取层
本体 + 知识图谱 (结构化领域知识)
    ↓ 检索层 (Hybrid RAG)
Agentic AI 编排层
    ↓
飞行员建议输出 (分步骤、有根据、简洁)
```

**使用的 FAA 手册资源**（用于知识来源）：
- Airplane Flying Handbook: https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/airplane_handbook
- PHAK: https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/phak
- Risk Management Handbook: https://www.faa.gov/regulationspolicies/handbooksmanuals/risk-management-handbook-faa-h-8083-2a

---

## 二、本次会话完成的工作

### 2.1 汇报 PPT（`aviation_ai_v2.pptx`）

**文件位置**：`aviation project/aviation_ai_v2.pptx`

共 10 张幻灯片，聚焦三个核心工具，用 EFATO（发动机起飞后失效）场景作为贯穿始终的具体例子：

| 幻灯片 | 内容 |
|--------|------|
| 1 | 封面 |
| 2 | 问题背景 |
| 3 | 三工具流水线总览 |
| 4 | LinkML 理论 |
| **5** | **LinkML 例子**：EFATO 的 YAML schema 代码 |
| 6 | OntoGPT 理论 |
| **7** | **OntoGPT 例子**：POH 原文 → 结构化提取输出对比 |
| 8 | SHACL 理论 |
| **9** | **SHACL 例子**：PASS / FAIL 验证结果卡片 |
| 10 | 总结 + EFATO 追踪链 |

**三工具职责**：
- **LinkML** — 定义目标 schema（蓝图）
- **OntoGPT** — 从手册文本提取结构化知识
- **SHACL** — 验证知识图谱数据质量，阻止不合格数据进入 AI advisor

---

### 2.2 可运行 Prototype（`aviation_prototype/`）

**文件位置**：`aviation project/aviation_prototype/`

完整的 Python 项目，已在沙盒测试全部通过。

#### 目录结构

```
aviation_prototype/
├── README.md
├── requirements.txt              # openai, rdflib, pyshacl, pdfplumber, pyyaml
├── .env.example                  # OPENAI_API_KEY=...
├── schema/
│   └── emergency_schema.yaml     # LinkML schema 定义
├── data/
│   └── efato_sample.txt          # 样本文本（EFATO + 巡航发动机失效）
├── shacl/
│   └── procedure_shapes.ttl      # SHACL shapes（3个约束）
├── output/                       # 运行后自动生成
│   ├── extracted.json
│   ├── kg.ttl
│   └── validation_report.txt
└── scripts/
    ├── 01_extract.py
    ├── 02_validate.py
    └── 03_query.py
```

#### 流水线说明

**Step 1 — `01_extract.py`**
- 读取 `data/` 中的文本文件
- 按 `schema/emergency_schema.yaml` 的结构，调用 OpenAI GPT（gpt-4o-mini）提取
- 输出：`output/extracted.json`，包含所有 `EmergencyProcedure` 实例
- 需要：`OPENAI_API_KEY`

**Step 2 — `02_validate.py`**
- 读取 `extracted.json`，将 JSON 转换为 RDF 三元组（rdflib）
- 使用 `pyshacl` 对照 `shacl/procedure_shapes.ttl` 验证
- SHACL 约束：每个 Procedure 必须有 name 和至少 1 个 step；每个 Step 必须有 action 和 step_number
- 输出：`output/kg.ttl`（Turtle 格式 RDF 图谱）+ 验证报告
- FAIL 的数据被阻止，不会进入查询层

**Step 3 — `03_query.py`**
- 从 `kg.ttl` 加载知识图谱
- 用 SPARQL 查询按关键词检索相关程序
- 格式化输出飞行员友好的分步建议
- 支持：`--question`、`--list`、`--interactive` 三种模式

#### 运行命令

```bash
cd aviation_prototype
pip install -r requirements.txt
cp .env.example .env   # 填入 OpenAI API Key

python scripts/01_extract.py
python scripts/02_validate.py
python scripts/03_query.py --question "engine failure"
```

#### 测试输出样例

```
📋 程序: Engine Failure After Takeoff
   触发条件: Engine failure below 1000ft AGL

   [1] Lower nose to maintain 65 KIAS
       → 预期结果: Aircraft maintains flying speed
   [2] Select landing area ahead
   [3] Set fuel selector to OFF
   [4] Set ignition switch to OFF

   ⚠️  警告: Do not attempt to return to runway below 1000ft AGL
```

---

## 三、LinkML Schema（数据模型）

```yaml
classes:
  EmergencyProcedure:       # 核心：一个完整紧急程序
    name: string            # required
    trigger_condition: str
    aircraft_phase: str
    steps: [ProcedureStep]
    warnings: [Warning]

  ProcedureStep:            # 单个检查单步骤
    step_number: integer    # required
    action: string          # required
    expected_result: str

  Warning:                  # 安全警告
    description: string     # required
```

---

## 四、下一步建议

以下是建议 Claude Code 继续完成的任务，优先级从高到低：

### 4.1 接入真实 FAA PDF（高优先级）
- 用 `pdfplumber` 解析下载的 AFH PDF（Chapter 17 Emergency Procedures）
- 按章节分割文本，批量运行 `01_extract.py`
- 目标：从真实 FAA 手册建立知识图谱，而非用样本文本

```python
# 示例：PDF 提取入口
import pdfplumber
with pdfplumber.open("data/airplane_flying_handbook.pdf") as pdf:
    chapter_17 = pdf.pages[240:265]  # 根据实际页码调整
    text = "\n".join(p.extract_text() for p in chapter_17)
```

### 4.2 加入向量检索（Hybrid RAG）
当前 prototype 只有 SPARQL（结构化检索）。需要补充向量检索：
- 安装 `chromadb`，对每个 procedure 的文本生成 embedding
- 实现双通道检索：SPARQL（精确）+ ChromaDB（语义相似）
- 合并结果后送入 LLM 生成最终回答

```
用户问题
    ├── SPARQL 查询 → 结构化程序步骤
    └── ChromaDB 向量查询 → 语义相关段落
         ↓ 合并
    LLM 生成最终建议
```

### 4.3 LangGraph Agentic 编排层
将查询层包装成一个有状态的 Agent：
- Node 1: 识别飞行情境（从用户输入提取意图）
- Node 2: 选择检索策略（KG / 向量 / 混合）
- Node 3: 执行检索
- Node 4: 生成并格式化建议
- 支持多轮对话（跟踪上下文）

### 4.4 本体扩展
当前 schema 只覆盖 EmergencyProcedure。后续可扩展：
- `AbnormalProcedure`（异常但非紧急）
- `SystemComponent`（发动机、燃油系统等）
- `WeatherCondition`（IMC、结冰等）
- `AircraftState`（传感器数据接口）

### 4.5 评估层
- 验证提取准确率（与 FAA 原文对照）
- 评估 RAG 召回质量（相关程序是否被检索到）
- SHACL 覆盖率统计（多少数据通过验证）

---

## 五、技术栈总览

| 层 | 当前 prototype | 下一步 |
|----|----------------|--------|
| PDF 处理 | pdfplumber（待接入） | 同左 |
| Schema 定义 | LinkML YAML | 同左，扩展类 |
| 知识提取 | OpenAI GPT-4o-mini | 可选 OntoGPT CLI |
| 图谱存储 | rdflib (内存) | Neo4j 或 Oxigraph |
| 验证 | pyshacl | 同左 |
| 向量存储 | 无 | ChromaDB |
| RAG 编排 | 无 | LlamaIndex |
| Agent 编排 | 无 | LangGraph |
| LLM | OpenAI API | Claude API / 本地模型 |

---

*文档生成于 2026-04-16 · Cowork 会话*
