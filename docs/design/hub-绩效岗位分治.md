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
| **销售顾问** | ✅ F–P 已迁 **HubMetricsRuleEngine**；W–AI 已迁 **HubRuleEngine**（`hub_column_rules.yaml`） |
| 销售主管 / 销售助理 | 并入销售顾问 family，W–AI 与顾问同规则 |

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

## 金标准覆盖废除（2026-07）

**原则：** 系统输出仅含计算值；金标准仅用于骨架/对账，**禁止**把金标准单元格复制进 `output/提成汇总.xlsx` 或发薪 SUMIF 源以掩盖差异。

| 路径 | 变更 |
|------|------|
| `hub.bootstrap_from_golden` | 默认 `false`；`HubFormulaEngine._bootstrap_cell` / `_lazy_cell` 不回读金标准 |
| `bootstrap_non_frontline_physical_columns` | 空操作 |
| `build_hub_sumif_frame` | 仅 `output/提成汇总.xlsx`（按表头名映射到字母列）；无 computed 时数值列为空 |
| `collect_topology_static_fill_cells` | 拓扑判定「需手工填入」；浅灰 `#D9D9D9` 标格，不回填数值 |
| `xw_payout` | `--golden-hub` 已废弃；SUMIF 固定走 computed hub |

手工格（如 **唐操** hub 行 94 的 W/X 在金标准为常数）在系统中由 overlay/公式计算或留空，与金标准差异在对账报告可见。

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

## 非一线：语义列（2026-06）

金标准 `提成汇总` 在多个区块用**子表头复用物理列**，系统另增语义列避免与一线混读。物理列数值不变（F–P 对账、XW SUMIF 兼容）。

### 管理区块（row 138/145）

| Excel 列 | 一线表头 | 非一线子表头 |
|----------|----------|--------------|
| W | 整车绩效 | **岗位绩效** |
| Y | 加装绩效 | **业绩绩效** |

店别：销售管理部、事业部、总经办；职务补充：实习销售总监、网销经理。

### 支持部门区块（row 161）

| 物理列 | 一线表头 | 支持部门子表头 |
|--------|----------|----------------|
| M | 整车毛利 | 售后总产值 |
| N | 加装毛利 | 配件外销 |
| Q | 爱车宝毛利 | 售后产值 |
| R | 上户毛利 | 出库 |
| S | 整车+加装（毛利） | 入库 |
| T | 综合毛利 | 台次 |
| U | 主营单台毛利 | 提成系数 |
| V | 综合单台毛利 | 提成系数2 |
| W | 整车绩效 | 岗位绩效 |
| X | 权限结余绩效 | 新能源专项 |
| Y | 加装绩效 | 业绩绩效1 |
| Z | 保险绩效 | 业绩绩效2 |

店别：财务部、市场部、物流、上户部、增值业务部、客户关系部、行政人事部、销售支持、机场网销、武侯展厅、其它。

配置与复制：`config/non_frontline_roles.yaml`、`calculators/non_frontline/classification.py`、`pipelines/non_frontline_columns.py`（overlay 之后执行）；生成的 `提成汇总.xlsx` 与观察台预览均含全部语义列。

### 流水线顺序（overlay 之后）

1. **`bootstrap_non_frontline_physical_columns`**：从金标准 `提成汇总` 按 `店别/职务/姓名` 回填非一线物理列空值（支持部门 M–U、管理岗手工 W/Y 等 Hub 引擎未覆盖格）。
2. **`apply_non_frontline_columns`**：按 `non_frontline_roles.yaml` 将物理列复制到语义列，并**清空**该行物理列，避免导出表与一线表头混读；Hub 缓存在此步之前写入，F–P / W–AI 对账仍按物理列比对。
3. **`CommissionSummaryBuilder._align_to_template`**：列序与模板对齐后导出。

### 对账高亮与语义列

- `expand_highlight_columns`：琥珀 mismatch / 灰蓝 deferred 着色时，若比对列含物理列则同时着色对应语义列（反之亦然）。
- `highlight_column_for_row`：非一线行按 tier 映射决定 Excel 上着色的列名（金标准物理列 vs 系统语义列）。

配置：`parity.auto_highlight: true`（`month.yaml`）时，`compute` 与发薪试算在 **`export_excel` 之后** 调用 `apply_commission_summary_highlighting`，与 `reconcile` 同色图例与批注。

### 琥珀格批注格式

`format_mismatch_comment_text` 三行结构：

1. 标题（默认「数值不一致」）
2. `金标准: … | 系统: … | 差: …`
3. `原因: …` — 由 `enrich_cell_mismatches` / `lookup_mismatch_root_cause` 解析：YAML 个案、`wa_parity_deferred`、金标准 topology 公式（含 #REF! / SUMIF 列说明）、非一线列映射、F–P / W–AI 分层兜底。

拓扑 anomaly 扫描会用金标准 workbook D 列校验 `hub_excel_row` 与登记姓名一致（如 **刘波** 行 32），避免错位格误标橙色。

实现：`pipelines/non_frontline_columns.py`、`pipelines/commission_summary_formatting.py`、`calculators/sales_advisor/parity_annotations.py`、`utils/excel_format.py`。

