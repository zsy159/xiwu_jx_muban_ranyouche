# 迭代 0 工作日志

## 2026-06-23

### 1. 建立迭代文档目录

- 新增 `docs/iterations/` 及 `iteration-0/`，与总规划 `docs/迭代文档.md` 分离。
- 本文件夹存放任务清单、日志与 `artifacts/` 脚本产出。

### 2. 修复拓扑解析器（T1）

**问题：** `build_unquoted_sheet_pattern` 仅匹配 `[A-Za-z0-9_]+`，导致 `销售任务及完成率!C:C` 未被识别，被 `LOCAL_COLUMN_PATTERN` 误记为当前 sheet `提成汇总!C:C`。

**修改：** `scripts/extract_formula_topology.py`

- 无引号 sheet 模式改为使用工作簿内**全部** sheet 名（按长度降序，避免前缀歧义）。
- 新增 `mask_sheet_qualified_references`，在解析本 sheet 单元格/列引用前，同时屏蔽 external、quoted、unquoted 三类跨表引用。

### 3. 依赖闭包脚本

- 新增 `scripts/closure_report.py`：从拓扑 JSON 以 `提成汇总` 为锚点 BFS 展开公式格依赖，输出 JSON + Markdown 至 `artifacts/`。

### 4. 验收命令

```bash
python scripts/extract_formula_topology.py --month 2026-05
python -c "import json; c=json.load(open('data/topology/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).topology.json'))['cells']['提成汇总!F3']; print(c['depends_on_ranges'])"
python scripts/closure_report.py --month 2026-05
```

验收结果见下方「验收记录」小节（重跑后填写）。

---

## 验收记录

| 检查项 | 预期 | 实际 | 通过 |
|--------|------|------|------|
| F3 range deps | 含 `销售任务及完成率!C:C`、`销售任务及完成率!Y:Y` | `['销售任务及完成率!C:C', '销售任务及完成率!Y:Y']` | ✅ |
| 闭包报告生成 | `artifacts/closure_提成汇总.md` 存在 | 16 个公式 sheet、2 个纯输入 sheet | ✅ |
| reconcile 框架 | CLI 可运行 | `python main.py reconcile` 正常输出分岗位报告（stub 模块预期 FAIL） | ✅ |

### 闭包摘要（`提成汇总` 锚点）

- **闭包公式 sheet（16）**：含 `销售任务及完成率`、`绩效整理表` 及各类岗位提成子表（`XW提成-发` 等）
- **纯输入 sheet（2）**：`保客考核明细`、`直营店交车`
- **未进入闭包（示例）**：`终端明细表`、`整车成本`、`按揭明细`、`保险明细`、`渗透率` 等 — 说明这些表不直接参与 `提成汇总` 公式链，或经中间表间接引用（迭代 1 起按闭包逐项接入）

### 迭代 0 结论

基础能力已就绪，可进入**迭代 1**（`data_loader` + 汇总枢纽 `提成汇总` 首列对账）。

---

## 2026-06-23（续）业务分层澄清

### 背景

财务确认：`XW提成-发` 等「发」表才是**最终发薪表**；`提成汇总` 是**汇总枢纽**，约 55% 发薪表公式格通过 `SUMIF` 从汇总表取数。汇总表少量列（BB/BC）回引发薪表，Excel 内形成环。

### 文档与配置更新

- `docs/迭代文档.md` v0.4：`hub` / `output` 双层结构、双锚点闭包说明
- `sheet_registry.yaml`：`提成汇总` → `hub`；`XW提成-发` 等 → `output`
- `closure_report.py`：报告增加术语说明；修复区域引用（整列 SUMIF）不展开上游公式 sheet 的问题

### 双锚点闭包（2026-05 西物）

| 锚点 | 闭包公式 sheet | 纯输入 sheet | 要点 |
|------|----------------|--------------|------|
| `提成汇总` | 16 | 2 | 往上追汇总自身所需；含因回引而进入的「发」表 |
| `XW提成-发` | 43 | 14 | 往上追发薪表所需；**含 `提成汇总` 枢纽**及更长上游链 |

产物：`artifacts/closure_提成汇总.md`、`artifacts/closure_XW提成-发.md`
