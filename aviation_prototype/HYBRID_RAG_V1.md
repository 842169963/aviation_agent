# Hybrid RAG 第一版实施方案

本文档记录当前 aviation prototype 的 Hybrid RAG v1 设计与实施步骤。

目标不是立刻做完整 agent，而是先把 `KG + vector` 双通道召回跑通，让系统能够用语义问题找到正确的 emergency procedure，并继续用已验证知识图谱输出结构化步骤、warning 和来源依据。

---

## 一、当前基础

现有链路已经完成：

```text
FAA procedure txt
  ↓
scripts/01_extract.py
  ↓
output/extracted.json
  ↓
scripts/02_validate.py
  ↓
output/kg.ttl
  ↓
scripts/03_query.py
```

当前 KG 状态：

- procedure 数量：`18`
- steps 总数：`99`
- warnings 总数：`19`
- RDF triples：`777`
- SHACL：`PASS`

现有查询层 `scripts/03_query.py` 主要是 SPARQL + keyword 查询，适合精确命中 procedure name，例如：

```bash
.\.venv\Scripts\python.exe .\scripts\03_query.py --question "engine"
```

但它对语义问法不够强。例如用户问：

```text
what if I accidentally fly into clouds?
```

这个问题没有直接出现 `IMC`，纯 keyword 查询可能召回不足。

---

## 二、Hybrid RAG v1 的核心思路

第一版架构：

```text
用户问题
  ├─ KG 通道：SPARQL / keyword / structured fields 精确召回
  └─ Vector 通道：procedure text / steps / warnings 语义召回
        ↓
  合并候选 procedure
        ↓
  从 KG 读取完整 steps / warnings / provenance
        ↓
  输出飞行员友好的 advisory response
```

关键原则：

- KG 是权威结构源。
- Vector 只负责找到候选 procedure。
- 最终答案仍然从 `kg.ttl` 中读取，避免向量 chunk 自己组织出不受验证的答案。
- 第一版不接 LLM 生成最终建议，先验证 retrieval 是否稳定。

---

## 三、建议新增文件

### 1. `scripts/05_build_vector_index.py`

用途：

- 读取 `output/extracted.json`
- 将每个 procedure 转成一条向量文档
- 建立本地向量索引

第一版建议按 procedure 级 chunk，不要先按 step 级切分。

每条向量文档建议包含：

```text
Procedure: Inadvertent VFR Flight Into IMC
Trigger: Encountering instrument meteorological conditions unintentionally
Phase: All phases of flight
Source: 24_inadvertent_vfr_flight_into_imc.txt | ...
Section: Inadvertent VFR Flight Into IMC
Excerpt: Accident statistics show...

Steps:
1. Recognize and accept the seriousness of the situation...
2. Maintain control of the airplane using flight instruments...
3. Trim the airplane...

Warnings:
- Attempts to control the airplane partially by reference to flight instruments...
```

metadata 建议保存：

```json
{
  "procedure_name": "Inadvertent VFR Flight Into IMC",
  "source_file": "24_inadvertent_vfr_flight_into_imc.txt | ...",
  "source_section": "Inadvertent VFR Flight Into IMC",
  "aircraft_phase": "All phases of flight"
}
```

输出位置建议：

```text
output/vector_index/
```

---

### 2. `scripts/06_hybrid_query.py`

用途：

- 接收用户问题
- 同时跑 KG 通道和 vector 通道
- 合并候选 procedure
- 从 KG 中读取完整 procedure 内容
- 输出结构化 advisory response

命令形式：

```bash
.\.venv\Scripts\python.exe .\scripts\06_hybrid_query.py --question "accidentally flew into clouds"
```

第一版输出应至少包含：

- 命中的 procedure name
- 触发条件
- 来源文件 / 来源章节
- procedure excerpt
- ordered steps
- warnings
- 每个 step 的 source excerpt
- KG 命中、vector 命中、合并分数等 debug 信息

---

## 四、依赖选择

第一版推荐使用：

```text
chromadb
openai
python-dotenv
```

当前 `requirements.txt` 已有：

```text
openai>=1.0.0
rdflib>=6.3.0
pyshacl>=0.23.0
pdfplumber>=0.10.0
python-dotenv>=1.0.0
pyyaml>=6.0
```

建议新增：

```text
chromadb>=0.5.0
```

embedding 模型建议先配置为：

```env
EMBEDDING_MODEL=text-embedding-3-small
```

如果当前 OpenAI-compatible 转发服务不支持 embedding，再改成本地 embedding 方案，例如 `sentence-transformers`。第一版代码最好把 embedding provider 封装清楚，避免写死。

---

## 五、KG 通道设计

当前 `scripts/03_query.py` 只按 procedure name 做 `CONTAINS` 查询。

Hybrid RAG v1 中，KG 通道建议扩大检索范围：

- `EmergencyProcedure.name`
- `EmergencyProcedure.trigger_condition`
- `EmergencyProcedure.aircraft_phase`
- `EmergencyProcedure.source_section`
- `ProcedureStep.action`
- `ProcedureStep.source_excerpt`
- `Warning.description`

KG 通道可以返回：

```json
{
  "procedure_name": "Cabin Fire",
  "kg_score": 2,
  "matched_fields": ["name", "step.action"]
}
```

建议评分：

| 命中位置 | 分数 |
|---|---:|
| procedure name | `+3` |
| trigger condition | `+2` |
| source section | `+2` |
| step action | `+2` |
| warning description | `+1` |
| source excerpt | `+1` |

---

## 六、Vector 通道设计

Vector 通道负责语义召回。

输入：

```text
用户自然语言问题
```

输出：

```json
[
  {
    "procedure_name": "Inadvertent VFR Flight Into IMC",
    "vector_rank": 1,
    "vector_score": 3,
    "distance": 0.18
  }
]
```

建议第一版取 top 5：

```python
collection.query(
    query_texts=[question],
    n_results=5
)
```

Vector 排名转分数建议：

| 排名 | 分数 |
|---|---:|
| top 1 | `+3` |
| top 2-3 | `+2` |
| top 4-5 | `+1` |

---

## 七、合并策略

第一版合并逻辑保持简单：

```text
final_score = kg_score + vector_score
```

如果同一个 procedure 同时被 KG 和 vector 命中，则分数累加。

最终取前 `3` 个 procedure：

```text
top_k = 3
```

合并后的候选结构：

```json
{
  "procedure_name": "Inadvertent VFR Flight Into IMC",
  "final_score": 5,
  "kg_score": 2,
  "vector_score": 3,
  "matched_fields": ["trigger_condition", "step.action"],
  "vector_rank": 1
}
```

然后用 procedure name 回到 KG 查询完整 steps / warnings / provenance。

---

## 八、第一版不要做的事

为了保持 v1 可控，暂时不要做：

- 不要直接让 LLM 自由生成飞行建议。
- 不要上 LangGraph。
- 不要做多轮 Agent。
- 不要把整本 PDF raw text 全部塞进向量库。
- 不要一开始就做 step 级 chunk。
- 不要让 vector chunk 成为最终答案来源。

v1 只解决一个问题：

```text
语义问法能不能稳定找对 procedure？
```

---

## 九、建议实现顺序

### Step 1：更新依赖

修改 `requirements.txt`：

```text
chromadb>=0.5.0
```

安装依赖：

```bash
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

### Step 2：新增 vector index builder

新增：

```text
scripts/05_build_vector_index.py
```

运行：

```bash
.\.venv\Scripts\python.exe .\scripts\05_build_vector_index.py
```

预期输出：

```text
读取 output/extracted.json
构建 18 条 procedure documents
写入 output/vector_index/
```

---

### Step 3：新增 hybrid query

新增：

```text
scripts/06_hybrid_query.py
```

运行：

```bash
.\.venv\Scripts\python.exe .\scripts\06_hybrid_query.py --question "accidentally flew into clouds"
```

预期召回：

```text
Inadvertent VFR Flight Into IMC
```

---

### Step 4：保留 KG 格式化输出

可以复用 `scripts/03_query.py` 中的：

- `load_kg`
- `get_procedure_steps`
- `get_procedure_warnings`
- `format_advisory_response`

但建议后续把公共查询函数抽到单独模块，例如：

```text
scripts/query_common.py
```

第一版为了少改动，也可以先在 `06_hybrid_query.py` 中复用或复制少量函数。

---

## 十、验收用例

建议至少跑以下查询：

```bash
.\.venv\Scripts\python.exe .\scripts\06_hybrid_query.py --question "engine failure after takeoff"
.\.venv\Scripts\python.exe .\scripts\06_hybrid_query.py --question "smoke in cabin"
.\.venv\Scripts\python.exe .\scripts\06_hybrid_query.py --question "accidentally flew into clouds"
.\.venv\Scripts\python.exe .\scripts\06_hybrid_query.py --question "landing on snow whiteout"
.\.venv\Scripts\python.exe .\scripts\06_hybrid_query.py --question "pilot incapacitated parachute"
```

期待结果：

| 问题 | 期待召回 |
|---|---|
| `engine failure after takeoff` | `Engine Failure After Takeoff (Single-Engine)` |
| `smoke in cabin` | `Cabin Fire` |
| `accidentally flew into clouds` | `Inadvertent VFR Flight Into IMC` |
| `landing on snow whiteout` | `Snow Landing` |
| `pilot incapacitated parachute` | `Ballistic Parachute Deployment` |

---

## 十一、成功标准

Hybrid RAG v1 完成的标准：

- 能从 `output/extracted.json` 构建本地向量索引。
- 能同时运行 KG 通道和 vector 通道。
- 能合并同名 procedure 候选。
- 能对语义问法召回正确 procedure。
- 最终输出仍来自 `output/kg.ttl`。
- 输出中保留 source file、source section、source excerpt。
- 至少通过上面的 5 个验收查询。

---

## 十二、后续 v2 方向

v1 稳定后，再考虑：

- step 级 chunk
- warning 级 chunk
- reranker
- LLM answer synthesis
- LangGraph / agentic workflow
- query intent classification
- 根据飞行阶段、飞机状态、风险等级做检索策略选择
- Neo4j / Oxigraph 等持久化图数据库

---

## 十三、推荐结论

当前项目最适合的下一步是：

```text
先实现 Hybrid RAG v1 retrieval prototype。
```

不要急着做完整 advisor agent。先确认：

```text
自然语言问题 → 正确 procedure 召回 → KG 权威结构化输出
```

这条链路稳定后，再进入 LLM 生成、agent 编排和交互式 advisor。
