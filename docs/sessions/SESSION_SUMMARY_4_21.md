# 工作会话总结 - 2026-04-21

> 本次会话是在 [SESSION_SUMMARY_4_20.md](</E:/aviation project/SESSION_SUMMARY_4_20.md>) 基础上的继续推进，重点处理 provenance 版抽取后的 3 个高优先级质量问题：
> `Snow Landing` 过度压缩、`Inadvertent VFR Flight Into IMC` 缺步骤、`Ballistic Parachute Deployment` 消失。

---

## 一、这次做了什么

### 1. 新增定点重抽脚本

新增文件：
- [04_targeted_reextract.py](</E:/aviation project/aviation_prototype/scripts/04_targeted_reextract.py>)

作用：
- 只重抽少数低质量 / 漏抽的目标文件
- 不重跑整个 35 文件语料库
- 将修复结果合并回 [extracted.json](</E:/aviation project/aviation_prototype/output/extracted.json>)

这次脚本新增了两类能力：
- 单文件重抽
- 分组重抽

其中最关键的是分组重抽：
- `imc_bundle`
- 覆盖 `24` 到 `31` 号文件
- 把被 PDF parser 拆散的 IMC 子章节重新视作一个完整 procedure 来抽取

---

## 二、关键发现

### 1. IMC 不是“模型抽坏了”，而是“输入切得太碎了”

之前 `Inadvertent VFR Flight Into IMC` 只有 3 步，不是因为模型不会抽，而是因为：
- [24_inadvertent_vfr_flight_into_imc.txt](</E:/aviation project/aviation_prototype/data/procedures/24_inadvertent_vfr_flight_into_imc.txt>) 只包含导言和 first steps
- 真正的控制动作被拆到后续文件：
  - [25_maintaining_airplane_control.txt](</E:/aviation project/aviation_prototype/data/procedures/25_maintaining_airplane_control.txt>)
  - [26_attitude_control.txt](</E:/aviation project/aviation_prototype/data/procedures/26_attitude_control.txt>)
  - [27_turns.txt](</E:/aviation project/aviation_prototype/data/procedures/27_turns.txt>)
  - [28_climbs.txt](</E:/aviation project/aviation_prototype/data/procedures/28_climbs.txt>)
  - [29_descents.txt](</E:/aviation project/aviation_prototype/data/procedures/29_descents.txt>)
  - [30_combined_maneuvers.txt](</E:/aviation project/aviation_prototype/data/procedures/30_combined_maneuvers.txt>)
  - [31_transition_to_visual_flight.txt](</E:/aviation project/aviation_prototype/data/procedures/31_transition_to_visual_flight.txt>)

结论：
- 这类内容不能只做“单文件重抽”
- 必须做“分组目标重抽”

### 2. merge 逻辑需要按 source_file 重叠替换

由于 IMC 修复后一个 procedure 的 `source_file` 会变成多文件合并值：

```text
24_...txt | 25_...txt | 26_...txt | ...
```

旧的“按单个 source_file 精确相等替换”逻辑不够用了。  
这次已经改成：
- 只要旧条目的 `source_file` 与目标文件集合有重叠
- 就把它替换掉

这样不会残留旧版 IMC 条目。

---

## 三、定点重抽后的最终状态

### 1. 当前最终结果

重新定点重抽并合并后：
- procedure 数量：`18`
- steps 总数：`99`
- warnings 总数：`19`
- RDF triples：`777`
- SHACL：`PASS`

对应输出：
- [extracted.json](</E:/aviation project/aviation_prototype/output/extracted.json>)
- [kg.ttl](</E:/aviation project/aviation_prototype/output/kg.ttl>)
- [validation_report.txt](</E:/aviation project/aviation_prototype/output/validation_report.txt>)

### 2. 三个重点修复项

#### `Snow Landing`
- 之前：`1` 步
- 现在：`3` 步
- 状态：可接受

当前包含：
1. 像 water ditching 一样执行 snow landing
2. 使用与 water landing 相同构型
3. 注意 reduced visibility / white out 下的 depth perception 风险

#### `Inadvertent VFR Flight Into IMC`
- 之前：`3` 步
- 现在：`8` 步
- 状态：明显改善

当前 provenance：
- `source_file` 为 `24-31` 多文件合并

当前已覆盖：
- 识别并接受紧急状态
- 用仪表保持控制
- trim 到 hands-off level flight
- 用 fingertip pressure 保持机翼水平
- 小幅、平滑姿态变化
- 温和爬升
- 避免 over-controlling
- 必要时请求 ATC 协助

说明：
- 这已经比旧版 3 步强很多
- 但如果后面要继续做高保真 checklist，还可以再细化 turn / descent / transition to visual flight 的独立动作

#### `Ballistic Parachute Deployment`
- 之前：在 provenance 版结果中消失
- 现在：已恢复，`4` 步
- 状态：已找回

当前包含：
1. 乘客 deployment 条件 brief
2. 告知 deployment sequence
3. 遵循 manufacturer / supplier guidance
4. 落地后按 evacuation procedure 撤离

---

## 四、查询验证结果

这次重新验证了：

```bash
.\.venv\Scripts\python.exe .\scripts\02_validate.py
.\.venv\Scripts\python.exe .\scripts\03_query.py --question "imc"
.\.venv\Scripts\python.exe .\scripts\03_query.py --question "ballistic"
.\.venv\Scripts\python.exe .\scripts\03_query.py --question "snow"
.\.venv\Scripts\python.exe .\scripts\03_query.py --list
```

确认结果：
- `imc` 可查到 8 步版本
- `ballistic` 可查到恢复后的 procedure
- `snow` 可查到 3 步版本
- `--list` 当前稳定显示 18 个 procedure

---

## 五、当前图谱中的 procedure（18 个）

- Asymmetric Split Flap
- Ballistic Parachute Deployment
- Cabin Fire
- Electrical Fire
- Electrical System Failure
- Emergency Autoland
- Emergency Descent
- Engine Failure After Takeoff (Single-Engine)
- Engine Fire
- Inadvertent Door Opening In-Flight
- Inadvertent VFR Flight Into IMC
- Landing Gear Malfunction
- Loss of Elevator Control - Down Cable Failure
- Loss of Elevator Control - Up Cable Failure
- Snow Landing
- Total Flap Failure
- Tree Landing
- Water Ditching

---

## 六、现在最合理的下一步

### 选项 A：继续做抽取质量优化

适合如果你想先把 KG 质量继续打磨到更稳：
- 继续细化 IMC 的步骤粒度
- 改进 `source_excerpt` 的选取质量
- 考虑给 `ProcedureStep` 增加 `source_file`

### 选项 B：开始做 Hybrid RAG 第一版

适合如果你想往 advisor / instance 继续推进：
- 保留当前 KG + SHACL 这条线
- 加一层向量检索
- 做 `KG + vector` 双通道召回

当前我更推荐：
- **直接开始 Hybrid RAG 第一版**

原因：
- 当前 18 个 procedure 已经能支撑第一版 retrieval prototype
- 局部质量问题已经从“阻塞”降到“可迭代优化”

---

## 七、运行提醒

统一使用：

```bash
E:\aviation project\aviation_prototype\.venv\Scripts\python.exe
```

不要用系统默认 `python`，因为这台机器默认仍指向 `Python 2.7`。

---

## 八、安全提醒

本次和上次会话里都出现过真实 API key。  
建议：
- 立即 rotate / 删除所有已经在对话中暴露过的 key
- `.env` 只保留本地使用，不要提交到版本库

---

*生成于 2026-04-21 - Codex 会话*
