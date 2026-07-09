# 阶段 1 验收凭证：CLI --month 选择器

**日期：** 2026-07-02  
**目标：** 所有子命令支持 `--month`；未知月份报错；`golden_workbook` 为 null 时 compute/reconcile 跳过对账

## 变更文件

- `salary_pipeline/main.py` — 新增 `_default_month`、`_resolve_month_config`、`_config_from_args`、`_has_golden_workbook`、`_add_month_arg`；所有 `cmd_*` 改用 `load_month_config_for`；null golden 跳过逻辑
- `tests/test_multi_month_cli.py` — 阶段 1 单元测试（6 项）

## 执行命令与输出

### 1. `--month` 解析已注册月份

```bash
$ python -c "
from salary_pipeline.main import _config_from_args
import argparse
for m in ('2026-02','2026-04','2026-05'):
    cfg = _config_from_args(argparse.Namespace(month=m))
    print(m, cfg['month'])
"
```

```
2026-02 2026-02
2026-04 2026-04
2026-05 2026-05
```

### 2. 未知月份报错并提示 onboard-month

```bash
$ python main.py reconcile --month 2099-12 2>&1; echo exit:$?
```

```
Unknown month '2099-12'. Registered: 2026-02, 2026-04, 2026-05. Onboard with: python main.py onboard-month --month 2099-12 ...
exit:1
```

### 3. 默认月份来自 months_registry

```bash
$ python main.py compute --help 2>&1 | grep month
```

```
  --month YYYY-MM       账期（默认 months_registry default_month=2026-05）
```

### 4. null golden：reconcile 跳过

```bash
$ python -c "
import salary_pipeline.main as m, argparse
cfg = m.load_month_config_for('2026-05')
cfg['parity']['golden_workbook'] = None
args = argparse.Namespace(month='2026-05', computed=None, golden=None, sheet=None, report_dir=None, verbose=False)
orig = m._config_from_args
m._config_from_args = lambda a: cfg
print(m.cmd_reconcile(args))
m._config_from_args = orig
"
```

```
[reconcile] 本月无金标准，跳过
0
```

### 5. 单元测试全绿

```bash
$ python -m unittest tests.test_multi_month_cli -v
```

```
Ran 6 tests in 0.052s
OK
```

## 验收清单

| 项 | 结果 | 证据 |
|----|------|------|
| compute 支持 --month | ✅ | help 输出 |
| reconcile 支持 --month | ✅ | parser 已添加 `_add_month_arg` |
| compute-aftersales 支持 --month | ✅ | 同上 |
| reconcile-aftersales 支持 --month | ✅ | 同上 |
| compute-payout 支持 --month | ✅ | 同上 |
| reconcile-payout 支持 --month | ✅ | 同上 |
| compute-all 支持 --month | ✅ | 同上 |
| export-performance-sheet 支持 --month | ✅ | 同上 |
| 默认月份 2026-05 | ✅ | registry + help 文本 |
| 02/04/05 配置正确解析 | ✅ | 命令 1 |
| 未注册月份 SystemExit | ✅ | 命令 2 |
| null golden reconcile 跳过 | ✅ | 命令 4 |
| null golden compute --reconcile 跳过 | ✅ | 单元测试 |

## 最高规则合规

- ✅ null golden 时不读取金标准、不写金标准数值到 computed output
- ✅ reconcile 跳过而非 fallback 到 sales_workbook
- ✅ compute 仅写系统计算产出，无 golden bootstrap 路径新增

## 剩余风险 / 下阶段

- `AftersalesPipeline` / `ChannelPayoutPipeline` 仍从 `month.yaml` 加载配置（阶段 2 注入 `month_config`）
- `month.yaml`（2026-05）仍指向 `placeholder.xlsx`，对该月执行 reconcile 会因文件不存在而报错（既有配置问题）
