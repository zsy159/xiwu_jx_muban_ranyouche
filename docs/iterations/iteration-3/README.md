# 迭代 3：售后账套 + 规则库

> 对应总规划：[迭代文档.md § 迭代 3](../../迭代文档.md)

## 目标

售后门店提成表（武侯 / 机场）+ `提成依据.xlsx` 规则可配置化。

## 任务清单

| # | 任务 | 交付物 | 状态 |
|---|------|--------|------|
| 1 | 售后公式引擎 | `AftersalesFormulaEngine`（INDEX/MATCH、SUMIF、算术） | ✅ |
| 2 | 售后流水线 | `pipelines/aftersales.py` | ✅ |
| 3 | 骨架读取 | `aftersales_skeleton.py`（按 Excel 行号对齐） | ✅ |
| 4 | 规则抽取 | `scripts/extract_commission_rules.py` → `config/commission_rules/` | ✅ |
| 5 | CLI | `compute-aftersales` / `reconcile-aftersales` | ✅ |
| 6 | 第二门店 | `AIRPORT_CONFIG` 共用引擎 | ✅（初版） |
| 7 | 对账 D–W | `aftersales_parity` in `month.yaml` | ✅ |

## 已实现公式模式

| 模式 | 示例 |
|------|------|
| INDEX+MATCH 跨表 | `INDEX('05基本'!P:P,MATCH(Cn,'05基本'!C:C,0))` |
| INDEX 求和 | `INDEX(...I...)+INDEX(...J...)` |
| SUMIF | `SUMIF(综合考核!A:A,Cn,综合考核!M:M)` |
| SUM 行内 | `SUM(Kn:Ln)` |
| 算术链 | `O=M-N`, `R=M+I+Q`, `U=S-T`, `W=O-P-U` |
| 个税 AB/AC 表 | `INDEX(AC:AC,MATCH(Cn,AB:AB,0))`（自金标准引导） |

## 验收结果（2026-05 武侯售后）

| 指标 | 结果 |
|------|------|
| D–W 单元格一致率 | **99.5%** |
| 公式 warnings | **0** |
| 剩余差异 | 个别 `其它` / `其他补贴` 列手工覆盖 |

机场售后：**97.1%** 一致率，0 warnings（已注册 `钣喷中心`、`西物公积金`）。

## 命令

```bash
python -m unittest discover -s tests -v
python main.py compute-aftersales --store wuhou --reconcile
python main.py compute-aftersales --store airport --reconcile
python scripts/extract_commission_rules.py
```

## 执行记录

详见 [WORKLOG.md](./WORKLOG.md)。
