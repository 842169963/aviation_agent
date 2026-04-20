# 工作会话总结 — 2026-04-20

> 本次会话完成了 **真实 FAA Chapter 18 抽取链路的清理、provider 兼容扩展、以及通过 ChatAnywhere 转发 host 跑通 extraction → validation → query**。

---

## 一、完成内容概览

| 任务 | 状态 |
|------|------|
| 清理 `data/procedures/` 中遗留/重复 txt 文件 | ✅ 完成 |
| 建立本地 Python 3.12 虚拟环境 `.venv` | ✅ 完成 |
| 修复 Windows GBK 终端输出兼容问题 | ✅ 完成 |
| 将 `01_extract.py` 改为按 `index.txt` 读取正式输入集 | ✅ 完成 |
| 增加“额度不足时不覆盖已有输出”的保护 | ✅ 完成 |
| 增加 Gemini provider 支持 | ✅ 完成 |
| 增加 `OPENAI_BASE_URL` 支持，兼容 ChatAnywhere/OpenAI-compatible 转发 | ✅ 完成 |
| 用 ChatAnywhere + `gpt-4o-mini` 跑通 35 份 FAA procedure 批量抽取 | ✅ 完成 |
| 过滤无步骤 procedure 后重新通过 SHACL 验证 | ✅ 完成 |
| 增加 normalize + dedupe 后处理并合并重复 procedure | ✅ 完成 |
| 增加 procedure / step 级 provenance 字段并跑通来源展示 | ✅ 完成 |
| 查询层 smoke test（`engine` / `--list`）通过 | ✅ 完成 |

---

## 二、本次新增 / 修改的文件

### 2.1 修改：`aviation_prototype/scripts/01_extract.py`

本次是核心改动文件，已完成以下增强：

- 支持 provider 自动选择：
  - `OPENAI_API_KEY`
  - `GEMINI_API_KEY`
- 支持 `LLM_PROVIDER` 显式指定 provider
- 支持 `MODEL_NAME` 覆盖默认模型
- 支持 `OPENAI_BASE_URL`，可接入 OpenAI-compatible 第三方转发服务
- Gemini 兼容路径使用：
  - `https://generativelanguage.googleapis.com/v1beta/openai/`
- 批量模式优先按 `data/procedures/index.txt` 的正式文件顺序读取
- 增加 JSON 清洗与解析逻辑，兼容代码块包裹输出
- 增加 procedure 归一化逻辑：过滤没有任何有效 step 的条目
- 增加额度不足保护：失败时不覆盖已有 `output/extracted.json`
- 增加 Gemini 免费层限速保护与自动重试逻辑
- 增加多文件 chunking 支持（主要为 Gemini 免费层准备）

### 2.2 修改：`aviation_prototype/scripts/02_validate.py`

- 增加 Windows GBK 终端兼容处理

### 2.3 修改：`aviation_prototype/scripts/03_query.py`

- 增加 Windows GBK 终端兼容处理

### 2.4 修改：`aviation_prototype/.env.example`

- 补充多 provider 配置示例：
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`
  - `GEMINI_API_KEY`
  - `LLM_PROVIDER`
  - `MODEL_NAME`

### 2.5 修改：`aviation_prototype/README.md`

- 文档已更新为支持：
  - OpenAI
  - Gemini
  - OpenAI-compatible 转发服务

### 2.6 归档：`aviation_prototype/data/procedures/_archive/20260420_legacy_cleanup/`

- 已将 8 个遗留/重复 txt 文件移出 active 输入目录，避免污染批量抽取

---

## 三、关键运行结果

### 3.1 输入集清理结果

当前 active 输入目录：

- `aviation_prototype/data/procedures/`
- 仅保留 `index.txt` 登记的 **35** 个正式 procedure 文件

### 3.2 ChatAnywhere 连通性验证

已验证以下模式可用：

```env
OPENAI_API_KEY=<chatanywhere_key>
OPENAI_BASE_URL=https://api.chatanywhere.tech/v1
LLM_PROVIDER=openai
MODEL_NAME=gpt-4o-mini
```

最小请求成功返回 JSON，说明该转发 host 可作为当前项目的 OpenAI-compatible provider 使用。

### 3.3 FAA 批量抽取结果

执行链路：

```bash
.\.venv\Scripts\python.exe .\scripts\01_extract.py --input-dir data/procedures
```

结果：

- 输入文件数：`35`
- provenance 版抽取后保留：`17`
- 所有保留 procedure 均包含 `source_file`
- 所有保留 step 均包含 `source_excerpt`
- Token 合计：`41,608`
  - 输入：`33,392`
  - 输出：`8,216`

### 3.4 被过滤条目

以下条目因 **没有可执行步骤**，被过滤，不进入知识图谱：

- `Abnormal Engine Instrument Indication`

原因：

- 原文更像“提示去看 AFM/POH / 图表”的说明性段落
- 不适合作为当前 schema 下的 `EmergencyProcedure`
- 若后续要保留，建议扩展 schema，而不是硬塞进现有 `ProcedureStep` 结构

### 3.5 SHACL 验证结果

重新验证后已通过：

```text
Conforms: True
紧急程序数量: 17
步骤总数: 87
警告总数: 15
RDF 三元组总数: 686
```

关键输出文件：

- [extracted.json](</E:/aviation project/aviation_prototype/output/extracted.json>)
- [kg.ttl](</E:/aviation project/aviation_prototype/output/kg.ttl>)
- [validation_report.txt](</E:/aviation project/aviation_prototype/output/validation_report.txt>)

### 3.6 查询层 smoke test

已验证：

```bash
.\.venv\Scripts\python.exe .\scripts\03_query.py --list
.\.venv\Scripts\python.exe .\scripts\03_query.py --question "engine"
```

关键结果：

- `engine` 可返回：
  - `Engine Failure After Takeoff (Single-Engine)`
  - `Engine Fire`
- `--list` 可稳定列出当前图谱中的 17 个 procedure，并显示来源文件 / 章节
- `--question "engine"` 可显示 procedure 级来源与 step 级依据摘录

---

## 四、当前图谱中的 procedure（17 个）

- Tree Landing
- Water Ditching
- Snow Landing
- Engine Failure After Takeoff (Single-Engine)
- Emergency Descent
- Engine Fire
- Electrical Fire
- Cabin Fire
- Total Flap Failure
- Asymmetric Split Flap
- Loss of Elevator Control - Up Cable Failure
- Loss of Elevator Control - Down Cable Failure
- Landing Gear Malfunction
- Electrical System Failure
- Inadvertent Door Opening In-Flight
- Inadvertent VFR Flight Into IMC
- Emergency Autoland

> 注意：provenance 版 prompt 更保守，当前 recall 下降到了 17 个 procedure。
> 结构质量和可解释性提升了，但召回率需要下一步继续优化。

---

## 五、当前推荐运行方式

统一使用虚拟环境，不要使用系统默认 `python`（机器默认指向 Python 2.7）：

```bash
E:\aviation project\aviation_prototype\.venv\Scripts\python.exe
```

推荐在 `aviation_prototype/` 下运行：

```bash
.\.venv\Scripts\python.exe .\scripts\01_extract.py --input-dir data/procedures
.\.venv\Scripts\python.exe .\scripts\02_validate.py
.\.venv\Scripts\python.exe .\scripts\03_query.py --list
.\.venv\Scripts\python.exe .\scripts\03_query.py --question "engine"
```

---

## 六、环境配置建议

### 6.1 ChatAnywhere 转发方案（本次已验证）

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.chatanywhere.tech/v1
LLM_PROVIDER=openai
MODEL_NAME=gpt-4o-mini
GEMINI_API_KEY=
```

### 6.2 Gemini 方案（代码已支持）

```env
GEMINI_API_KEY=
LLM_PROVIDER=gemini
MODEL_NAME=gemini-2.5-flash
OPENAI_API_KEY=
OPENAI_BASE_URL=
```

---

## 七、未完成 / 已知问题

### 7.1 抽取质量仍有提升空间

当前 extraction 已经可用，但仍存在这些问题：

- provenance 版 prompt 导致 recall 下降，一些 procedure 未被保留
- 某些 narrative 段落没有被抽成 procedure（例如部分概述类文本）
- 某些 procedure 可能拆分得不够细
- 某些步骤仍偏“说明性”而非纯 checklist 风格

### 7.2 重复项去重已做第一版，但仍可继续增强

当前已经实现：

- 按 procedure name 的规范化键做合并
- step 去重与重编号
- warning 去重

后续仍可增强：

- 更细粒度的语义去重（不仅看 name）
- 相似 action 合并
- trigger_condition 的更自然合并策略

### 7.3 Provenance 已接入，但仍可增强

当前已实现：

- `EmergencyProcedure.source_file`
- `EmergencyProcedure.source_section`
- `EmergencyProcedure.source_excerpt`
- `ProcedureStep.source_excerpt`

当前 provenance 来源：

- 优先使用模型抽取结果
- 缺失时由本地启发式从原文中回填最接近的摘录

后续可增强：

- 页面级 provenance（PDF page）
- 行号 / chunk id
- warning 级 provenance
- 更好的 excerpt 对齐算法

### 7.4 本体边界问题

`Abnormal Engine Instrument Indication` 暴露了 schema 边界：

- 当前 schema 只适合“带明确可执行步骤”的 procedure
- 不适合“参考 POH / 查看表格 / 诊断性说明”类内容

后续如果要保留这类知识，建议新增类型，例如：

- `ReferenceProcedure`
- `DiagnosticGuidance`
- `AbnormalConditionNote`

---

## 八、建议的下一步

优先级建议如下：

### 8.1 优先做 extraction recall 优化

- 调整 provenance prompt，降低过度保守过滤
- 对“说明 + procedure 混合段落”做更稳的抽取策略
- 必要时分成两阶段：
  1. 先抽 procedure / steps
  2. 再补 provenance

### 8.2 持续做 extraction 后处理优化

- procedure 去重
- 低质量步骤清洗
- provenance excerpt 合并优化

### 8.3 再做 Hybrid RAG 第一版

基于当前已通过 SHACL 的 `kg.ttl`：

- 加入向量检索（ChromaDB）
- 保持 SPARQL 查询层
- 实现 KG + Vector 双通道检索

### 8.4 最后再做 Agent 编排层

- LangGraph / 状态机
- 意图识别
- 检索策略选择
- 格式化建议输出

---

## 九、压缩上下文说明

后续继续本项目时，优先把这份文件当作“压缩上下文入口”：

- 本次会话的关键实现、现状、配置和风险都已写入本文件
- 后续无需重新回放整段对话，只需要从这里继续

---

## 十、安全说明

本次会话中出现过多个真实 API key。

建议：

- 立即 rotate / 删除所有已在对话中暴露过的 key
- 在任何后续 md、代码或日志中都不要保存真实 key
- `.env` 只保留本地使用，不要提交到版本库

---

*生成于 2026-04-20 · Claude Code 会话*
