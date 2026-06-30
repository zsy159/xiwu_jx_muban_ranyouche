# 迭代 1 工作日志

## 2026-06-23

### 交付

1. **`salary_pipeline/ops/basic.py`** — `sumif_by_key`、`ratio_with_cap`
2. **`WorkbookLoader`** — 按列字母读 `销售任务及完成率`（C/Y/Z），日志输出 `shape`
3. **`HubTaskMetricsCalculator`** — 按拓扑公式填充 `考核量` / `实际销量` / `销量完成率`
4. **`SummarySkeletonModule`** — 从金标准读取行键（店别/职务/姓名 + `_excel_row`）；迭代 1 bootstrap，后续改为模块产出员工全集
5. **`month.yaml`** — `parity.columns` 限定三列对账

### 验收

- 标准 `SUMIF` + `IF 120%` 链路：**95 行零差异**
- `python main.py compute --reconcile`：49 个岗位三列全通过
- 未通过岗位多为：F/G 为静态值或 `=F106` 类聚合引用（非本迭代范围）

### 下一步（迭代 2）

- 小计/分组 `SUM` 行
- 跨 sheet 引用（如 `销售管理岗提成依据 新标`）
- 逐步去掉 skeleton 对金标准 keys 的依赖
