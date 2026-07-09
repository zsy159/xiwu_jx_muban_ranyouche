# Hub 列瘦身试点：集客达成率 → 综合单台毛利

**账期样板：** 2026-05  
**范围：** 提成汇总 Hub 列 I（集客达成率）至 V（综合单台毛利）  
**判定标准：** 发薪表是否直接或间接消费该列（含 Hub 列 → Hub 列 → 发薪 SUMIF 传递链）  
**约束：** 默认生产路径不变；瘦身仅 opt-in（`hub_metrics_rules.pilot_slim.yaml`）

---

## 1. 验证结论摘要

| 列 | Hub 表头 | 销售顾问发薪 | 判定 | 说明 |
|----|----------|--------------|------|------|
| I | 集客达成率 | 间接（DCC 等） | **KEEP** | 发薪 AC「集客考核」= `SUMIF(Hub I)`；销售顾问本人通常无此项，但 payout 引擎已映射 |
| J | 加装额 | 否 | **UNUSED** | 仅派生 K；W–AI 读绩效整理表 AI，不读 Hub J |
| K | 加装销量完成率 | 否 | **UNUSED** | `J/(G×1500)`；无下游 Hub / 发薪引用 |
| L | 保险渗透率 | 否 | **UNUSED** | 管理看板指标；W–AI 不引用 |
| M | 整车毛利 | 否 | **UNUSED** | HubMetrics 汇总整理表 BG；销售顾问发薪 H 来自 Hub W（整理表 AG×完成率），非 M |
| N | 加装毛利 | 否 | **UNUSED** | 同上，整理表 BI；发薪 J 来自 Hub Y |
| O | 保险毛利 | 否 | **UNUSED** | 整理表 AB；发薪 K 来自 Hub Z |
| P | 按揭毛利 | 否 | **UNUSED** | 整理表 AC；发薪 L 来自 Hub AA |
| Q | 爱车宝毛利 | 否 | **UNUSED** | 模板列存在；**生产 HubMetricsRuleEngine 未计算**；非一线语义映射用 |
| R | 上户毛利 | 否 | **UNUSED** | 同上 |
| S | 整车+加装（毛利） | 否 | **UNUSED** | 文档派生 `M+N`；**未实现** |
| T | 综合毛利 | 否 | **UNUSED** | 文档派生 `SUM(M:R)`；**未实现**；非一线映射→台次，不发薪 |
| U | 主营单台毛利 | 否 | **UNUSED** | 文档派生 `S/G`；**未实现** |
| V | 综合单台毛利 | 否 | **UNUSED** | 文档派生 `T/G`；**未实现** |

**销售顾问发薪直接消费的 Hub 列（对照）：** F、G、W、X、Y、Z、AA、AB、AC、AE、AF、AO、AH、AG、AK、AM、AN（及任务乘数 **H**、门店块 **BA**）。均不在 I–V 段。

---

## 2. 传递链分析

### 2.1 发薪 SUMIF 映射（`payout_column_sources.py`）

试点段内仅 **I** 出现在 `_HUB_SUMIF_BY_PAYOUT`：

```text
发薪 AC 集客考核 → Hub I 集客达成率
```

其余发薪绩效列均映射 Hub W–AO / AK / AM / AN。

### 2.2 销售顾问 Hub W–AI（`hub_column_rules.yaml`）

- 乘数：**H**（销量完成率）或 **BA**（合并完成率，非 Hub 物理列）
- 绩效源：**绩效整理表** AG/AH/AI/…，非 Hub M–V
- **不引用** I–V 任一项

### 2.3 Hub F–P 内部派生

```text
J → K（加装销量完成率）     [死胡同]
M…P → S → U（主营单台毛利）  [仅文档；生产未算 S/U]
M…R → T → V（综合单台毛利）  [仅文档；生产未算 T/V]
```

### 2.4 非一线语义列（`non_frontline_columns.py`）

M–V 物理列可 **复制** 到语义列（台次、提成系数等），供导出阅读；**发薪表不 SUMIF 这些语义列**。清除物理列不影响 XW/直营店/CS 发薪对账。

---

## 3. 安全实现建议

| 动作 | 默认生产 | 说明 |
|------|----------|------|
| 从 `hub_metrics_rules.yaml` 删除 J–P | ❌ 暂不 | 会改变默认 Hub 导出列内容（虽不影响发薪） |
| 使用 `hub_metrics_rules.pilot_slim.yaml` | 可选 | 仅 F/G/H/I；需显式 opt-in |
| 从 `SUMMARY_TEMPLATE_COLUMNS` 删 Q–V | ❌ 暂不 | 影响导出列序与对账报告列位 |
| 财务合并模板省略 M–V | ✅ 可以 | 模板层，不接入 ingestion |

**推荐：defer 默认代码删除**；试点结论已固化，待全 Hub 审计后一次性 opt-in 瘦身。

---

## 4. 相关文件

| 文件 | 用途 |
|------|------|
| `salary_pipeline/config/hub_metrics_rules.yaml` | 生产 F–P 规则 |
| `salary_pipeline/config/hub_metrics_rules.pilot_slim.yaml` | 试点 opt-in 规则（F/G/H/I） |
| `salary_pipeline/pipelines/payout_column_sources.py` | 发薪→Hub SUMIF |
| `salary_pipeline/config/hub_column_rules.yaml` | 销售顾问 W–AI |
| `docs/iterations/payout/发薪表-岗位取数与计算逻辑.md` | 发薪列说明 |

---

## 5. 验证方法（可复现）

```bash
# 发薪映射
rg '集客|加装额|渗透率|整车毛利|综合单台' salary_pipeline/pipelines/payout_column_sources.py

# Hub 规则是否引用试点列
rg '集客|加装额|渗透率|整车毛利|综合' salary_pipeline/config/hub_column_rules.yaml

# 生产 metrics 规则列清单
python -c "import yaml; from pathlib import Path; c=yaml.safe_load(Path('salary_pipeline/config/hub_metrics_rules.yaml').read_text()); print([x['hub_column'] for x in c['columns']])"
```
