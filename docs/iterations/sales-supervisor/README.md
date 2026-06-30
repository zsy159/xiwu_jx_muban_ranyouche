# 销售主管岗位族迭代

**账期：** 2026-05  
**状态：** Phase A（Hub 拓扑 W–AI）✅  
**最后更新：** 2026-06-25

## 规模摸底

| 指标 | 数值 |
|------|------|
| 依据 sheet | `销售提成标准`（与销售顾问同表） |
| Hub `职务=销售主管` 行 | **2** |
| Hub W–AI 登记列（`hub_performance.yaml`） | 整车 / 加装 / 保险绩效 |
| 拓扑回放 W–AI 差异（修复前） | **2 处**（均 `上户绩效`）→ **0 处** |

## 两人与差异明细

| 姓名 | 店别 | Hub 行 | 差异列 | 金标准 | 修复前 computed | 根因 |
|------|------|--------|--------|--------|-----------------|------|
| 邓戈 | 机场展厅 | 60 | 上户绩效 | 258 | 0 | `SUMIF(AN)` 段未计入（AS=0，漏 AN=258） |
| 熊杰文 | 武侯DCC | 107 | 上户绩效 | 568 | 140 | `SUMIF(AN)` 段未计入（仅 AS=140，漏 AN=428） |

整车 / 加装 / 保险绩效两人在修复前后均已对齐（`SUMIFS×完成率` 等模式引擎已支持）。

## 公式模式

Hub `AC` 列（上户绩效）与销售顾问相同：

```
=SUMIF(绩效整理表!P:P,D{n},绩效整理表!AN:AN)+SUMIF(绩效整理表!P:P,D{n},绩效整理表!AS:AS)
```

## 修复说明

**无需新建 `sales_supervisor_performance` 模块。**

根因与 [销售顾问 Phase A](../sales-advisor/README.md) 相同：`_eval_sumif_chain` 在链式 `SUMIF(a)+SUMIF(b)` 中漏掉第一段（无 `SUMIF(` 前缀的 `绩效整理表!AN:AN` 段）。

修复位置：`salary_pipeline/pipelines/hub_formula_engine.py` — 已在 2026-06-25 销售顾问收口时合入；销售主管 2 人随同一补丁达标。

## 验收结果（2026-06-25）

```bash
python -m unittest \
  tests.test_hub_formula_engine.TestHubFormulaEngine.test_deng_ge_supervisor_shanghu_double_sumif_chain \
  tests.test_hub_formula_engine.TestHubFormulaEngine.test_xiong_jiewen_supervisor_shanghu_double_sumif_chain \
  -v
python main.py compute --reconcile
# 差异报告 → 销售主管 W–AI：2 人 13 列零差异
```

## 后续

- 与销售顾问共用 `销售提成标准`；若未来立项 `sales_advisor_performance`（Phase C），宜以 **姓名 + 职务** 覆盖顾问与主管（见顾问 README 触发条件 T4）。
- 当前 **不** 登记 `parity_gate`（与顾问一致，拓扑回放达标即可）。
