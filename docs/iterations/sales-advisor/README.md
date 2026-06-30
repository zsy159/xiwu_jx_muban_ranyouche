# 销售顾问岗位族迭代

**账期：** 2026-05  
**状态：** Phase A ✅；Phase B **全表脱离 ✅**；Phase C **业务模块骨架 ✅**（`sales_advisor_performance` + 对账验收门槛）  
**最后更新：** 2026-06-26

**相关文档：**

- [绩效整理表-系统生成-数据源.md](./绩效整理表-系统生成-数据源.md)（Phase B：25 列输出、15 张 input 表、列级来源溯源）
- [HUB-W-AI-列级溯源.md](./HUB-W-AI-列级溯源.md)（销售顾问 Hub 十三列绩效：原始数据 → 绩效整理表 → 提成汇总，中文表头对照）

## 规模摸底

| 指标 | 数值 |
|------|------|
| `销售提成标准` 规则条数 | 164（多职务混表） |
| Hub `职务=销售顾问` 行 | **51**（49 人有 F–P 金标准） |
| Hub `职务=销售主管` 行 | **2**（与顾问同 sheet；W–AI ✅，见 [sales-supervisor/README.md](../sales-supervisor/README.md)） |
| Hub W–AI 目标列 | 整车 / 加装 / 保险 / 金融 / 爱车宝 / 上户绩效 |
| 拓扑回放 W–AI 差异（修复前） | **46 处** → **0 处**（2026-06-25，销售顾问） |

> 164 是提成依据全员名册，不等于 51 个进 Hub 的销售顾问；迭代以 **Hub 行 + 子表算薪** 为准。  
> **风险备忘：** `HubFormulaEngine` 按 Hub 格公式回放，不解析 164 条规则本身；模块化后须从 `销售提成标准` + 订单级数据显式算薪，二者边界要在 Phase C 设计时写清。

## 分阶段路线图（A → D）

| 阶段 | 内容 | 依赖 | 状态 |
|------|------|------|------|
| **A — 拓扑回放达标** | 修 `HubFormulaEngine`（双 SUMIF 链、`SUMIFS+常数` 等），51 人 W–AI 零差异 | 金标准 `绩效整理表` 整表可读（迭代 2 已具备） | ✅ 2026-06-25 |
| **B — 数据层独立** | `绩效整理表` 由明细层重算（含闭包列 AG/AH/AI…） | 闭包报告 + 订单级 ingestion pipeline | ✅ **全表脱离**；见 [PHASE-B-PLAN.md](./PHASE-B-PLAN.md) |
| **C — 业务模块** | `sales_advisor_performance` + `calculators/sales_advisor/` + `config/sales_advisor_roles.yaml`；读 `销售提成标准` JSON，**不再**依赖金标准中间表 | Phase B 顾问相关列可算，或业务接受「模块仍引导读整理表」的过渡方案 | ✅ 2026-06-25（见 [PHASE-C-PLAN.md](./PHASE-C-PLAN.md)） |
| **D — 门禁与观察台** | `hub_performance.yaml` 登记 `module` + `parity_gate: true`；观察台 **算薪 → 销售顾问** 页；`role_field_alignment`（按店别版式） | Phase C W–AI 与引擎结果一致 | ⏳ 字段拉通深化 |

```text
[现在] Phase A：HubFormulaEngine 回放金标准绩效整理表 → W–AI ✅
         ↓（不必紧接；见下方触发条件）
[数据 Epic] Phase B：明细 → 绩效整理表（formula 层重算）
         ↓
[模块 Epic] Phase C：sales_advisor_performance 写 hub 列
         ↓
[产品化] Phase D：parity_gate + 观察台算薪页 + 字段拉通
```

## 何时开发 `sales_advisor_performance` 模块

**结论：现在不需要；最佳开工窗口在 Phase B 立项之时，将 Phase C 作为同一 Epic 的后半段一并规划。**

### 启动条件（满足任一即可立项 Phase C）

| # | 触发场景 | 说明 |
|---|----------|------|
| T1 | **脱离金标准 `绩效整理表`** | 月度生产不再提供财务预整理的 `绩效整理表` 整表，必须从明细重算（Phase B 交付或同期） |
| T2 | **观察台算薪页** | 业务要在观察台 **算薪 → 销售顾问** 逐人钻取、对照 `销售提成标准` 子表版式（与四算薪族同等体验） |
| T3 | **字段拉通** | 需要 `role_field_alignment` 按店别版式展示整车/加装/保险等分项（Phase D 前置，通常与 T2 同批） |
| T4 | **销售主管与顾问统一治理** | 销售主管（Hub 2 人）与顾问同 sheet，需一套 `BaseCommissionModule` 覆盖多职务，而非继续在引擎里分叉修公式 |
| T5 | **引擎维护成本上升** | 销售顾问/主管族出现新的 Hub 公式模式，修 `HubFormulaEngine` 的边际成本高于模块化 |
| T6 | **硬门禁扩展** | 需将销售顾问纳入 `gated_performance` 层（与新媒体/邀约/客户/直营店经理并列 `parity_gate: true`） |

### 不建议早于（即使「想做」也应等待）

| # | 条件 | 原因 |
|---|------|------|
| N1 | Phase A 未全绿 | 模块与引擎结果无法对照，验收无锚点 |
| N2 | **仅为架构对称** | 拓扑回放已 W–AI 零差异，拆模块不改善当月对账 |
| N3 | Phase B 完全未规划 | 模块仍会 `merge` 金标准 `绩效整理表`，名为独立、实为假模块化 |
| N4 | 迭代 4 **XW 发薪**未稳 | XW 已 ✅；但 **CS / 直营店发薪（迭代 4+）** 若正关账，优先发薪层，避免 hub 列来源切换引发二次对账 |
| N5 | 164 条规则未做 Hub 映射策略 | 须先定「仅 51 Hub 行」还是「子表全员算薪 + 部分 hub_linked」——照抄客户专员骨架前先写清人员分工表 |

### 与其它迭代的时序建议

| 优先级 | 事项 | 与模块关系 |
|--------|------|------------|
| 可立即做 | 销售主管 2 人 Hub W–AI 引擎收口 | 仍走 Phase A，**不**等于开工 Phase C |
| 可并行 | 招聘岗位族摸底 | 独立族，不阻塞顾问模块 |
| 本月关账优先 | 迭代 3 售后 / 迭代 4+ CS·直营店发薪 | 发薪层与 hub 模块解耦；模块不挡关账 |
| **模块 Epic 自然窗口** | 迭代 5 跨月生产化 + 明细层接入 `绩效整理表` 重算 | Phase B 与 C 同一里程碑最省返工 |

## 阶段 0 发现：上户绩效根因

Hub 公式示例（何宇 / AC92）：

```
=SUMIF(绩效整理表!P:P,D92,绩效整理表!AN:AN)+SUMIF(绩效整理表!P:P,D92,绩效整理表!AS:AS)
```

`_eval_sumif_chain` 只算了第二段 SUMIF(AS)，漏掉第一段(AN) → 大量顾问显示 210 而非金标准。

修复：`salary_pipeline/pipelines/hub_formula_engine.py` — 链式第一段无 `SUMIF(` 前缀时仍参与求值。

## 阶段 2：韩柏成保险绩效

公式（Z134）：

```
=SUMIFS(绩效整理表!AJ:AJ,绩效整理表!P:P,D134)+600
```

引擎原先只识别纯 `SUMIFS`，`+600` 后缀返回 `None` → 0。已增加 `SUMIFS_ADD_CONST_RE` 支持（全表仅 1 处）。

## Phase B 进度（2026-06-25）

**计划：** [PHASE-B-PLAN.md](./PHASE-B-PLAN.md)

**Slice 1：** 保险明细 → AB/AJ；按揭明细 → AK  
**Slice 2：** 保险明细 → AO/AP（BU/BV）；49 顾问 SUMIF 门禁；`HubFormulaEngine` 可注入 `computed_perf_frame`  
**Slice 3：** 按揭原表+明细 → AL；装饰台账 → BH；整车成本 → AW–BB  
**Slice 4：** 系统销售毛利 → O/G/K/P 订单骨架（脱离金标准引导）；`终端明细表` ingestion 登记  
**Slice 5：** `PerformanceSheetModule` → `SalesPipeline`；`build()` 注入 `HubFormulaEngine`；51 顾问 W–AI 零差异  
**Slice 6（全表脱离）：** 闭包列 AG/AH/AI/AM/AN/AS/AQ/AR 全部由明细重算；`GOLDEN_OVERLAY_COLUMNS` 清空；金标准仅对账

```bash
python -m unittest tests.test_performance_sheet_builder tests.test_performance_sheet_module -v
python main.py compute --reconcile
```

| 列 / 键 | 订单行匹配率 | 说明 |
|----|-------------|------|
| O/P/K/G | 100% | 系统销售毛利 5 月含整车订单 462 + 11 服务补录行 |
| AB | 100% | `SUMIF(保险明细!D, VIN, BP)` |
| AK | 100% | `SUMIF(按揭明细!G, VIN, BO)` |
| AJ | 99.2% | `SUMIF(保险明细!D, VIN, BS)`；4 行边界 |
| AO | 100% | `SUMIF(保险明细!D, VIN, BU)` → Hub AF |
| AP | 100% | `SUMIF(保险明细!D, VIN, BV)` → Hub AG |
| AL | 顾问 100% | 双源 SUMIF → Hub AD；行级 ≤8 金标准空白边界 |
| BH | 订单行 ~99.8% | `SUMIFS(装饰台账!AK, N, G)`；尾部品类行跳过 |
| AW–BA | 100% | `INDEX(整车成本!R–V, MATCH VIN)` |
| BB | ~99.8% | `INDEX(整车成本!W, MATCH VIN)` |

订单键 O/P/G 已由 `build()` 从明细层生成；顾问级 `SUMIF(P, 姓名, col)` 已验（含 AL）。**流水线已接线**：`compute` 默认 `performance_sheet.use_computed: true`。

**Hub W–AI 值列（含闭包）：** AG/AH/AI/AM/AN/AS/AQ/AR 均已内化；`compute --reconcile` 销售顾问 W–AI **0 差异**。行级 AH/AI 在服务补录行等边界与金标准有个别偏差，不影响顾问汇总。

**Phase B 状态：** ✅ 全表脱离完成；Phase C 骨架已交付。

## Phase C 进度（2026-06-25）

**计划：** [PHASE-C-PLAN.md](./PHASE-C-PLAN.md)

- `SalesAdvisorPerformanceModule` 接入 `SalesPipeline`，用金标准盖上去写 Hub W–AI
- `hub_performance.yaml`：`module: sales_advisor_performance` + `parity_gate: true`
- 观察台 **算薪 → 销售顾问** 页（`8_销售顾问.py`）
- `compute --reconcile`：`gated_performance` 销售顾问 **0 差异**

## 验收结果（2026-06-25）

销售顾问 51 人 Hub W–AI **7 列零差异**（拓扑回放，无需独立模块即可达标）。

```bash
python -m unittest tests.test_hub_formula_engine.HubFormulaEngineTest.test_he_yu_shanghu_double_sumif_chain -v
python main.py compute --reconcile
# 关注差异报告 → 销售顾问 W–AI 行
```

## 子表与 Hub 关系

- 依据 sheet：`销售提成标准`（按人序号，多店别版式混排）
- Hub 列：W–AB 区绩效列，多数已由 `SUMIFS(绩效整理表)×完成率` 拓扑回放
- 与已完成的四算薪族不同：销售顾问 **Phase A 已够用**；`sales_advisor_performance` 等到 **T1–T6 触发 + Phase B 数据层** 再开工

## 店别分布（Hub）

多数销售顾问 `店别` 为空（49/51），匹配宜以 **姓名 + 职务** 为主，店别作辅助。

## Phase C 开工时复制的骨架（✅ 已建，见 PHASE-C-PLAN.md）

```
config/sales_advisor_roles.yaml
calculators/sales_advisor/
modules/sales_advisor_performance.py
config/role_field_alignment/sales_advisor.yaml   # 若 T2/T3 触发
app/pages/算薪/N_销售顾问.py
tests/test_sales_advisor_performance.py
```

登记：`hub_performance.yaml` → `销售顾问.module` + `parity_gate: true`（Phase D）。
