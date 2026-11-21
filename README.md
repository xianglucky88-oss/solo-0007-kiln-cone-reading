# 窑炉见证锥序位证据

把模拟票据转换成架位的序位集合和证据，供配方目标带数据分析。 这是处理合成数据的离线参考应用，不依赖网络、数据库服务或第三方库。

```sh
python3 -B -m coneread examples/demo.json
python3 -B examples/smoke.py
```

需要 Python 3.9+。传入任意匹配契约的 UTF-8 JSON 文件，输出 JSON 写到标准输出；非法输入使用退出码 2，诊断写到标准错误。业务上发现冲突仍会产生完整分析结果。完整测试套件暂缓；随仓冒烟样例从实际命令行入口验证有效结果与输入拒绝。

模拟序位从 0 到 `rank_ceiling`；倒伏提供下界，直立提供上界，弯曲限制在相邻两级，未读不提供约束。不是温度、工程或安全建议。 详见 [项目说明](PROJECT_SPEC.md) 和 [输入样例](examples/demo.json)。

## 锥目录迁移

历史票据沿用旧目录，迁移以显式旧码→新码对应为准；未配对的旧码仅在新目录仍存在同名码时按同名回退沿用，否则记为新侧不可解释，缺码票不按未读票处理。新目录允许合码，但每张原票 ID 与逐票约束都保留。

```sh
python3 -B -m coneread.migration examples/migration_old.json examples/migration_spec.json
python3 -B -m coneread.migration examples/migration_old.json examples/migration_spec.json examples/correction_mapping.json
python3 -B examples/migration_smoke.py
```

迁移说明是独立文件（`new_cone_ranks`、`explicit_mapping`，可另选 `new_rank_ceiling`、`new_band`），旧输入文档与合同不变。正式报告同时给出旧侧与新侧的配方带裁定、架位端点及逐票约束差异；约束变了但端点或裁定未动也有显式标记。无法完成的一侧仍输出报告，缺码票在 `missing_tickets` 与架位 `complete=false` 中列出。

第三个参数是归档员的一条更正（映射更正或新码序位更正）。更正报告列出直接受影响和经回退映射受影响的旧票、实际重算的架位、未引用相关码而不重扫的架位、与正式迁移报告的差异，以及与整份更正目录全量重放的一致性核对。
