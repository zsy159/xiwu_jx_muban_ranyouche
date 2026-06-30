# 提成汇总 W–AI 绩效：岗位分治

## 终态 vs 过渡

| | 说明 |
|---|------|
| **终态** | `config` + `calculators` + `modules` 写入 Hub；Excel 仅作金标准对账 |
| **过渡** | `HubFormulaEngine` + 中间表（`绩效整理表`、子表 `SUMIF`）仅在对账或未内化阶段使用 |

**岗位内化状态（2026-06）：**

| 岗位族 | 状态 |
|--------|------|
| 新媒体 / 邀约专员 / 客户专员 / 直营店经理 / **招聘** | ✅ 已内化（`parity_gate: true`） |
| 销售顾问 / 销售主管 | 引擎过渡（拓扑回放已达标，待明细层 Phase B） |

内化完成标志：登记 `hub_performance.yaml` → 实现 `modules/<族>_performance.py` → 测试与 `compute --reconcile` 通过后设 `parity_gate: true`。

## 为什么不能「一套公式算全员」

`提成汇总` 的 **F–P**（考核量、毛利等）大量来自统一中间表（`销售任务及完成率`、`绩效整理表`），适合用拓扑公式引擎按格回放。

**W–AI（整车绩效、加装绩效…）** 则与 **提成依据** 一样：**岗位族不同，算法不同**——

| 岗位族 | 依据来源 | Hub 列示例 |
|--------|----------|------------|
| 销售顾问 | `销售提成标准` | 整车/加装/保险绩效 |
| 邀约专员 | `邀约专员提成` | 整车绩效（AE→AF SUMIF） |
| 新媒体 | `新媒体` | 整车绩效（Y→AB SUMIF） |
| 招聘 | `招聘` | 保险绩效 |
| 客户部 | `客户部提成` | 多列绩效 |

不能用单一 `HubFormulaEngine` 替代全部业务规则；引擎只作 **过渡层**（按 Excel 公式回放），长期应由 **岗位模块 + 提成依据 JSON** 写入 hub 列。

配置入口：`salary_pipeline/config/hub_performance.yaml`（与 `commission_rules/manifest.yaml` 对齐）。

## 对账分层（2026-06 起）

| 层 | 列 | 作用 |
|----|-----|------|
| **F–P 验收** | `month.yaml` → `parity.columns` | 硬门禁，`compute --reconcile` 整体通过 |
| **W–AI 跟踪** | `parity.performance_columns` | 可见进度，**不阻断** F–P；观察台 Hub 卡 F–P 过、W–AI 未全时显示 ⚠️ |

试点岗位族（新媒体、DCC邀约专员、客户专员）已落地，见 `modules/new_media_performance.py`、`modules/invite_specialist_performance.py`、`modules/customer_specialist_performance.py`。

## 实施顺序

1. 登记岗位族 → `hub_performance.yaml`（新媒体已登记 `module: new_media_performance`）
2. 为每族实现 `BaseCommissionModule`（读 rules JSON / 中间表）
3. 模块结果经 `performance_overlay` 写入 hub 列（hub 公式之后覆盖）
4. 该族 W–AI 对账通过后，设 `parity_gate: true` 并关掉该族 bootstrap

`HubFormulaEngine` 继续服务尚未模块化的岗位，直至被替换。

## 销售顾问：引擎过渡 vs 独立模块

销售顾问 Hub **51 人 W–AI 已零差异**（2026-06-25，拓扑回放），与四算薪族不同，**当前不必**急于 `sales_advisor_performance`。

| 维度 | 现在（Phase A） | 模块化后（Phase C–D） |
|------|-----------------|----------------------|
| 数据来源 | 读金标准 `绩效整理表` 整列 | 明细层重算整理表 + `销售提成标准` 规则 |
| Hub 写入 | `HubFormulaEngine` 按格回放 | `performance_overlay` 覆盖 W–AI 列 |
| 验收 | W–AI 跟踪层通过即可 | `parity_gate: true` + 观察台算薪页 |

**最佳开工时机：** `绩效整理表` 数据层（Phase B，迭代 5 / 明细 ingestion Epic）立项时，将 `sales_advisor_performance` 作为后半段；观察台算薪页、销售主管统一治理、硬门禁扩展为并列触发条件。详见 [iterations/sales-advisor/README.md](../iterations/sales-advisor/README.md)。

> `销售提成标准` 有 **164** 条规则、`Hub` 仅 **51** 行顾问 + **2** 行主管；引擎只回放 Hub 格公式，模块须单独定义「谁进 hub / 谁仅子表」策略，避免把 164 人全塞进一套算子。
