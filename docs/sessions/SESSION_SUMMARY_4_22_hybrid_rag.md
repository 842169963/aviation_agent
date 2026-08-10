# 工作会话总结 - 2026-04-22 Hybrid RAG v1

> 本次会话在 [SESSION_SUMMARY_4_21.md](</E:/aviation project/SESSION_SUMMARY_4_21.md>) 的基础上继续推进。
> 上次已经完成 provenance 版 KG 的定点修复，本次重点是把 **Hybrid RAG 第一版 retrieval prototype** 跑通。

---

## 一、这次完成了什么

### 1. 先验证了 ChatAnywhere Embedding API

一开始 `.env` 里只有 `OPENAI_API_KEY`，没有 `OPENAI_BASE_URL`，导致 embedding 请求被发到 OpenAI 官方 endpoint，并返回：

```text
401 invalid_api_key
```

确认当前使用的是 ChatAnywhere 后，已在本地 `.env` 中补充：

```env
OPENAI_BASE_URL=https://api.chatanywhere.tech/v1
LLM_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
```

随后 embedding smoke test 成功：

```text
provider=openai
embedding_model=text-embedding-3-small
base_url_host=https://api.chatanywhere.tech
embedding_dimensions=1536
status=OK
```

说明当前 ChatAnywhere endpoint 支持 `text-embedding-3-small`，可以进入 Hybrid RAG 实现。

---

### 2. 新增 Hybrid RAG v1 设计文档

新增文件：

- [HYBRID_RAG_V1.md](</E:/aviation project/aviation_prototype/HYBRID_RAG_V1.md>)

文档记录了：

- v1 目标
- KG + vector 双通道架构
- 新增脚本设计
- ChromaDB 依赖
- 合并评分策略
- 验收用例
- 暂不做 LangGraph / Agent 的原因

核心原则：

```text
Vector 只负责语义召回候选 procedure。
最终 steps / warnings / evidence 仍然从已验证 KG 中读取。
```

---

### 3. 新增向量索引构建脚本

新增文件：

- [05_build_vector_index.py](</E:/aviation project/aviation_prototype/scripts/05_build_vector_index.py>)

作用：

- 读取 [extracted.json](</E:/aviation project/aviation_prototype/output/extracted.json>)
- 将每个 emergency procedure 转成一条 procedure-level document
- 调用 OpenAI-compatible embedding API
- 写入本地 ChromaDB index

输出位置：

```text
aviation_prototype/output/vector_index/
```

该目录是本地运行产物，已加入 [.gitignore](</E:/aviation project/.gitignore>)，不会提交。

本次运行结果：

```text
procedure_documents=18
embedding_model=text-embedding-3-small
embedding_dimensions=1536
collection=aviation_procedures
status=OK
```

---

### 4. 新增 Hybrid Query 脚本

新增文件：

- [06_hybrid_query.py](</E:/aviation project/aviation_prototype/scripts/06_hybrid_query.py>)

作用：

```text
用户自然语言问题
  ├─ KG 通道：keyword / structured fields 召回
  └─ Vector 通道：ChromaDB semantic retrieval
        ↓
  合并候选 procedure
        ↓
  从 kg.ttl 读取完整 steps / warnings / provenance
        ↓
  输出 advisory-style 结果
```

KG 通道覆盖字段：

- procedure name
- trigger condition
- aircraft phase
- source section
- procedure excerpt
- step action
- step source excerpt
- warning description

Vector 通道：

- 查询本地 ChromaDB collection
- 默认取 top 5
- top 1 得 `+3`，top 2-3 得 `+2`，top 4-5 得 `+1`

合并策略：

```text
final_score = kg_score + vector_score
```

---

## 二、验证结果

### 1. 语法检查

已通过：

```bash
.\.venv\Scripts\python.exe -m py_compile .\scripts\05_build_vector_index.py .\scripts\06_hybrid_query.py
```

---

### 2. 向量索引构建

已通过：

```bash
.\.venv\Scripts\python.exe .\scripts\05_build_vector_index.py
```

关键结果：

```text
procedure_documents=18
embedding_dimensions=1536
status=OK
```

---

### 3. 五个验收查询全部 top-1 命中

已验证：

| 查询 | 预期结果 | 实际结果 |
|---|---|---|
| `engine failure after takeoff` | `Engine Failure After Takeoff (Single-Engine)` | PASS |
| `smoke in cabin` | `Cabin Fire` | PASS |
| `accidentally flew into clouds` | `Inadvertent VFR Flight Into IMC` | PASS |
| `landing on snow whiteout` | `Snow Landing` | PASS |
| `pilot incapacitated parachute` | `Ballistic Parachute Deployment` | PASS |

最关键的验证结果：

```text
Question: accidentally flew into clouds
Top result: Inadvertent VFR Flight Into IMC
Final score: KG 0 + Vector 3
```

这个结果很重要，因为问题里没有出现 `IMC` 关键词，KG keyword 通道没有命中，但 vector semantic 通道成功找回了正确 procedure。

---

## 三、这说明了什么

本次 Hybrid RAG v1 跑通后，证明了三件事：

### 1. 当前 KG 已经能支撑 retrieval prototype

当前 `18` 个 procedure、`99` 个 steps、`19` 个 warnings 已经足够支持第一版 advisor 检索层。

虽然局部抽取质量后续还能继续优化，但已经不是做 RAG 原型的阻塞点。

### 2. Vector 通道补上了纯 keyword / SPARQL 的短板

以前用户必须说出接近 procedure name 的关键词，例如：

```text
IMC
engine
snow
ballistic
```

现在可以用更自然的问题：

```text
accidentally flew into clouds
pilot incapacitated parachute
landing on snow whiteout
smoke in cabin
```

系统仍然能找到正确 emergency procedure。

### 3. 最终答案仍然受 KG 约束

当前实现没有让 LLM 自由生成飞行建议。

流程是：

```text
语义召回找入口
KG 提供权威结构化内容
输出 steps / warnings / source evidence
```

这对 aviation safety 场景更稳，因为可以避免模型凭空编新步骤。

---

## 四、本次修改文件

新增：

- [HYBRID_RAG_V1.md](</E:/aviation project/aviation_prototype/HYBRID_RAG_V1.md>)
- [05_build_vector_index.py](</E:/aviation project/aviation_prototype/scripts/05_build_vector_index.py>)
- [06_hybrid_query.py](</E:/aviation project/aviation_prototype/scripts/06_hybrid_query.py>)
- [SESSION_SUMMARY_4_22_hybrid_rag.md](</E:/aviation project/SESSION_SUMMARY_4_22_hybrid_rag.md>)

修改：

- [.gitignore](</E:/aviation project/.gitignore>)
- [README.md](</E:/aviation project/aviation_prototype/README.md>)
- [.env.example](</E:/aviation project/aviation_prototype/.env.example>)
- [requirements.txt](</E:/aviation project/aviation_prototype/requirements.txt>)

本地生成但不提交：

- `aviation_prototype/output/vector_index/`
- `aviation_prototype/.env`

---

## 五、当前运行方式

进入目录：

```bash
cd "E:\aviation project\aviation_prototype"
```

构建向量索引：

```bash
.\.venv\Scripts\python.exe .\scripts\05_build_vector_index.py
```

运行 Hybrid RAG 查询：

```bash
.\.venv\Scripts\python.exe .\scripts\06_hybrid_query.py --question "accidentally flew into clouds"
.\.venv\Scripts\python.exe .\scripts\06_hybrid_query.py --question "pilot incapacitated parachute"
```

---

## 六、当前限制

这还不是完整 advisor agent。

当前已经完成的是：

```text
retrieval layer
```

尚未完成：

- LLM synthesis
- 多轮对话
- 飞行状态管理
- LangGraph 编排
- 风险分级
- 根据 aircraft profile / POH 的机型适配

---

## 七、建议下一步

推荐下一步做：

```text
Grounded LLM synthesis
```

也就是在 [06_hybrid_query.py](</E:/aviation project/aviation_prototype/scripts/06_hybrid_query.py>) 后面加一个可选 synthesis 层：

- 输入：retrieved steps + warnings + source evidence
- 输出：简洁、可操作、飞行员能读的 advisor response
- 约束：不得编造 KG 中不存在的新步骤
- 保留：source evidence / warning / POH disclaimer

暂时不建议直接上 LangGraph。

更合适的顺序是：

```text
Hybrid RAG v1 retrieval baseline
  → grounded LLM synthesis
  → response quality evaluation
  → 再考虑 LangGraph / Agentic workflow
```

---

*生成于 2026-04-22 - Codex 会话*
