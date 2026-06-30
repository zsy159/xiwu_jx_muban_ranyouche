# 销售顾问 Phase B — 数据层实施计划

**账期样板：** 2026-05  
**状态：** Phase B 全表脱离 ✅（Slice 5 闭包列内化 + 流水线接线）  
**最后更新：** 2026-06-25

## 目标

`绩效整理表` 由 **明细层重算**，脱离财务预整理 Excel；为 Phase C `sales_advisor_performance` 提供真实数据来源。

```text
input（明细）          formula（中间表）           hub（提成汇总）
终端明细表、保险明细、  →  绩效整理表（订单级）  →  SUMIF/SUMIFS(P列)  →  W–AI
按揭明细、装饰台账…         ↑ 本 Phase 建设
```

Phase A 已证明：Hub 引擎读金标准 `绩效整理表` 可 W–AI 零差异。Phase B 替换该表的**数据来源**，引擎拓扑公式暂不变。

## 「明细」是什么

| Sheet | `sheet_registry` 角色 | 在绩效整理表中的作用（样本月） |
|-------|----------------------|-------------------------------|
| `终端明细表` | input | 386 处公式引用（如 BC 列 SUMIFS） |
| `保险明细` | input | 1635 处（AJ/AB/AO/AP 等 SUMIF by VIN） |
| `按揭明细` | input | 1222 处（AK/AL 等） |
| `装饰台账` | input | 915 处 |
| `整车成本` | input | 3082 处（最大引用量） |

另有未登记 input：`上户提成`、`爱车保`、`置换服务`、`按揭原表`、`系统销售毛利` 等 — 闭包在 `绩效整理表` 内，后续 slice 按列优先级接入。

## 绩效整理表结构（订单级）

- **粒度：** 约 500 行订单（`K` 台数、`O` VIN、`G` 订单号）
- **Hub 关联键：** `P` 列 = 销售顾问姓名（`SUMIF(绩效整理表!P:P, 提成汇总!Dn, …)`）
- **行 2：** 表头；**数据自 Excel 行 3 起**

### 销售顾问 Hub W–AI 引用的绩效整理表列（49 可比人）

| Hub 列 | 绩效整理表值列 | 典型 Hub 公式模式 |
|--------|---------------|-------------------|
| W 整车绩效 | AG | `SUMIFS(AG,P,Dn)*完成率` |
| Y 加装绩效 | AH | `SUMIFS(AH,P,Dn)` |
| Z 保险绩效 | AJ | `SUMIFS(AJ,P,Dn)*H` 或 `+600` |
| AA 金融绩效 | AI | `SUMIFS(AI,P,Dn)*H` |
| AB 爱车宝 | AK | `SUMIF(AK,P,Dn)` |
| AC 上户绩效 | AN+AS | 双 SUMIF 链 |
| AD–AI | AL, AM, AO… | SUMIF/SUMIFS |

完整列清单见 `salary_pipeline/config/performance_sheet_columns.yaml`。

## T1–T6 触发条件在 Phase B 中的含义

| 触发 | Phase B 交付物 |
|------|----------------|
| T1 脱离金标准整理表 | 流水线 `compute` 不再 `read_excel(绩效整理表)`，改读 builder 输出 |
| T2 观察台算薪页 | builder 需导出可钻取订单明细（按 P 聚合前） |
| T3 字段拉通 | 列语义与 `销售提成标准` 子表对齐 |
| T4 主管+顾问统一 | builder 不按职务分叉，Hub 层再分治 |
| T5 引擎维护成本 | 列算法内化后减少 `HubFormulaEngine` 补丁 |
| T6 硬门禁 | Phase B 全列达标 + Phase C 模块后设 `parity_gate` |

## 实施切片（建议顺序）

### Slice 1 — 明细 SUMIF 列（✅）

**范围：** 保险明细 → AB/AJ；按揭明细 → AK  
**金标准验证：** 473 订单行 AB/AK 100% 一致；AJ 99.2%（4 行边界）

| 文件 | 作用 |
|------|------|
| `config/performance_sheet_columns.yaml` | 列注册与明细映射 |
| `data_ingestion/insurance_detail_sheet.py` | 读保险明细 |
| `data_ingestion/mortgage_detail_sheet.py` | 读按揭明细 |
| `data_ingestion/performance_sheet_golden.py` | 订单骨架 O/P/K（过渡：键来自金标准） |
| `calculators/performance_sheet/from_insurance.py` | AB/AJ 重算 |
| `calculators/performance_sheet/from_mortgage.py` | AK 重算 |
| `pipelines/performance_sheet_builder.py` | 组装 partial frame |
| `tests/test_performance_sheet_builder.py` | 列级 + 顾问 SUMIF 聚合测试 |

**验收：**

```bash
python -m unittest tests.test_performance_sheet_builder -v
```

### Slice 2 — 保险扩展列 + 顾问聚合门禁（✅ 本批）

- AO/AP（保险明细 BU/BV）→ 473 订单行 100% 一致
- 49 可比顾问 `SUMIF(P, name, AJ/AK/AO/AP)` 与金标准一致（AJ ≤4 人边界）
- `HubFormulaEngine(computed_perf_frame=…)` 可选注入（AF/AG 抽样验证）

| 变更 | 作用 |
|------|------|
| `build_slice_2()` | AB/AJ/AK + AO/AP |
| `hub_formula_engine._overlay_computed_perf` | 按 VIN 覆盖金标准列 |
| `test_advisor_sumif_gate_slice_2` | 顾问级 parity 门禁 |

### Slice 3 — 按揭 / 装饰 / 整车成本（✅ 本批）

- AL（按揭原表 AF + 按揭明细 BR）→ 顾问级 SUMIF 100%；行级 ≤8 边界（金标准空白行）
- BH（装饰台账 AK by 订单号 G）→ 真实订单行 ≤1 边界
- AW–BA 整车成本 INDEX/MATCH → 473 订单行 100%；BB ≤1 边界
- `build_slice_3()` 组装 Slice 1–2 列 + AL/BH/AW–BB
- Hub AD（盈利产品绩效）注入抽样验证

| 变更 | 作用 |
|------|------|
| `mortgage_original_sheet.py` | 读按揭原表 AC/AF |
| `decoration_ledger_sheet.py` | 读装饰台账 N/AK |
| `vehicle_cost_sheet.py` | 读整车成本 K + R–W |
| `from_mortgage.py` | AL 双源 SUMIF |
| `from_decoration.py` | BH SUMIFS |
| `from_vehicle_cost.py` | AW–BB INDEX/MATCH |
| `test_slice_3_*` | 列级 + AL 顾问门禁 + Hub AD |

### Slice 4 — 订单骨架脱离金标准（✅ 本批）

- `O`/`G`/`K` 从 `系统销售毛利` 当月 `含整车订单` 生成；`P` = `INDEX(BJ, MATCH(O, BD))` + 11 处 Hub 别名覆盖
- 11 条服务补录行（`G`=置换服务/爱车保/延保服务…，`K` 空白）由 `performance_sheet_columns.yaml` 登记
- `终端明细表` ingestion 登记（`terminal_detail_sheet.py`）；BC 列 SUMIFS 留待后续 slice
- `build_slice_4()` = computed skeleton + Slice 1–3 列；473 行 O/P/K/G 与金标准 100% 一致

| 变更 | 作用 |
|------|------|
| `system_sales_gross_sheet.py` | 读系统销售毛利 B/BD/BJ/BA/AZ |
| `terminal_detail_sheet.py` | 读终端明细表 C/D/P |
| `order_skeleton.py` | 组装 O/P/K/G |
| `build_slice_4()` | 脱离 `performance_sheet_golden` 引导键列 |
| `test_slice_4_*` | 键列 + 值列 + 顾问 SUMIF 门禁 |

### Slice 5 — 全列 parity + 流水线接线（✅ 本批）

- `modules/performance_sheet_module.py` → `SalesPipeline` 在 Hub 引擎前运行 `build()`
- `month.yaml` → `performance_sheet.use_computed: true`（T1：已内化列走 builder）
- `HubFormulaEngine(computed_perf_frame=…)` 由流水线自动注入
- 51 销售顾问 W–AI：重算整理表 vs 金标准拓扑 **0 处差异**

| 变更 | 作用 |
|------|------|
| `performance_sheet_module.py` | 构建 `computed_perf_frame` 写入 context |
| `sales.py` | Hub 前接线 builder 输出 |
| `performance_sheet_builder.build()` | 当时生产入口 = `build_slice_4()`（仅明细列；Slice 6 升级为 `build_slice_5()`） |

### Slice 6 — 闭包列内化 / 全表脱离（✅ 本批）

- Hub 间接引用列 **AG/AH/AI/AM/AN/AS/AQ/AR** 全部由明细/标准表重算，**不再**从金标准 xlsx 读值列
- `GOLDEN_OVERLAY_COLUMNS` 置空；金标准 `绩效整理表` 仅用于列级/顾问级对账
- `build()` = `build_slice_5()` = 订单骨架 + Slice 1–3 明细列 + 闭包列
- 新增：`closure_input_sheets.py`、`order_context.py`、`from_closure.py`
- 51 销售顾问 W–AI：`compute --reconcile` **0 处差异**；单元测试全绿

| 列 | 来源概要 | 订单行匹配率（样本月） |
|----|----------|------------------------|
| AG | 提成标准 lookup × K；武侯星越L 特例 | ~99.2%（4 行边界） |
| AH | D/AA + AG/AI/AJ/AK 整车超额公式链 | 顾问 SUMIF 对账一致；行级约 67% |
| AI | K/L/S/U 加装绩效公式 | 顾问 SUMIF 对账一致；行级约 55% |
| AM | SUMIF(爱车保) | ~99.8% |
| AN | SUMIF(上户提成) | ~99.4% |
| AS | SUMIF(置换服务) | ~99.8% |
| AQ | 重功超期+活动 + 提成标准 H | ~97% |
| AR | 二手置换 + 大客户 | ~99.8% |

**行级边界说明：** 服务补录行（`G`=置换服务/爱车保…）及部分 `系统销售毛利` 未匹配 VIN 时，AH/AI 行级与金标准有差，但顾问级 `SUMIF(P, 姓名, col)` 与 Hub W–AI 仍零差异。

| 变更 | 作用 |
|------|------|
| `from_closure.py` | AG/AH/AI/AM/AN/AS/AQ/AR 重算 |
| `order_context.py` | 系统销售毛利 BL/AO/BQ + 比对表 + V/Z/AA 链 |
| `closure_input_sheets.py` | 上户提成/爱车保/置换服务/提成标准等 ingestion |
| `build_slice_5()` | 生产完整值列表 |
| `GOLDEN_OVERLAY_COLUMNS = ()` | 全表脱离金标准值列 |

**验收：**

```bash
python -m unittest tests.test_performance_sheet_builder tests.test_performance_sheet_module -v
python main.py compute --reconcile
```

## Phase B 完成标准（整体）

1. ✅ 顾问 Hub W–AI **直接/间接引用**的列均可从 input 明细/标准表重算（含 AG/AH/AI/AM/AN/AS/AQ/AR）
2. ✅ `compute` 对绩效整理表**值列**不再依赖金标准 xlsx（T1 达成；金标准仅对账）
3. ✅ 文档 + 测试覆盖每列来源公式
4. ✅ 为 Phase C `sales_advisor_performance` 预留 `calculators/sales_advisor/` 接口（见 README）→ **Phase C 已交付**，见 [PHASE-C-PLAN.md](./PHASE-C-PLAN.md)

## 与 Phase C 边界

| Phase B | Phase C |
|---------|---------|
| 订单级中间表列 | 读 `销售提成标准` JSON，写 Hub W–AI |
| `SUMIF(明细)` 复刻 Excel | 业务规则显式算薪 |
| 引擎仍可做 `×完成率` | `performance_overlay` 覆盖 |

## 风险

- `绩效整理表` 有 21717 个公式格，全表一次做完不现实 — 按 Hub 引用闭包逐列推进
- `P` 列部分行来自 `系统销售毛利` INDEX/MATCH，Slice 4 前需金标准键引导
- 164 条 `销售提成标准` ≠ 51 Hub 行：Phase C 须单独定义 hub_linked 策略（见 README N5）
