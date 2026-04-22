# Aviation Agentic AI — Prototype

私人飞行员 AI 决策辅助系统 · 小型验证原型

## 系统架构

```
FAA 手册文本 (data/)
    ↓  [01_extract.py]  OpenAI / Gemini 按 LinkML schema 提取
output/extracted.json
    ↓  [02_validate.py] JSON → RDF 图谱 + SHACL 验证
output/kg.ttl  (已验证的知识图谱)
    ↓  [03_query.py]   SPARQL 查询 → 飞行员建议输出
"发动机失效怎么办？" → 步骤 1、2、3...

Hybrid RAG v1:
output/extracted.json
    ↓  [05_build_vector_index.py]  ChromaDB 向量索引
output/vector_index/
    ↓  [06_hybrid_query.py]        KG + vector 双通道召回
"accidentally flew into clouds" → Inadvertent VFR Flight Into IMC
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 OpenAI 或 Gemini API Key
```

### 3. 运行完整流水线

```bash
# Step 1: 从文本提取知识（需要 OpenAI API 或 Gemini API）
python scripts/01_extract.py

# Step 2: 构建 RDF 图谱 + SHACL 验证
python scripts/02_validate.py

# Step 3: 查询知识图谱
python scripts/03_query.py
python scripts/03_query.py --question "takeoff"
python scripts/03_query.py --list
python scripts/03_query.py --interactive
```

### 4. 运行 Hybrid RAG v1

```bash
# Step 5: 从 extracted.json 构建本地 ChromaDB 向量索引
python scripts/05_build_vector_index.py

# Step 6: KG + vector 双通道查询
python scripts/06_hybrid_query.py --question "accidentally flew into clouds"
python scripts/06_hybrid_query.py --question "pilot incapacitated parachute"

# 可选：在 KG 检索结果上生成 grounded advisor 回复
python scripts/06_hybrid_query.py --question "accidentally flew into clouds" --synthesize --top-k 1
python scripts/06_hybrid_query.py --question "accidentally flew into clouds" --synthesis-only --top-k 1 --no-debug

# Step 7: 运行 Hybrid RAG 回归评估
python scripts/07_eval_hybrid_rag.py
python scripts/07_eval_hybrid_rag.py --include-synthesis
```

`ProcedureStep.step_type` 用于把步骤分成 `immediate_action`、`training_note`、`caution`、`background`，让 synthesis 能把立即动作、训练/准备说明和风险提示分开展示。

## 文件结构

```
aviation_prototype/
├── data/
│   └── efato_sample.txt        # 样本 FAA 文本 (EFATO + 巡航失效)
├── schema/
│   └── emergency_schema.yaml   # LinkML schema — 定义知识结构
├── shacl/
│   └── procedure_shapes.ttl    # SHACL shapes — 验证约束
├── scripts/
│   ├── 01_extract.py           # 知识提取
│   ├── 02_validate.py          # 图谱构建 + SHACL 验证
│   ├── 03_query.py             # 知识图谱查询
│   ├── 05_build_vector_index.py # 构建 ChromaDB 向量索引
│   ├── 06_hybrid_query.py      # Hybrid RAG 查询
│   └── 07_eval_hybrid_rag.py   # Hybrid RAG 回归评估
├── output/                     # 运行后自动生成
│   ├── extracted.json          # 提取结果
│   ├── kg.ttl                  # RDF 知识图谱
│   ├── validation_report.txt   # SHACL 验证报告
│   ├── hybrid_eval_report.md   # Hybrid RAG 评估报告
│   └── vector_index/           # 本地向量索引（不提交）
└── requirements.txt
```

## LLM Provider

`01_extract.py` 支持两种 provider：

- `OPENAI_API_KEY`：默认使用 OpenAI，默认模型是 `gpt-4o-mini`
- `GEMINI_API_KEY`：使用 Gemini 的 OpenAI 兼容接口，默认模型是 `gemini-2.5-flash`
- `OPENAI_BASE_URL`：可选，用于兼容 OpenAI 协议的第三方转发服务

可选环境变量：

```bash
LLM_PROVIDER=openai   # 或 gemini
OPENAI_BASE_URL=https://api.chatanywhere.tech/v1
MODEL_NAME=gpt-4o-mini
MODEL_NAME=gemini-2.5-flash
EMBEDDING_MODEL=text-embedding-3-small
SYNTHESIS_MODEL=gpt-4o-mini
```

## 扩展方向

| 扩展目标 | 做法 |
|----------|------|
| 接入真实 FAA PDF | 用 `pdfplumber` 提取文本，替换 `data/` 中的文件 |
| 加入向量检索 | 加 ChromaDB，实现 Hybrid RAG |
| Agentic 编排 | 用 LangGraph 包装查询层，支持多轮对话 |
| 持久化图谱 | 替换 rdflib 为 Neo4j 或 Oxigraph |
