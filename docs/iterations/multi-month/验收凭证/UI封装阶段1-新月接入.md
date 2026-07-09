# UI 封装阶段 1 验收凭证：新月接入 Streamlit 页

**日期：** 2026-07-02  
**目标：** 在观察台新增「新月接入」表单页，直接保存销售账套至 `data/raw/<账期>/` 并调用 `cmd_onboard_month` 注册账期。

## 变更文件

- `salary_pipeline/app/pages/0_新月接入.py` — Streamlit 表单页
- `salary_pipeline/app/onboard_helpers.py` — 可测 helper（校验、保存路径、继承月份列表）
- `salary_pipeline/app/_nav.py` — 「上传」分组新增导航项
- `tests/test_onboard_ui.py` — 8 项 helper 单元测试

## UI 布局（文字 mockup）

```
┌─────────────────────────────────────────────────────────────┐
│ 新月接入                                                     │
│ 上传销售账套 · 选择规则来源 · 一键生成 month 配置并注册账期   │
├─────────────────────────────────────────────────────────────┤
│ [info] 将销售账套直接保存到 data/raw/<账期>/ …               │
│                                                              │
│ ── 基础信息 ──                                               │
│ 账期 (YYYY-MM)          │ 显示名称                           │
│ [ 2026-07          ]    │ [ 2026年07月              ]        │
│                                                              │
│ 销售账套 (.xlsx)  [ Choose File ]                            │
│                                                              │
│ ── 规则来源 ──                                               │
│ ○ 🗂️ 继承历史规则（适用于无公式的纯数据月）                   │
│ ● ⚙️ 从新表提取规则（适用于有公式的样板月）                   │
│                                                              │
│ （选中「继承」时显示）                                       │
│ 继承自账期  [ 2026-05 ▼ ]                                    │
│                                                              │
│              [ 🚀 一键建档 (Onboard) ]                       │
└─────────────────────────────────────────────────────────────┘
```

**联动逻辑：**

- `st.radio` 互斥选择继承 / 提取模式
- 选「继承历史规则」→ 显示 `st.selectbox`，选项来自 `discover_months()`，排除当前填写的目标账期
- 选「从新表提取规则」→ 隐藏 selectbox，提交时 `extract_topology=True`

## 核心：直接保存至 data/raw/<month>/

```python
# salary_pipeline/app/onboard_helpers.py
def save_sales_workbook(month_id, uploaded_bytes, uploaded_filename) -> Path:
    dest = sales_save_path(month_id, uploaded_filename)
    os.makedirs(dest.parent, exist_ok=True)  # raw_month_dir(month_id)
    dest.write_bytes(uploaded_bytes)
    return dest
```

页面提交时：

```python
saved_path = save_sales_workbook(month_clean, sales_file.getvalue(), sales_file.name)
sales_rel = sales_relative_path(saved_path)  # e.g. data/raw/2026-07/销售账套-合并-2026-07.xlsx
```

- 上传文件保留原始 `.xlsx` 文件名
- 非 xlsx 扩展名时回退为 `销售账套-合并-{month_id}.xlsx`

## 核心：调用 cmd_onboard_month

```python
args = argparse.Namespace(
    month=month_clean,
    sales=sales_rel,
    rules=None,
    sheet_sources=None,
    label=label_trimmed,
    extract_topology=(rule_mode == RULE_EXTRACT),
    inherit_topology=inherit_month if rule_mode == RULE_INHERIT else None,
)

stdout_buf = io.StringIO()
with contextlib.redirect_stdout(stdout_buf):
    rc = cmd_onboard_month(args)

if rc == 0:
    st.balloons()
    st.success(f"账期已注册。配置：salary_pipeline/config/month-{month_clean}.yaml")
else:
    st.error(f"建档失败（退出码 {rc}）")
    st.code(stdout_buf.getvalue())
```

不经过 subprocess；stdout 重定向用于在 UI 展示 CLI 日志。

## 导航注册

```python
# salary_pipeline/app/_nav.py
"上传": [
    st.Page(PAGES_DIR / "0_新月接入.py", title="新月接入", icon="📅"),
    st.Page(PAGES_DIR / "0_发薪上传.py", title="发薪上传", icon="📤"),
],
```

## 单元测试

```bash
$ python -m unittest tests.test_onboard_ui tests.test_multi_month_cli -v
```

```
test_validate_month_id_ok ... ok
test_validate_month_id_errors ... ok
test_save_sales_workbook_writes_bytes ... ok
test_list_inherit_source_months_excludes_target ... ok
... (test_onboard_ui 8 项 + test_multi_month_cli 12 项)

Ran 20 tests in 0.082s
OK
```

完整输出见 [`_stage_ui_onboard_test_output.txt`](./_stage_ui_onboard_test_output.txt)。

## 验收清单

| 项 | 结果 | 证据 |
|----|------|------|
| 新页面 `0_新月接入.py` 遵循 `_shared` 模式 | ✅ | `set_page_config` / `init_session_state` / `render_sidebar` |
| `st.form` 向导：基础信息 + 规则来源 + 提交 | ✅ | 页面源码 |
| `month_id` YYYY-MM 校验 | ✅ | `validate_month_id` + `test_validate_month_id_*` |
| 上传文件直接写入 `data/raw/<month>/` | ✅ | `save_sales_workbook` + `test_save_sales_workbook_writes_bytes` |
| 继承模式 selectbox 排除目标账期 | ✅ | `list_inherit_source_months` + 测试 |
| 提交调用 `cmd_onboard_month`（非 subprocess） | ✅ | 页面 `argparse.Namespace` + stdout 重定向 |
| 成功 balloons + success；失败 error + CLI 输出 | ✅ | 页面逻辑 |
| `_nav.py` 上传分组新增「新月接入」 | ✅ | `_nav.py` |
| 测试全部通过 | ✅ | 20 tests OK |

## 最高规则合规

- ✅ UI 仅保存用户上传的销售账套字节，不从金标准 xlsx 拷贝数值
- ✅ 继承模式复用已有拓扑 JSON 路径（`cmd_onboard_month` + `no_golden=True`），不写入金标准单元格
- ✅ 失败时展示 CLI 退出码与 stdout，不静默 fallback
