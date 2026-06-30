# 迭代 4：汇总发薪 + 分渠道输出

> 对应总规划：[迭代文档.md § 迭代 4](../../迭代文档.md)

## 目标

接近财务实发口径：基本工资 + 提成 + 扣款 → `XW提成-发` 等渠道发薪表。

## 任务清单

| # | 任务 | 交付物 | 状态 |
|---|------|--------|------|
| 1 | XW 发薪公式引擎 | `XwPayoutFormulaEngine` | ✅ |
| 2 | 基本工资接入 | `payroll_merge.py` + 西物基本 SUMIF | ✅ |
| 3 | XW 流水线 | `pipelines/xw_payout.py` | ✅ |
| 4 | CLI | `compute-payout` / `reconcile-payout` | ✅ |
| 5 | 对账 | `payout_parity` in `month.yaml` | ✅ |
| 6 | CS / 直营店 | 共用引擎换配置（含直营店经理 **代发放绩效 银河A+B**） | ✅ 直营店 / ⏳ CS |
| 7 | 个税模块 | 可选 Phase 2 | ⏳（AZ/BA 引导已实现） |

## 已实现公式模式

| 模式 | 示例 |
|------|------|
| Hub SUMIF | `SUMIF(提成汇总!D:D,Dn,提成汇总!W:W)` |
| 基本工资 SUMIF | `SUMIF(西物基本!C:C,Dn,西物基本!P:P)` |
| 银河双表 | `SUMIF(银河B…)+SUMIF(银河A…)` |
| 行内 SUM | `SUM(Hn:Tn)`、`SUM(Vn:ACn)` |
| 算术链 | `AE=U+AD`、`AH=AE-AF+AG`、`AS=AH-AP-AR` |
| 个税 INDEX | `INDEX(BA:BA,MATCH(Dn,AZ:AZ,0))`（金标准引导） |

## 验收结果（2026-05 XW提成-发）

| 指标 | 结果 |
|------|------|
| 对账列（9 列核心指标） | **100%** 一致 |
| 分岗位对账 | **12/12** 店别全通过 |
| 公式 warnings | 19（`#REF!` 损坏格，已跳过） |
| 数据来源 | 提成汇总 + 西物基本 + 银河子表（金标准引导） |

## 命令

```bash
python -m unittest discover -s tests -v
python main.py compute-payout --reconcile
python main.py compute-payout --channel direct_store --reconcile
```

多渠道发薪详见 [iteration-4-plus/README.md](../iteration-4-plus/README.md)。

## 执行记录

详见 [WORKLOG.md](./WORKLOG.md)。
