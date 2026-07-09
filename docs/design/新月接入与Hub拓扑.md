# 新月接入与 Hub 拓扑

**版本：** v0.7.0  
**日期：** 2026-07-02

---

## 1. 两类输入，不要混用

| 类型 | 来源 | 用途 |
|------|------|------|
| **基础数据（uploads）** | 发薪上传 / `data/raw/<月>/uploads/` | 终端明细、任务表、成本、保险等**当月数值** |
| **公式地图（topology）** | 从**带公式的金标准**或上月经确认的 topology 提取 | Hub `提成汇总` F–P 等列的 **`=SUMIF` / `=SUMIFS` 回放** |

合并上传账套 `销售账套-合并-<月>.xlsx` 里的 `提成汇总` 往往是**数值快照**（无公式），**不能**作为 topology 来源，否则 Hub 公式数为 0，F/G 等列全空。

---

## 2. CLI 驱动接入流程

多月流水线通过 CLI 注册账期并计算，**无需**手工复制 YAML、改 `months_registry.yaml` 或手写拓扑路径。

### 步骤概览

1. **注册账期**：`python main.py onboard-month ...`（须先备好 `data/raw/<YYYY-MM>/uploads/` 与 `sheet_sources.json`；见下文两种拓扑模式）。
2. **计算产出**：`python main.py compute --month <YYYY-MM>` → 检查 `output/<月>/提成汇总.xlsx` 与 `绩效整理表-系统生成.xlsx`。
3. **对账（可选）**：仅当金标准存在（`parity.golden_workbook` 非空）时：`python main.py reconcile --month <YYYY-MM>`。

所有子命令（`compute`、`reconcile`、`export-performance-sheet`、发薪试算等）均支持 `--month YYYY-MM`；未指定时使用 `months_registry.yaml` 的 `default_month`。

### 拓扑模式（二选一）

| 模式 | 适用场景 | CLI 标志 | 效果 |
|------|----------|----------|------|
| **繁衍新月** | 新月只有 uploads，**无**带公式的金标准账套；公式结构与上月一致 | `--inherit-topology <YYYY-MM>` | 继承指定月的 `topology.sales` / `rules` / `aftersales` JSON 路径；`parity.golden_workbook` 与各渠道 `payout.*.golden_workbook` 均为 `null` |
| **反推旧月** | 新月（或样板月）有**带公式**的金标准销售账套 | `--extract-topology` | 从 `--sales` 提取公式到 `data/topology/<月>/`，写入 `month-<月>.yaml`；可登记金标准路径供对账 |

`--extract-topology` 与 `--inherit-topology` **互斥**，须且仅能指定其一。

### 示例：繁衍新月（无金标准）

当月只有 uploads，无带公式的金标准账套；沿用 2026-05 已验收的 Hub 公式地图：

```bash
# uploads 已就位：data/raw/2026-07/uploads/ + sheet_sources.json

python main.py onboard-month \
  --month 2026-07 \
  --sales data/raw/2026-07/销售账套-合并-2026-07.xlsx \
  --inherit-topology 2026-05 \
  --label "2026年07月"

python main.py compute --month 2026-07
```

`onboard-month` 会：生成 `salary_pipeline/config/month-2026-07.yaml`、注册 `months_registry.yaml`、创建 `data/raw/2026-07/uploads/` 与 `output/2026-07/`。配置中拓扑指向 **2026-05** 的 JSON，**不**继承金标准单元格数值。

### 示例：反推旧月（有金标准公式账套）

从带公式的金标准 xlsx 提取 topology，并登记对账金标准（样板月 02/04 等）：

```bash
python main.py onboard-month \
  --month 2026-02 \
  --sales data/raw/2026-02/销售账套-合并-2026-02.xlsx \
  --extract-topology \
  --label "2026年02月"

python main.py compute --month 2026-02
python main.py reconcile --month 2026-02
```

若 `--sales` 指向的合并账套 `提成汇总` 无公式，改指向含 Hub 公式的金标准路径（如项目根 `燃油车-2026年02月西物超市销售提成.xlsx` 或 `data/raw/2026-02/source/` 下原表）。

拓扑输出示例：`data/topology/2026-02/燃油车-2026年02月西物超市销售提成.topology.json`。

可选参数：`--rules`（提成依据）、`--sheet-sources`。

### 配置模板

`onboard-month` 基于 `salary_pipeline/config/month.template.yaml` 生成各月 `month-<YYYY-MM>.yaml`；`compute` 通过 `load_month_config_for(month)` 注入 `SalesPipeline` / `ChannelPayoutPipeline` / `AftersalesPipeline`，输出路径与拓扑均来自当月配置。

---

## 3. 人员骨架

- **首次**：可从金标准 `提成汇总` 读取店别/职务/姓名行键（`SummarySkeletonModule`，**只读结构**）。
- **后续**：财务提供人员表或在观察台维护；不应长期依赖金标准数值 bootstrap。

---

## 4. 禁止用金标准填系统产出

以下行为**默认禁止**（除非在本项目对话中用户书面同意）：

- 从 `data/raw/**` 或金标准 xlsx **拷贝单元格数值**写入 `output/**/提成汇总.xlsx`、`绩效整理表-系统生成.xlsx`、发薪表等。
- `bootstrap_from_golden`、`use_golden_perf_sheet` 等回退读金标准数值；算不出时应用空值或系统计算值，通过对账/色块暴露差异，**不得**用金标准抹平。

`--inherit-topology` 仅继承 **topology JSON 路径**（公式地图），`golden_workbook=null` 时 `compute` / `reconcile` 跳过对账，符合上述规则。

---

## 5. 2026-02 样例配置

`month-2026-02.yaml`（可由 `--extract-topology` 生成或手工维护）：

- 输入：`data/raw/2026-02/`
- 拓扑：`data/topology/2026-02/燃油车-2026年02月西物超市销售提成.topology.json`（从金标准提取，含 Hub 公式）
- 对账金标准：项目根目录 `燃油车-2026年02月西物超市销售提成.xlsx`（只读）

---

## 6. 常见故障

| 现象 | 原因 | 处理 |
|------|------|------|
| F–P 全空，`computed=0` | topology 来自无公式的合并账套 | 用 `--extract-topology` 从金标准提取，或 `--inherit-topology` 继承有效月份 |
| 有骨架无数 | 同上 | 同上 |
| `Unknown month` | 未 `onboard-month` | 按 §2 注册账期 |
| 绩效整理表无 xlsx | 旧版 `compute` 未导出 | 重跑 `compute` 或 `export-performance-sheet --month <月>` |
| 对账标色极慢 | `highlight_mode: full` | 改为 `mismatch_only`（默认） |

---

## 7. 中长期方向

业务规则每月变化不大时，目标为：**固定一套 Python 规则 + 每月只换 uploads**，topology 通过 `--inherit-topology` 繁衍；金标准仅用于 `reconcile` 验收。公式结构变更时再 `--extract-topology` 或单独更新 topology JSON。
