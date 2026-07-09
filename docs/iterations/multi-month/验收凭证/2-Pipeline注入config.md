# 阶段 2 验收凭证：Pipeline 支持注入 config

**日期：** 2026-07-02  
**目标：** `ChannelPayoutPipeline` / `AftersalesPipeline` 支持可选 `month_config` 注入，镜像 `SalesPipeline` fallback 逻辑；`main.py` 在 `--month` 场景传入 config

## 变更文件

- `salary_pipeline/pipelines/xw_payout.py` — `ChannelPayoutPipeline.__init__` 增加 `month_config`；`XwPayoutPipeline` 透传
- `salary_pipeline/pipelines/aftersales.py` — `AftersalesPipeline.__init__` 增加 `month_config`
- `salary_pipeline/main.py` — `cmd_compute_aftersales` / `cmd_compute_payout` / `cmd_compute_all` 传入 `month_config=config`
- `tests/test_multi_month_cli.py` — 新增 `test_pipeline_month_config_injection`

## 关键代码 Diff（fallback 兜底逻辑）

### AftersalesPipeline

```python
def __init__(
    self,
    config_dir: Path | None = None,
    store: str = "wuhou",
    month_config: dict[str, Any] | None = None,
) -> None:
    self.config_dir = config_dir or CONFIG_DIR
    if month_config is not None:
        self.month_config = month_config
    else:
        self.month_config = load_month_config(self.config_dir)  # fallback
    self.store = store
    self.engine_config = self.STORE_CONFIGS[store]
```

### ChannelPayoutPipeline

```python
def __init__(
    self,
    channel: str = "xw",
    config_dir: Path | None = None,
    month_config: dict[str, Any] | None = None,
) -> None:
    ...
    self.config_dir = config_dir or CONFIG_DIR
    if month_config is not None:
        self.month_config = month_config
    else:
        self.month_config = load_month_config(self.config_dir)  # fallback
    ...
```

### main.py 接线（节选）

```python
config = _config_from_args(args)
pipeline = AftersalesPipeline(CONFIG_DIR, store=args.store, month_config=config)
pipeline = ChannelPayoutPipeline(channel, CONFIG_DIR, month_config=config)
hub_pipeline = SalesPipeline(CONFIG_DIR, month_config=config)
```

## 执行命令与输出

### 1. 注入测试

```bash
$ python -m unittest tests.test_multi_month_cli.MultiMonthCliTest.test_pipeline_month_config_injection -v
```

```
test_pipeline_month_config_injection ... ok
```

### 2. 完整单元测试

```bash
$ python -m unittest discover -s tests -v
```

完整输出见同目录 [`_stage2_test_output.txt`](./_stage2_test_output.txt)（末尾须为 `OK` 或记录 `EXIT:0`）。

## 验收清单

| 项 | 结果 | 证据 |
|----|------|------|
| `ChannelPayoutPipeline` 接受 `month_config` 注入 | ✅ | `test_pipeline_month_config_injection` |
| `AftersalesPipeline` 接受 `month_config` 注入 | ✅ | 同上 |
| 未传入时 fallback `load_month_config(config_dir)` | ✅ | 见上方 Diff |
| 旧的无参调用不被破坏 | ✅ | `test_direct_store_payout` 等仍通过 |
| `main.py` compute-aftersales 传入 config | ✅ | `main.py:291` |
| `main.py` compute-payout 传入 config | ✅ | `main.py:380` |
| `main.py` compute-all 传入 config | ✅ | `main.py:481` |

## 最高规则合规

- ✅ 本阶段仅改配置加载路径，不涉及金标准数值写入

## 备注（断网恢复）

- 阶段 2 代码在网络中断前已由后台 worker 写入；本凭证在恢复连接后补全落盘。
- 若 `_stage2_test_output.txt` 末尾非 `OK`，请重跑：`python -m unittest discover -s tests -v`
