# 新月接入与 Hub 拓扑

**版本：** v0.6.5  
**日期：** 2026-07-01

---

## 1. 两类输入，不要混用

| 类型 | 来源 | 用途 |
|------|------|------|
| **基础数据（uploads）** | 发薪上传 / `data/raw/<月>/uploads/` | 终端明细、任务表、成本、保险等**当月数值** |
| **公式地图（topology）** | 从**带公式的金标准**或上月经确认的 topology 提取 | Hub `提成汇总` F–P 等列的 **`=SUMIF` / `=SUMIFS` 回放** |

合并上传账套 `销售账套-合并-<月>.xlsx` 里的 `提成汇总` 往往是**数值快照**（无公式），**不能**作为 topology 来源，否则 Hub 公式数为 0，F/G 等列全空。

---

## 2. 推荐接入步骤

1. 将当月底层 Excel 放入 `data/raw/<YYYY-MM>/uploads/`，生成 `sheet_sources.json`。
2. **拓扑（二选一）**  
   - **首选**：从当月或样板月金标准 xlsx 提取  
     `python scripts/extract_formula_topology.py`（或内联调用 `extract_workbook_topology`）  
     输出到 `data/topology/<月>/燃油车-…销售提成.topology.json`  
   - **过渡**：公式结构未变时，复用最近月份 topology（如 2026-05），但需对账验证。
3. 新增 `salary_pipeline/config/month-<YYYY-MM>.yaml`，登记 `workbooks`、`topology.sales`、`parity.golden_workbook`（对账只读）。
4. 在 `months_registry.yaml` 注册账期。
5. `python main.py compute` → 检查 `output/<月>/提成汇总.xlsx` 与 `绩效整理表-系统生成.xlsx`。
6. 有金标准时：`python main.py reconcile`。

---

## 3. 人员骨架

- **首次**：可从金标准 `提成汇总` 读取店别/职务/姓名行键（`SummarySkeletonModule`，只读结构）。
- **后续**：财务提供人员表或在观察台维护；不应长期依赖金标准数值 bootstrap。

---

## 4. 2026-02 样例配置

`month-2026-02.yaml`：

- 输入：`data/raw/2026-02/`
- 拓扑：`data/topology/2026-02/燃油车-2026年02月西物超市销售提成.topology.json`（从金标准提取，含 Hub 公式）
- 对账金标准：项目根目录 `燃油车-2026年02月西物超市销售提成.xlsx`（只读）

---

## 5. 常见故障

| 现象 | 原因 | 处理 |
|------|------|------|
| F–P 全空，`computed=0` | topology 来自无公式的合并账套 | 改用金标准 topology |
| 有骨架无数 | 同上 | 同上 |
| 绩效整理表无 xlsx | 旧版 `compute` 未导出（v0.6.5 已修复） | 重跑 `compute` 或 `export-performance-sheet` |
| 对账标色极慢 | `highlight_mode: full` 查根因 | 改为 `mismatch_only`（默认） |

---

## 6. 中长期方向

业务规则每月变化不大时，目标为：**固定一套 Python 规则 + 每月只换 uploads**，topology 逐步内化废弃；金标准仅用于 `reconcile` 验收。
