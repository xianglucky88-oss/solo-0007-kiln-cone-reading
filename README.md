# 窑炉见证锥序位证据

把模拟票据转换成架位的序位集合和证据，供配方目标带数据分析。 这是处理合成数据的离线参考应用，不依赖网络、数据库服务或第三方库。

```sh
python3 -B -m coneread examples/demo.json      # 旧单票模式
python3 -B -m coneread examples/archive.json   # 新归档模式
python3 -B examples/smoke.py
```

需要 Python 3.9+。传入任意匹配契约的 UTF-8 JSON 文件，输出 JSON 写到标准输出；非法输入使用退出码 2，诊断写到标准错误。业务上发现冲突仍会产生完整分析结果。完整测试套件暂缓；随仓冒烟样例从实际命令行入口验证有效结果与输入拒绝，以及归档重算。

模拟序位从 0 到 `rank_ceiling`；倒伏提供下界，直立提供上界，弯曲限制在相邻两级，未读不提供约束。不是温度、工程或安全建议。

## 新归档模式

`version: 2`（或带 `budget`／`discard`）启用多票归档。同一锥可有任意多张独立票，每架用 `budget`（也可写作 `k`／`discard`，缺省取文档级 `budget`，否则为 0）限制**可丢弃的可读票**数量；`unreadable` 票不占预算、也不产生约束。

一个架位的可行集合是「最多丢弃 `budget` 张可读票后仍成立的序位」的全部取值，按精确闭段输出到 `segments`。每段两端的证据分别列出：

- `support`：边界恰好等于该端序位的票；
- `conflicts`：在该端被丢弃的票（至多 `budget` 张）；
- `blocking`：恰好挡住下一格的票，说明该段为何到此为止。

集合整体按目标带分类为 `inside`／`below`／`above`／`undetermined`／`contradictory`；两侧都有可行值而带内一个都没有时单列为 `straddling`。

## 复判与重算

报告里的 `archive` 字段就是继续核查所需的完整快照（不需要旧采集文件）。把它连同按票号的 `amendments`（`corrections` 改读数／锥，`retractions` 撤回）再次输入即可重算：

```json
{"archive": {...}, "amendments": {"corrections": [{"ticket": "x", "reading": "bending"}],
                                   "retractions": ["y"]}}
```

输出只重算被涉及到的架位（`touched`），`changes` 交代新增/消失的可行范围、状态变化、范围未动但端点证据变化的情形，以及是否为 `unchanged`；其余架位仅在刷新的 `archive` 中带过，不重新分析。

详见 [项目说明](PROJECT_SPEC.md)、[旧样例](examples/demo.json) 与 [归档样例](examples/archive.json)。
