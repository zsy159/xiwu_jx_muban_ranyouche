# 迭代 4 执行记录

## 2026-06-23

### 完成项

1. **`XwPayoutFormulaEngine`**
   - 提成汇总 hub SUMIF（F/G + W–AR 绩效块）
   - 西物基本 payroll SUMIF（AI/AK/AL/AQ，含 AA/AE 变体列）
   - 银河 A/B 子表 AG 列
   - 车展奖励（并税）AJ 列
   - 行内 SUM（横向 H:T、V:AC）与算术链
   - 个税 AZ/BA 表金标准引导

2. **`XwPayoutPipeline` + CLI**
   - `python main.py compute-payout --reconcile`
   - 输出 `output/2026-05/XW提成-发.xlsx`

3. **`payroll_merge.py`**
   - `load_basic_pay_frame()` 封装西物基本读取

4. **对账**
   - `payout_parity`：店别+职务+姓名，9 列核心指标
   - **整体通过**，12 个店别零差异

### 设计决策

- **Hub 数据来源**：迭代 4 从金标准 `提成汇总` 读 SUMIF 源列（与 Excel 一致）；后续可切换为计算版 hub
- **循环依赖**：不实现 hub BB/BC 回引发薪表（打破 Excel 环）
- **#REF! 行**：AC12–AC31 引用损坏的 CS 表格，跳过并记入 warnings

### 后续（迭代 4+）

- `CS提成-发` / `直营店提成-发`：复用引擎 + `超市基本` / `直营店基本`
- 扩展 parity 至 F–AS 全列
- 将 hub 计算版接入（替换金标准引导）

### 2026-06-23（续）闭环 wiring

1. **`hub_frame_loader.py`**
   - `build_hub_sumif_frame()`：金标准 W–AR + 可选覆盖计算版 F–P
   - 计算版列数不足时（如缺 AY）自动跳过越界列

2. **`compute-all` CLI**
   - `python main.py compute-all [--reconcile]`
   - 顺序：提成汇总 → XW提成-发（`use_computed_hub=True` 合并 hub）

3. **`HubFormulaEngine` 扩展 W–AI**
   - 绩效整理表 SUMIFS、横向 SUM、多 SUMIF 链
   - hub F–P 与金标准仍有 ~4% 差异行，故 `compute-payout` 默认仍用金标准 hub

### 验证命令

```bash
python -m unittest discover -s tests -v
python main.py compute-payout --reconcile   # 金标准 hub，parity 通过
python main.py compute-all --reconcile      # 端到端；payout 对账可能因 hub F–P 差异未过
```
