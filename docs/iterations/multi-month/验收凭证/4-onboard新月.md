# 阶段 4 验收凭证：onboard-month 新月注册

**日期：** 2026-07-02  
**目标：** 实现 `onboard-month` CLI，支持继承拓扑（无金标准）或从销售账套提取拓扑；生成 `month-YYYY-MM.yaml` 并注册到 `months_registry.yaml`。

## 变更文件

- `salary_pipeline/ingestion_upload/month_config.py` — `aftersales_topology`、`no_golden` 参数
- `salary_pipeline/observability/loaders.py` — `register_month(..., config=...)`
- `salary_pipeline/main.py` — `cmd_onboard_month` + parser
- `tests/test_multi_month_cli.py` — 新增 4 项测试（共 12 项）

## onboard-month 核心路由

```python
def cmd_onboard_month(args: argparse.Namespace) -> int:
    if args.extract_topology and args.inherit_topology:
        print("[onboard-month] 不能同时使用 --extract-topology 与 --inherit-topology")
        return 1
    if not args.extract_topology and not args.inherit_topology:
        print("[onboard-month] 须指定 --extract-topology 或 --inherit-topology")
        return 1
    # ... validate --sales exists ...

    if args.inherit_topology:
        inherit_cfg = load_month_config_for(args.inherit_topology)
        # validate topology.sales / rules / aftersales JSON exist
        config_path = write_month_config(
            month_id, ..., no_golden=True,
            sales_topology=..., rules_topology=..., aftersales_topology=...,
        )
    else:
        topo_rel = str(extract_sales_topology(sales_path, month_id))
        config_path = write_month_config(month_id, sales_topology=topo_rel, ...)

    register_month(month_id, label, raw_dir, config=config_path.name)
    output_month_dir(month_id).mkdir(...)
    (raw_month_dir(month_id) / "uploads").mkdir(...)
```

## write_month_config `no_golden` diff

```diff
+    aftersales_topology: str | None = None,
+    no_golden: bool = False,
@@
+    if aftersales_topology:
+        cfg["topology"]["aftersales"] = aftersales_topology
@@
-    parity["golden_workbook"] = sales_workbook
-    for channel in ("xw", "direct_store", "cs"):
-        cfg["payout"][channel]["golden_workbook"] = sales_workbook
+    if no_golden:
+        parity["golden_workbook"] = None
+        for channel in ("xw", "direct_store", "cs"):
+            cfg["payout"][channel]["golden_workbook"] = None
+    else:
+        parity["golden_workbook"] = sales_workbook
+        for channel in ("xw", "direct_store", "cs"):
+            cfg["payout"][channel]["golden_workbook"] = sales_workbook
```

## 实机测试

测试前于项目根创建最小 `dummy.xlsx`（openpyxl 空工作簿），测试后已清理。

```bash
$ python main.py onboard-month --month 2026-07 --inherit-topology 2026-05 --sales dummy.xlsx
```

```
[onboard-month] 继承 2026-05 拓扑（无金标准）
[onboard-month] 已注册 2026-07 (2026-07)
[onboard-month] 配置: .../salary_pipeline/config/month-2026-07.yaml
```

### 生成的 month-2026-07.yaml 关键节点

```yaml
workbooks:
  sales: dummy.xlsx
topology:
  sales: data/topology/2026-05/销售账套-合并-2026-05.topology.json
  aftersales: data/topology/2026-05/燃油车-2026年05月吉利超市售后提成(终)(1).topology.json
  rules: data/topology/2026-05/销售账套-合并-2026-05.topology.json
parity:
  golden_workbook: null
payout:
  xw:
    golden_workbook: null
  direct_store:
    golden_workbook: null
  cs:
    golden_workbook: null
```

三条 `topology.*` 均指向 **2026-05** 公式映射；`parity` 与三渠道 `payout.*.golden_workbook` 均为 `null`（未继承金标准单元格数值）。

## 单元测试

```bash
$ python -m unittest tests.test_multi_month_cli -v
```

```
test_onboard_inherit_topology_writes_null_golden ... ok
test_onboard_mutually_exclusive_flags ... ok
test_onboard_requires_topology_mode ... ok
test_write_month_config_no_golden ... ok
... (共 12 tests)

Ran 12 tests in 0.078s
OK
```

完整输出见 [`_stage4_test_output.txt`](./_stage4_test_output.txt)。

## 验收清单

| 项 | 结果 | 证据 |
|----|------|------|
| `write_month_config` 支持 `no_golden` / `aftersales_topology` | ✅ | `month_config.py` + `test_write_month_config_no_golden` |
| `register_month` 写入 `month-<id>.yaml` 文件名 | ✅ | `register_month(..., config=...)` |
| `onboard-month` inherit 分支继承 2026-05 拓扑 | ✅ | 实机输出 + YAML 节选 |
| inherit 时 `golden_workbook` 为 null | ✅ | YAML `parity` / `payout` 节点 |
| extract / inherit 互斥校验 | ✅ | `test_onboard_mutually_exclusive_flags` |
| 须指定拓扑模式 | ✅ | `test_onboard_requires_topology_mode` |
| 创建 `output/<month>/` 与 `data/raw/<month>/uploads/` | ✅ | 实机 `ls` |
| `test_multi_month_cli` 全部通过 | ✅ | 12 tests OK |
| 测试月 2026-07 已清理 | ✅ | 配置/注册表/目录/dummy.xlsx 已删除 |

## 最高规则合规

- ✅ `no_golden=True` 仅继承 **公式拓扑 JSON 路径**，不拷贝金标准单元格数值
- ✅ 未从 `data/raw/**` 金标准 xlsx 读取数值写入 output
