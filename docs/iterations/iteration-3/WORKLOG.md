# 迭代 3 执行记录

## 2026-06-23

### 完成项

1. **`AftersalesFormulaEngine`**
   - 扩展 `HubFormulaEngine`，支持售后锚点表 `05月提成-武侯售后` / `05月提成-机场售后`
   - 修正 `INDEX_TERM` 正则（中文 sheet 名、无 `+` 的单项 INDEX）
   - 接入中间表：`05基本`、`05月业务提成`、`05月其他部门提成`、`05月车间提成`、`吧台提成`、`保险专员5月外拓`、`综合考核`、`服装扣款`、`超市公积金`
   - AB/AC 个税累计表自金标准引导（迭代 3 合理 shortcut）

2. **`AftersalesPipeline` + CLI**
   - `python main.py compute-aftersales --store wuhou|airport`
   - `python main.py reconcile-aftersales --store wuhou|airport`

3. **骨架对齐**
   - `data_start_row=5`，`_excel_row` 与 Excel 行号一一对应（修复原 off-by-one）

4. **规则库**
   - `scripts/extract_commission_rules.py` → `salary_pipeline/config/commission_rules/*.json` + `manifest.yaml`

5. **对账**
   - `aftersales_parity` 配置；按列字母读取避免合并表头歧义
   - 武侯 D–W：**99.5%** 单元格一致
   - 机场 D–W：**97.1%** 单元格一致

### 收尾修复（同日）

- `SUM(Kn:Ln)` 横向求和：修复 `_sum_range` 仅按行求和的 bug（业务部 6 人链路差异）
- 机场专属 sheet：`钣喷中心`（K 列 SUMIF）、`西物公积金`（P 列 SUMIF）

### 已知剩余差异（武侯）

- `其它` 列 ~11 处：部分行为手工覆盖或 `05基本` K+L 与金标准微差
- `其他补贴` 1 处

### 机场售后

- 97.1% 一致率，0 warnings；剩余差异主要为业务提成 INDEX 与综合考核 SUMIF 抽样偏差

### 验证命令

```bash
python -m unittest discover -s tests -v
python main.py compute-aftersales --store wuhou --reconcile
python scripts/extract_commission_rules.py
```
