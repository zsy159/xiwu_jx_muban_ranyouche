# 迭代 2：销售中间层 + 提成汇总核心列扩展

> 对应总规划：[迭代文档.md § 迭代 2](../../迭代文档.md)

## 目标

将 `提成汇总` 从 3 列扩展到 **F–P 共 11 列**（考核量 → 按揭毛利），引入通用公式引擎与算子 v2。

## 任务清单

| # | 任务 | 交付物 | 状态 |
|---|------|--------|------|
| 1 | 算子 v2 | `lookup_match_index`、`sumifs_by_keys`、`if_ladder` | ✅ |
| 2 | 通用公式引擎 | `HubFormulaEngine`（替代 `HubTaskMetricsCalculator`） | ✅ |
| 3 | 中间表读取 | `销售任务及完成率`、`绩效整理表` 整列 | ✅ |
| 4 | 公式模式扩展 | SUM、跨行引用、INDEX/MATCH、SUMIFS、算术 | ✅ |
| 5 | `#REF!` 处理 | `formula_warnings.txt` | ✅ |
| 6 | 对账 F–P 十一列 | `month.yaml` parity.columns | ✅ |

## 已实现公式模式

| 模式 | 示例 |
|------|------|
| SUMIF 跨表 | `SUMIF(绩效整理表!P:P, Dn, 绩效整理表!BG:BG)` |
| SUM 区块 | `SUM(F90:F105)`、`F142=F106` |
| INDEX+MATCH | `IFERROR(INDEX(销售任务及完成率!F:F, MATCH(Dn, !C:C, 0)), 0)` |
| SUMIFS 组合 | 保险渗透率 L 列 |
| 比率 IF | `IF(Gn*1500<>0, Jn/(Gn*1500), 0)` |
| 简单除法 | `Hn=Gn/Fn` |
| 算术 | `M217-指标汇总!E53`、`指标汇总!E52+…` |

## 验收结果（2026-05）

| 指标 | 结果 |
|------|------|
| F–P 单元格一致率 | **96.3%**（66/1782 处差异） |
| 标准销售顾问行（SUMIF 链路） | 零差异 |
| 分岗位（11 列） | **49/67** 岗位全通过 |
| `#REF!` 行 | 已跳过并记入 `output/2026-05/reports/formula_warnings.txt` |

### 剩余差异（可解释，迭代 3+）

1. **管理岗静态格**：F/G/I 等列无公式（手工填入 100、完成率等）— 约 11 人
2. **静态覆盖**：如易花贞子 H 列 golden=1 但公式为 SUMIF 结果应为 0.125
3. **`#REF!` 行**：如牟春柳（出纳+内勤）整行引用损坏

## 命令

```bash
python -m unittest discover -s tests -v
python main.py compute --reconcile
```

## 执行记录

详见 [WORKLOG.md](./WORKLOG.md)。
