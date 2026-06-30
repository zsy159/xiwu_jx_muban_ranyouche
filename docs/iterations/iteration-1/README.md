# 迭代 1：数据接入 + 汇总枢纽 F/G/H 列打通

> 对应总规划：[迭代文档.md § 迭代 1](../../迭代文档.md)

## 目标

证明「公式 → 算子 → 流水线 → 对账」闭环可行。

## 任务清单

| # | 任务 | 交付物 | 状态 |
|---|------|--------|------|
| 1 | `data_loader` 扩展 | `WorkbookLoader`、任务表 C/Y/Z 列读取 | ✅ |
| 2 | 算子 v1 | `sumif_by_key`、`ratio_with_cap` + `tests/test_ops.py` | ✅ |
| 3 | 汇总枢纽指标 | `HubTaskMetricsCalculator`（F/G/H） | ✅ |
| 4 | 骨架行 | `SummarySkeletonModule`（仅 keys，迭代 1 bootstrap） | ✅ |
| 5 | 列级对账 | `parity.columns` 限定三列 | ✅ |

## 已实现公式模式

| 列 | Excel 模式 | 实现 |
|----|-----------|------|
| F 考核量 | `SUMIF(销售任务及完成率!C:C, Dn, !Y:Y)` | `sumif_by_key` |
| F | `=销售任务及完成率!Y23` 等单格引用 | `read_cell_value` |
| G 实际销量 | `SUMIF(...!Z:Z)` | `sumif_by_key` |
| H 销量完成率 | `IF(F<>0, IF(G/F>120%, 120%, G/F), 0)` | `ratio_with_cap(1.2)` |
| H | `>110%` 变体 | `ratio_with_cap(1.1)` |

**未覆盖（迭代 2）：** 小计行 `SUM(F3:F14)`、跨行引用 `=F106`、静态值（无公式）、其他 sheet 引用。

## 验收结果（2026-05 西物）

| 检查项 | 结果 |
|--------|------|
| 标准 F+G+H(120%) 共 95 行 | **95/95 一致** |
| 标准 SUMIF F 行 | **115/115 一致** |
| 标准 SUMIF G 行 | **118/118 一致** |
| `reconcile` 三列、可比对行 | 考核量/实际销量 **0 差异**；销量完成率 2 行（网销经理跨表公式） |
| 分岗位 | **49/67 岗位** 三列全通过 |

```bash
python -m unittest tests.test_ops -v
python main.py compute --reconcile
```

## 产物

- 代码：`salary_pipeline/ops/`、`pipelines/hub_task_metrics.py`、`modules/summary_skeleton.py`
- 输出：`output/2026-05/提成汇总.xlsx`
- 报告：`output/2026-05/reports/差异报告_*.md`

## 执行记录

详见 [WORKLOG.md](./WORKLOG.md)。
