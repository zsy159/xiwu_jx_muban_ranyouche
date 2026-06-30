# 迭代 2 工作日志

## 2026-06-23

### 交付

1. **`salary_pipeline/ops/lookup.py`** — `lookup_match_index`、`sumifs_by_keys`、`if_ladder`
2. **`HubFormulaEngine`** — 按拓扑 `execution_order`（F–P 列）多轮求值
3. **公式模式** — SUMIF、SUM 区块、INDEX/MATCH、SUMIFS、跨行引用、简单算术
4. **`#REF!`** — 跳过并写入 `output/2026-05/reports/formula_warnings.txt`
5. **对账范围** — `parity.columns` 扩展至 11 列（考核量 … 按揭毛利）

### 关键修复

- **多轮求值**：`F106=SUM(F90:F105)` 依赖的子行在拓扑序中靠后，需 8 轮 pass 才能收敛
- **SUMIF 全 NaN**：Excel 视为 0，`sumif_by_key` 对 `fillna(0)` 对齐

### 验收

- F–P：**96.3%** 单元格一致（66 处差异均可归类为静态格 / #REF!）
- 钟小丽等网销经理行：考核量 114、完成率 0.64 — 与金标准一致

### 下一步（迭代 3）

- 扩展引擎至 Q–AJ（绩效、提成合计…）
- 管理岗静态格策略（规则表 or 职务级模板）
- 售后账套 `pipelines/aftersales.py`
