# 窑炉见证锥序位证据：基线契约

## 数据流程

把模拟票据转换成架位的序位集合和证据，供配方目标带数据分析。 输入字段以 `examples/demo.json`（单架报告）和 `examples/archive.json`（包/架归档）为最小可运行的实际示例。

模拟序位从 0 到 `rank_ceiling`；倒伏提供下界，直立提供上界，弯曲限制在相邻两级，未读不提供约束。不是温度、工程或安全建议。

### 单架报告

每架独立：`interval` 是读数约束的交集，`evidence` 保留给出下界、上界和未读的票据，`status` 按目标带分为 `inside`/`outside`/`below`/`above`/`undetermined`/`contradictory`。

### 包/架归档

- 每个包带读数与候选架，每个架带自己的配方带；每包每架恰好使用一次。
- 交接票 `{ticket, bundle, rack, low, high}` 只收紧它点名的那个配对，要求该包归到该架时的序位落在 `[low, high]`。
- 全量可对账：只列至少能参与一次完整归属的配对和它真正允许的序位；给出 `in_band_count` 的最小/最大值和两套可重放的完整取值。
- 不可全量对账：`causes` 区分包自身矛盾、交接区间排空可行配对、边可用但互相抢架；前两类给出原读数与交接票证，第三类给出需求/供给及候选边。
- 每架“可在带内/可在带外”的结论都来自完整归属，不借用不完整归属。
- 求解只用二部图匹配、交替图（Kosaraju）和最小费用完美匹配，支持约 100 包/100 架/3000 条候选配对，不枚举排列。

## 责任边界

命令入口只处理文件输入和退出码。`pipeline.py` 分派两种文档；`archive.py` 负责包/架归属与失败诊断；`intake.py` 校验并归一化输入；`ordinal.py` 定义读数与区间语义；`matching.py` 提供图算法。生产代码：`coneread/__main__.py`, `coneread/intake.py`, `coneread/ordinal.py`, `coneread/pipeline.py`, `coneread/archive.py`, `coneread/matching.py`。

## 验证与边界

运行 `python3 -B examples/smoke.py`。样例经过真实生产入口，既核对核心数据结果也核对非零退出码及不输出部分数据的约束，并覆盖归档的全量对账与三类失败诊断。不安装第三方依赖，不提交未来题目、答案、隐藏测试或评审材料。
