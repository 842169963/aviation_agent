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
│   └── 03_query.py             # 知识图谱查询
├── output/                     # 运行后自动生成
│   ├── extracted.json          # 提取结果
│   ├── kg.ttl                  # RDF 知识图谱
│   └── validation_report.txt   # SHACL 验证报告
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
```

## 扩展方向

| 扩展目标 | 做法 |
|----------|------|
| 接入真实 FAA PDF | 用 `pdfplumber` 提取文本，替换 `data/` 中的文件 |
| 加入向量检索 | 加 ChromaDB，实现 Hybrid RAG |
| Agentic 编排 | 用 LangGraph 包装查询层，支持多轮对话 |
| 持久化图谱 | 替换 rdflib 为 Neo4j 或 Oxigraph |
