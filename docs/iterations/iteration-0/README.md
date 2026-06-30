# 迭代 0：基础能力巩固

> 对应总规划：[迭代文档.md § 迭代 0](../../迭代文档.md)

## 目标

公式地图可信 + 工程骨架 + 对账框架就绪（**不实现完整业务计算**）。

## 任务清单

| # | 任务 | 交付物 | 验收标准 | 状态 |
|---|------|--------|----------|------|
| 1 | 修复拓扑解析：无引号中文 sheet 引用（T1） | `scripts/extract_formula_topology.py` + 重跑 JSON | `提成汇总!F3` 的 `depends_on_ranges` 含 `销售任务及完成率!C:C` / `!Y:Y` | ✅ 已完成 |
| 2 | 依赖闭包分析脚本 | `scripts/closure_report.py` | 以锚点表输出最小公式 sheet 集 + 输入数据 sheet 集 | ✅ 已完成 |
| 3 | `salary_pipeline/` 骨架 | 包目录 + CLI | `compute` / `reconcile` 可运行 | ✅ 已完成 |
| 4 | 对账框架 | `validation/parity.py` | 列级差异 + 分岗位《差异报告》 | ✅ 已完成 |
| 5 | `sheet_registry.yaml` | hub（提成汇总）+ output（各「发」表） | ✅ 已完成 |

## 产物路径

| 产物 | 路径 |
|------|------|
| 拓扑 JSON（2026-05） | `data/topology/2026-05/*.topology.json` |
| 闭包报告 | `docs/iterations/iteration-0/artifacts/closure_提成汇总.*` |
| 差异报告 | `output/2026-05/reports/差异报告_*.md` |

## 已知技术债（本迭代处理范围）

- **T1**：无引号中文 sheet 名误归当前 sheet → 本迭代修复

不在本迭代：**T2** `#REF!`、**T3** 尾部空格 sheet 名、**T4** 主键重复。

## 执行记录

详见 [WORKLOG.md](./WORKLOG.md)。
