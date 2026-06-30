# 迭代 4+：多渠道发薪

> 承接 [iteration-4/README.md](../iteration-4/README.md) 任务 6。

## 目标

在 `XwPayoutFormulaEngine` 上换配置，输出 **直营店提成-发** / **CS提成-发**，不重复造公式引擎。

## 状态

| 渠道 | 基本表 | 引擎配置 | CLI | 对账 | 状态 |
|------|--------|----------|-----|------|------|
| XW提成-发 | 西物基本 | `XW_CONFIG` | `--channel xw`（默认） | `payout_parity` | ✅ 迭代 4 |
| **直营店提成-发** | **直营店基本** | `DIRECT_STORE_CONFIG` | `--channel direct_store` | `direct_store_parity` | ✅ |
| CS提成-发 | 超市基本 | `CS_CONFIG` | `--channel cs` | `cs_parity` | ✅ |

## 直营店验收（2026-05）

| 指标 | 结果 |
|------|------|
| 对账列（10 列核心指标） | **100%** 一致 |
| 分店别对账 | **4/4** 店别全通过 |
| 直营店经理 AG（银河 A+B） | 朱剑波等 5 人 ✅ |
| 公式 warnings | 45（表尾空行，可忽略） |

### 直营店经理代发放绩效

`代发放绩效(银河A+B)` 在 **AG 列**，公式：

```
SUMIF(银河B直营店提成!AG) + SUMIF(银河A提成!AH)
```

归属决策见 [direct-store-manager/发薪项归属.md](../direct-store-manager/发薪项归属.md)。

## CS 验收（2026-05）

| 指标 | 结果 |
|------|------|
| 对账列（9 列核心指标） | **100%** 一致 |
| 分店别对账 | **12/12** 店别全通过 |
| 个税 lookup | `INDEX(BB, MATCH(D, BA))`（非 XW 的 AZ/BA） |
| 公式 warnings | 22（`#REF!` 车展奖励行，AJ=0 与金标准一致） |

### CS 个税表

CS 发薪表个人所得税（AN 列）通过 **BA 列姓名 → BB 列税额** 查找，与 XW/直营店的 AZ/BA（或 BE/BF）不同。`CS_CONFIG` 已设 `tax_lookup_key_col=BA`、`tax_lookup_value_col=BB`。

## 命令

```bash
# 直营店（推荐）
python main.py compute-payout --channel direct_store --reconcile

# XW（默认，与迭代 4 相同）
python main.py compute-payout --reconcile

# CS（推荐）
python main.py compute-payout --channel cs --reconcile

# 端到端：Hub → 三渠道发薪（合并计算版 hub + 金标准 W–AR）
python main.py compute-all --reconcile

# 单测
python -m unittest tests.test_direct_store_payout tests.test_cs_payout -v
```

## 配置入口

- `salary_pipeline/config/month.yaml` → `payout.direct_store` / `direct_store_parity`
- `salary_pipeline/pipelines/xw_payout_formula_engine.py` → `DIRECT_STORE_CONFIG`
- `salary_pipeline/pipelines/xw_payout.py` → `ChannelPayoutPipeline`

- `salary_pipeline/config/month.yaml` → `payout.cs` / `cs_parity`
- `salary_pipeline/pipelines/xw_payout_formula_engine.py` → `CS_CONFIG`

## compute-all

`python main.py compute-all [--reconcile]` 顺序执行：

1. 提成汇总（Hub）
2. XW提成-发 / 直营店提成-发 / CS提成-发（均使用上一步计算版 hub）

带 `--reconcile` 时依次对账 Hub F–P + 算薪族 W–AI，以及三渠道发薪表；任一阶段失败则退出码非 0。
