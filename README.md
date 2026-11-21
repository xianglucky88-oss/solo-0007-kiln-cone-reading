# 窑炉见证锥序位证据

把模拟票据转换成架位的序位集合和证据，供配方目标带数据分析。 这是处理合成数据的离线参考应用，不依赖网络、数据库服务或第三方库。

```sh
python3 -B -m coneread examples/demo.json
python3 -B -m coneread examples/archive.json
python3 -B examples/smoke.py
```

需要 Python 3.9+。传入任意匹配契约的 UTF-8 JSON 文件，输出 JSON 写到标准输出；非法输入使用退出码 2，诊断写到标准错误。业务上发现冲突仍会产生完整分析结果。完整测试套件暂缓；随仓冒烟样例从实际命令行入口验证有效结果与输入拒绝。

模拟序位从 0 到 `rank_ceiling`；倒伏提供下界，直立提供上界，弯曲限制在相邻两级，未读不提供约束。不是温度、工程或安全建议。

## 两种文档

### 单架报告（`examples/demo.json`）

每架独立计算证据，输出 `interval`、`status` 和 `evidence`。架与架之间不共享包，不做归属。

### 包/架归档（`examples/archive.json`）

每个包（`bundles`）恰好归到一个架，每个架恰好用一个包：

- 包带一份自己的读数（`witnesses`）和若干候选架（`candidates`）；
- 每个架带自己的配方目标带 `band`；
- `handoffs` 逐条给出少量交接票：`{ticket, bundle, rack, low, high}`，限定该包**若**归到该架时序位必须落在整数闭区间 `[low, high]` 内。

交接票只收紧它点名的那一个配对；同一个包换到别的架时可用序位可以完全不同。

可全量对账时输出 `status: "full"`：

- `pairings`：只列至少能参与一次完整归属的配对，及该配对真正允许的序位闭区间；
- `rack_outlook`：每架“可在带内/可在带外”的结论及支撑它的包列表；
- `in_band_count`：全炉同时落在各自带内的架数最小值和最大值；
- `minimum_assignment` / `maximum_assignment`：两套可重放的完整取值，逐架给出所包、序位、是否在带内和该配对的区间。

不可全量对账时输出 `status: "impossible"`，用 `causes` 区分三类互不替代的原因：

- `bundle_self_contradiction`：包自身读数已互相矛盾（含原读数和冲突上下界）；
- `handoff_emptied_pairing`：交接区间把原本可行的配对排空（含原读数区间、双方交接票）；
- `rack_contention`：边各自可用但互相抢架（含需求/供给和候选边）。

规模上限按 100 个包、100 个架和 3000 条候选配对设计；归属用二部图匹配、交替图和最小费用完美匹配求解，不枚举排列。 详见 [项目说明](PROJECT_SPEC.md)。
