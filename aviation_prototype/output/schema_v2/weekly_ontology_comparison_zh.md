# 本周 Ontology 对比实验结论

## 任务目标

本周任务是根据论文 `Towards Automated Ontology Generation from Unstructured Text: A Multi-Agent LLM Approach` 的方法，生成一版新的 ontology，并和当前工程已有 ontology 对比：

- 如果变好了，说明哪里变好了。
- 如果没有明显变好，说明原因。

## 实验设计

我没有直接用 LLM 自由生成的 ontology 替换当前工程 ontology。原因是第一轮 raw candidate 出现了明显建模错误，例如：

```text
ProcedureStep is_a EmergencyProcedure
```

这个关系是错误的。正确关系应该是：

```text
EmergencyProcedure has_step ProcedureStep
```

所以最终采用的是“论文方法 + 工程约束”的受控实验：

1. 用论文方法生成 35 个 competency questions。
2. 用 multi-agent 方法生成候选 ontology。
3. 人工约束并修正候选 ontology 中的明显错误。
4. 得到 controlled ontology v2。
5. 将当前 `extracted.json` 确定性迁移到 v2。
6. 比较 v1 ontology 和 v2 ontology。

## 新增文件

- `schema/emergency_schema_v2.yaml`
- `shacl/procedure_shapes_v2.ttl`
- `scripts/09_migrate_to_schema_v2.py`
- `scripts/10_compare_ontology_versions.py`
- `output/schema_v2/extracted_v2.json`
- `output/schema_v2/kg_v2.ttl`
- `output/schema_v2/ontology_v1_vs_v2_report.md`
- `output/schema_v2/ontology_v1_vs_v2_report.details.json`

## 当前 V1 Ontology

当前 ontology 更像一个工程可运行 schema。

核心结构：

```text
EmergencyProcedure
ProcedureStep
Warning
StepType
```

优点：

- 已经能支持 extraction。
- 已经能转换为 RDF KG。
- 已经通过 SHACL。
- 已经接入 Hybrid RAG 和 UI。
- 已经能区分 `immediate_action`、`caution`、`training_note`、`background`。

不足：

- ontology 层次较薄。
- `source_file/source_section/source_excerpt` 只是字符串字段，不是一等对象。
- 没有显式建模 `Hazard`、`AircraftState`、`AircraftSystem`、`TriggerCondition`。
- 不够接近论文中强调的 event/state/hazard/provenance ontology structure。

## Controlled V2 Ontology

Controlled v2 保留当前可运行结构，同时新增论文方法启发出的概念层：

```text
EmergencyProcedure
ProcedureStep
Warning
SourceEvidence
TriggerCondition
FlightPhase
Hazard
AircraftState
AircraftSystem
```

关键变化：

- `SourceEvidence` 成为一等对象。
- `TriggerCondition` 成为结构化对象。
- `Hazard` 从 warning 文本中显式抽出。
- `AircraftSystem` 用于表达 engine、electrical system、landing gear、pitot-static system 等系统。
- `AircraftState` 用于表达 IMC、engine failure、gear malfunction 等状态。
- `ProcedureStep` 保持为 procedure 的组成部分，不再错误建成子类。

## 结构对比

| 指标 | V1 | Controlled V2 |
|---|---:|---:|
| Classes | 4 | 10 |
| Attributes | 15 | 33 |
| Required attributes | 7 | 14 |
| Enums | 1 | 1 |
| RDF triples | 818 | 2611 |
| SHACL | PASS | PASS |

V2 KG 中新增实例：

| 类型 | 数量 |
|---|---:|
| SourceEvidence | 218 |
| Hazard | 70 |
| AircraftSystem | 101 |
| TriggerCondition | 18 |
| AircraftState | 18 |
| FlightPhase | 18 |

这说明 v2 的 ontology 表示能力明显增强了。

## CQ Proxy 结果

使用论文方法生成的 35 个 CQ 做 deterministic proxy evaluation。

| 指标 | V1 | Controlled V2 |
|---|---:|---:|
| Avg expected-answer recall | 0.611 | 0.619 |
| Answer recall >= 0.5 | 23/35 | 23/35 |
| Avg question-term recall | 0.480 | 0.480 |
| Avg schema concept recall | 0.237 | 0.203 |
| Avg schema relation recall | 0.041 | 0.056 |
| Avg KG concept recall | 0.754 | 0.754 |

解释：

- V2 的答案覆盖只小幅提升：`0.611 -> 0.619`。
- V2 的 relation recall 有小幅提升：`0.041 -> 0.056`。
- V2 的 KG concept recall 没变，因为它迁移自同一份 `extracted.json`，事实内容没有重新抽取。
- V2 的 schema concept recall 没有上升，说明 schema 变丰富不等于和 CQ 用词完全一致。

## 是否变好了？

结论：**结构上变好了，功能回答能力暂时没有显著变好。**

### 变好的地方

V2 在 ontology 设计层面明显更好：

- provenance 更清楚：`SourceEvidence` 独立成对象。
- 风险表达更强：新增 `Hazard`。
- 系统表达更强：新增 `AircraftSystem`。
- 状态表达更强：新增 `AircraftState`。
- 触发条件表达更强：新增 `TriggerCondition`。
- 仍然保留现有工程需要的 procedure/step/warning/step_type。
- v2 KG 通过 SHACL，说明它不是不可运行的抽象设计。

### 没有明显变好的地方

V2 的回答能力没有显著变好，原因是：

- 这次是 deterministic migration，没有重新从 FAA 文本抽取新知识。
- V2 增强的是“知识表示方式”，不是“事实覆盖范围”。
- hazard/system/state 目前是规则推断，质量不如人工或 LLM 重新抽取。
- CQ proxy 不是完整 SPARQL/RAG/LLM judge，所以还不能证明最终问答能力显著提升。

## 为什么符合论文结果？

论文结果本身也不是说 multi-agent ontology generation 已经完美。

论文的主要结论是：

- multi-agent 明显提升 structural quality。
- RAG CQ coverage 有提升。
- 但 SPARQL CQ coverage 仍然只有约 40%-63%。
- 论文也承认结构质量和可执行查询能力并不完全一致。

我们的结果和论文一致：

```text
结构表示能力提升明显
但 CQ/问答能力没有自动大幅提升
```

## 最终判断

当前 V1 仍然更适合作为 demo 和 production prototype 的默认 schema。

Controlled V2 更适合作为下一阶段 ontology 设计目标。

不建议直接替换当前 schema。建议增量合并：

1. 先引入 `SourceEvidence`。
2. 再引入 `Hazard`。
3. 再引入 `AircraftSystem` 和 `AircraftState`。
4. 最后把 `trigger_condition` 升级为 `TriggerCondition`，但保留文本字段兼容检索。

## 下一步建议

下一步应该做真正的 CQ benchmark：

```text
35 CQs
  -> V1 KG 查询
  -> V2 KG 查询
  -> answer
  -> expected_answer 对比
```

如果 V2 在真实 CQ 查询上提升，再把 v2 schema 接入 `01_extract.py` 和 Hybrid RAG。

现在的结论是：

```text
论文方法对 ontology 设计有帮助；
Controlled V2 在结构上优于 V1；
但因为没有重新抽取事实，功能回答能力暂时没有显著提升。
```
