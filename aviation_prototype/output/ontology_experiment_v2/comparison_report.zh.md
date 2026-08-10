# Ontology 提取实验对比结论

生成时间：2026-05-12

本次实验按论文提出的 artifact-driven multi-agent 方法执行：

1. Domain Expert：从 FAA emergency procedure 文本生成 competency questions 和领域概念。
2. Manager：根据 CQ 生成 ontology 规划。
3. Coder：把规划转成候选 ontology。
4. QA：检查候选 ontology 的覆盖、结构和可落地性。

## 产物位置

- `domain_cqs.json`：35 个 competency questions。
- `ontology_plan.json`：Manager 生成的本体规划。
- `candidate_ontology.json`：候选 ontology 结构化 JSON。
- `candidate_schema.yaml`：候选 LinkML-style schema。
- `candidate_ontology.ttl`：候选 OWL/Turtle ontology。
- `qa_review.json`：QA 智能体评审结果。
- `comparison_report.md`：自动生成的英文对比报告。

## 当前工程 Ontology

当前工程的 ontology 更像一个可运行的 extraction/KG schema：

- LinkML classes：4
- LinkML attributes：14
- Required attributes：7
- KG triples：818
- KG instances：
  - EmergencyProcedure：18
  - ProcedureStep：89
  - Warning：23

核心优点：

- 已经和现有 extraction、SHACL、KG、Hybrid RAG、UI 全部打通。
- `ProcedureStep.step_type` 已经能区分 `immediate_action`、`caution`、`training_note`、`background`。
- `source_file`、`source_section`、`source_excerpt` 已经支持 grounding/provenance。
- 已通过 SHACL 验证，可以直接支撑当前 demo。

主要不足：

- 本体层次较薄，更多是数据 schema，而不是完整 ontology。
- 没有显式建模 `Hazard`、`AircraftState`、`AircraftSystem`、`EmergencyEvent`、`TriggerCondition` 等概念。
- CQ 层尚未进入正式评估流程，因此“能回答哪些本体能力问题”还没有被系统化表达。

## 论文方法提取出的候选 Ontology

v2 候选 ontology 提取结果：

- Classes：11
- Object properties：9
- Enums：1
- Validation rules：3
- Domain Expert CQs：35
- QA major/blocker issues：1 个 major

候选 classes：

- `EmergencyProcedure`
- `ProcedureStep`
- `Warning`
- `SourceEvidence`
- `TriggerCondition`
- `FlightPhase`
- `Hazard`
- `AircraftState`
- `AircraftSystem`
- `EmergencyEvent`
- `PilotAction`

这版比 v1 明显更接近当前工程需求，因为它保留了 procedure/step/warning，同时补出了更 ontology-like 的概念层。

## 好的地方

候选 ontology 值得吸收的部分：

- `SourceEvidence`：可以把 provenance 从普通字符串提升为一等对象，支持多个证据片段、页码、章节、来源类型等。
- `Hazard`：可以让 warning 不只是文本，而是和 hazard/risk 显式关联。
- `AircraftState`：适合表达 IMC、engine failure、electrical failure、gear malfunction 等状态。
- `AircraftSystem`：适合表达 engine、electrical system、landing gear、pitot-static system、flaps 等系统。
- `EmergencyEvent` / `TriggerCondition`：可以把“触发了什么 procedure”从字符串升级为可查询事件/条件。
- `StepType` enum：和当前工程已有 `step_type` 方向一致，说明论文方法也发现了这层分类的重要性。

## 不好的地方

候选 ontology 不能直接替换当前 ontology，原因：

- `ProcedureStep` 被导成了 `EmergencyProcedure` 的子类，这是错误建模。Step 应该是 procedure 的组成部分，而不是一种 procedure。
- `Warning` 只连接到 `Hazard`，没有明确挂回 `EmergencyProcedure`，会影响当前 UI 和 RAG 输出。
- `SourceEvidence` 只有 `evidence_source`，没有当前工程已经需要的 `source_file`、`source_section`、`source_excerpt`。
- 候选 schema 缺少 `expected_result`，会损失当前 advisor 输出中的执行结果信息。
- 候选 ontology 的 validation rules 太少，不能替代当前 SHACL。
- 它声明 CQ coverage 为 `8/8`，但 Domain Expert 实际生成了 35 个 CQ，说明候选 ontology 的 CQ 覆盖统计还不够可靠。

## 结论

当前 ontology 更适合继续支撑 demo 和工程运行。

论文方法提取出的候选 ontology 更适合作为下一版 schema 设计参考，而不是直接替换现有 schema。

最合理的路线是：保留当前 `EmergencyProcedure -> ProcedureStep -> Warning -> SourceEvidence string fields` 的稳定结构，然后增量吸收候选 ontology 的几个概念层：

1. 增加 `SourceEvidence` 对象。
2. 增加 `Hazard` 对象，并让 `Warning` 指向 `Hazard`。
3. 增加 `AircraftState` 和 `AircraftSystem`。
4. 把 `trigger_condition` 从纯字符串升级为 `TriggerCondition`，但保留字符串摘要字段以兼容检索。
5. 建立 CQ-based evaluation，用 35 个 CQ 检查 KG/SPARQL/Hybrid RAG 的回答能力。

## 推荐下一步

不要直接替换当前 ontology。

建议先做一个小的 v2 schema：

```text
EmergencyProcedure
  - name
  - trigger_condition_text
  - trigger_condition -> TriggerCondition
  - aircraft_phase
  - steps -> ProcedureStep[]
  - warnings -> Warning[]
  - evidence -> SourceEvidence[]

ProcedureStep
  - step_number
  - step_type
  - action
  - expected_result
  - evidence -> SourceEvidence

Warning
  - description
  - hazard -> Hazard
  - evidence -> SourceEvidence

SourceEvidence
  - source_file
  - source_section
  - source_excerpt

Hazard
  - name
  - description
  - affected_system -> AircraftSystem

TriggerCondition
  - description
  - aircraft_state -> AircraftState
```

这样既保留当前工程可运行的部分，又吸收论文方法带来的 ontology 层次。
