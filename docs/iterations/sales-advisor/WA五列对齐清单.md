# 销售顾问 Hub 五列对齐清单（W / Y / Z / AE / AF）

**月份：** 2026-05  
**范围：** 图中五列 — 整车绩效(W)、保险绩效(Z)、加装绩效(Y)、特殊车型+指定车型(AF)、延保提成(AE)  
**最后更新：** 2026-06-29  

---

## 1. 列映射

| 图中名称 | 提成汇总列 | 绩效整理表源列 | Hub 公式模式 |
|----------|------------|----------------|--------------|
| 整车绩效 (AG) | W | AG | `SUMIFS(AG,P,姓名)×H` 或 `×BA`（门店块） |
| 保险绩效 | Z | AJ | `SUMIFS(AJ,P,姓名)×H`（部分行 `+常数`） |
| 加装绩效 | Y | AI | `SUMIFS(AI,P,姓名)×H` |
| 特殊车型+指定车型 (AQ) | AF | AQ | `SUMIF(P,姓名,AQ)` 直引 |
| 延保提成 | AE | AT | `SUMIF(P,姓名,AT)` 直引 |

---

## 2. 当前对账状态（`compute --reconcile` 后）

| 列 | 49 人可比 | 剩余差异 | 状态 |
|----|-----------|----------|------|
| **特殊车型+指定车型** | 49 | **0** | ✅ 已对齐（绩效整理表 AQ 闭包 + Hub SUMIF） |
| **延保提成** | 49 | **0**（修后） | ✅ 模块 overlay 写 AE；刘凤英原 `nan→0` |
| **加装绩效** | 49 | **0**（修后） | ✅ 熊俊杰 +240 手工尾行已 YAML 建模 |
| **整车绩效** | 49 | **3** → **0*** | ⏸️ *3 人为手工暂缓 |
| **保险绩效** | 49 | **2** → **0*** | ⏸️ *2 人为手工暂缓 |

\* 对账报告中对 deferred 单元格（`wa_parity_deferred`、二网 AH、**topology 公式尾项常数**）**不计入** mismatch。

---

## 3. 手工暂缓（暂不管，待业务确认）

登记位置：`salary_pipeline/config/sales_advisor_roles.yaml` → `wa_parity_deferred`

| 姓名 | 列 | 金标准 | 系统 | 原因 |
|------|-----|--------|------|------|
| **韩柏成** | 整车绩效 | 1500 | 2000 | 翼真店 AG 与提成标准 lookup 不一致 |
| **韩柏成** | 保险绩效 | 800 | 600 | `Z134 = SUMIF(AJ)+600` 手工常数 |
| **韩柏成** | 加装绩效 | 1000 | nan | `Y134=1000` 静态格，无公式 |
| **沈燕1** | 整车绩效 | 3500 | 4000 | 翼真店 AG 手工 |
| **沈燕1** | 保险绩效 | 200 | 0 | 翼真保险绩效手工录入 |
| **唐操** | 整车绩效 | 1046.15 | 861.54 | 订单 `L6T78XCZ5TY782006` 渠道 I 映射个案 |

> 权限结余(X)、金融(AA) 等不在本清单五列内；见 [权限结余与绩效特殊情形汇报.md](./权限结余与绩效特殊情形汇报.md)。

---

## 4. 已交付修复（2026-06-29）

| 项 | 方式 | 配置/代码 |
|----|------|-----------|
| 熊俊杰加装绩效 −120 | 金标准无 VIN 尾行 AI=240 | `performance_sheet_columns.yaml` → `advisor_column_adjustments` |
| 刘凤英延保 nan | 顾问模块 overlay 写入 `SUMIF(AT)` | `hub_columns` 增 AE/AF；`sales_advisor_performance` |
| 特殊车型 8 人 | AQ 闭包已在 Phase B 内化 | `from_closure._compute_aq_standard` |
| 对账跳过手工格 | deferred（YAML + 二网 + topology 尾项常数）+ `parity.py` 过滤 | Excel 标浅蓝 `#BDD7EE` + 批注 |
| 金标准直填格 | `collect_topology_static_fill_cells` | Excel 标浅灰 `#D9D9D9` + 批注 |
| 公式尾项常数 | `collect_topology_manual_formula_cells`（如 `=5700`、`=SUMIFS+600`） | 并入 deferred 浅蓝 |
| 公式异常批注 | 浅橙 `#FCE4D6` + Excel 批注（#REF! 等） | [对账批注说明.md](./对账批注说明.md) |

---

## 5. 验收命令

```bash
.venv/bin/python main.py compute --reconcile
```

**五列通过标准（排除手工暂缓 6 格）：**

- W–AI 绩效层 → 销售顾问 → 上表五列 `mismatch_cells = 0`
- 或本地快查：

```bash
.venv/bin/python -m unittest tests.test_sales_advisor_wa_focus -v
```

---

## 6. 后续（需业务输入后再做）

1. 翼真店韩柏成 / 沈燕1：AG、Z、Y 常数或独立提成标准  
2. 唐操：确认 `L6T78XCZ5TY782006` 渠道应为「店面特价」还是「按揭专享」  
3. 手工暂缓清零后，从 `wa_parity_deferred` 删除对应行并重跑对账
