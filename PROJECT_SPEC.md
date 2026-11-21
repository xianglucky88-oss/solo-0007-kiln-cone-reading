# 窑炉见证锥序位证据：契约

## 数据流程

把模拟票据转换成架位的序位集合和证据，供配方目标带数据分析。 输入字段以 `examples/demo.json`（旧单票模式）和 `examples/archive.json`（新归档模式）为最小可运行的实际示例。

模拟序位从 0 到 `rank_ceiling`；倒伏提供下界，直立提供上界，弯曲限制在相邻两级，未读不提供约束。不是温度、工程或安全建议。

## 两种模式

**旧单票模式**（`demo.json`，无 `version`／`budget`）：每架每锥至多一张票，输出 `target_band` 与各架的 `interval`、`status`、`evidence`。行为与基线逐字节一致。

**新归档模式**（`version: 2`）：同锥多张独立票；每架 `budget`（别名 `k`／`discard`）为可丢弃的可读票上限，未读票不占预算。可行集合按精确闭段输出；每段都给出两端的 `support`／`conflicts`／`blocking` 证据。集合按目标带整体分类，两侧均有可行值而带内无值时单列 `straddling`。

**复判重算**：把报告中的 `archive` 快照与 `amendments`（`corrections` 按票号改读数／锥，`retractions` 撤回）一并输入；恢复只依赖快照，不读旧采集文件。只重算被涉及的架位，`changes` 汇报新增/消失范围、状态变化、端点证据变化（包括范围未动的情形）与 `unchanged`。

## 责任边界

命令入口只处理文件输入和退出码。`pipeline.py` 协调校验、模式分派、数据计算和报告；`intake.py` 负责输入、快照与复判批次校验；`ordinal.py` 负责序位语义。生产代码：`coneread/__main__.py`, `coneread/intake.py`, `coneread/ordinal.py`, `coneread/pipeline.py`。

## 验证与边界

运行 `python3 -B examples/smoke.py`。样例经过真实生产入口，既核对核心数据结果也核对非零退出码及不输出部分数据的约束，并覆盖归档与复判重算。不安装第三方依赖，不提交未来题目、答案、隐藏测试或评审材料。
