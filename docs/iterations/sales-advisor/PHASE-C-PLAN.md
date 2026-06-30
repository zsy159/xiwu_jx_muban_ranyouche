# 销售顾问 Phase C — 业务模块实施记录

**账期样板：** 2026-05  
**状态：** Phase C 骨架 ✅（`sales_advisor_performance` + 对账验收门槛）  
**最后更新：** 2026-06-25

## 目标

`销售提成标准` + Phase B `绩效整理表` → 显式业务规则写 Hub W–AI，不再仅依赖 `HubFormulaEngine` 拓扑回放。

```text
明细层 → PerformanceSheetModule → computed_perf_frame
                                      ↓
              SalesAdvisorPerformanceModule（topology 公式解析 + SUMIF/SUMIFS）
                                      ↓
              performance_overlay → 提成汇总 W–AI
```

## 交付物

| 路径 | 作用 |
|------|------|
| `config/sales_advisor_roles.yaml` | hub_linked 49 人 + 子表样例 |
| `calculators/sales_advisor/` | topology 解析、公式求值、金标准对照 |
| `modules/sales_advisor_performance.py` | 流水线模块 |
| `config/hub_performance.yaml` | `module` + `parity_gate: true` |
| `config/role_field_alignment/sales_advisor.yaml` | Phase D 字段拉通预备 |
| `app/pages/算薪/8_销售顾问.py` | 观察台算薪页 |
| `tests/test_sales_advisor_performance.py` | 单元 + 流水线对账 |

## hub_linked 策略（N5）

| 集合 | 规模 | 行为 |
|------|------|------|
| 提成汇总 `职务=销售顾问` 且姓名有效 | **49** 可比人 | `hub_linked: true`，模块写 W–AI overlay |
| 提成汇总「空白」占位行 | 2 | 跳过 |
| `销售提成标准` JSON 顾问记录 | 53 | 子表全员算薪 |
| 仅子表、不进 Hub | 如徐荣尧 | `hub_linked: false` |

## 公式模式（样本月）

| Hub 列 | 典型公式 |
|--------|----------|
| W 整车绩效 | `SUMIFS(AG,P,姓名) × H` 或 `× BA`（门店块） |
| X 权限结余 | `SUMIFS(AH,P,姓名)` |
| Y 加装绩效 | `SUMIFS(AI,P,姓名) × H`；无公式时读静态格 |
| Z 保险绩效 | `SUMIFS(AJ,P,姓名) × H` 或 `+600`（韩柏成） |
| AA–AI | `SUMIF` / 双 `SUMIF` 链 |

绩效整理表求值帧与 `HubFormulaEngine` 对齐：金标准底表 + computed VIN 覆盖（`build_eval_perf_frame`）。

## 验收

```bash
python -m unittest tests.test_sales_advisor_performance -v
python main.py compute --reconcile
# gated_performance → 销售顾问 mismatch_cells=0
```

## 与 Phase D 边界

| Phase C（本批） | Phase D（待做） |
|----------------|----------------|
| 模块 + 对账验收门槛 | 观察台字段拉通按店别版式 |
| topology 驱动公式 | 逐步内化常数/特例到 `sales_advisor_roles.yaml` |
| 销售主管仍走引擎 | 主管+顾问统一 `BaseCommissionModule`（T4） |

## 已知余量

- 部分列（如韩柏成 Y 列加装绩效）无 topology 公式，回读金标准静态值
- `gated_performance` 全层仍因其他岗位 W–AI 未模块化而 `overall_passed=false`；销售顾问子集已绿
