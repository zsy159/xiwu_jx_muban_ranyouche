# 汽车经销商薪酬结算流水线

将 Excel 提成账套反推为 Python 计算流水线，支持按月跑批与金标准对账。

## 目录结构

```text
jx_muban_ranyouche/
├── main.py                      # 统一入口
├── requirements.txt
├── README.md
├── docs/                        # 文档
│   ├── 迭代文档.md
│   └── 重构需求文档.md
├── data/
│   ├── raw/                     # 原始 Excel（按月份分子目录）
│   │   └── 2026-05/
│   │       ├── 提成依据.xlsx
│   │       ├── 燃油车-…西物超市销售提成….xlsx
│   │       └── 燃油车-…吉利超市售后提成….xlsx
│   └── topology/                # 公式拓扑 JSON（由脚本生成）
│       └── 2026-05/
│           └── *.topology.json
├── output/                      # 运行产出（不提交 git）
│   └── 2026-05/
│       ├── 提成汇总.xlsx        # 系统计算生成
│       └── reports/             # 《差异报告》
├── scripts/
│   └── extract_formula_topology.py
└── salary_pipeline/             # 核心 Python 包
    ├── config/
    │   ├── month.yaml           # 当月路径与对账配置
    │   └── sheet_registry.yaml
    ├── modules/                 # 业务计算模块
    ├── pipelines/               # 流水线编排
    ├── data_ingestion/
    ├── validation/              # 对账比对
    └── paths.py                 # 路径常量（勿散落硬编码）
```

## 环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 常用命令

```bash
# 1. 提取公式拓扑（新月份先放 data/raw/YYYY-MM/）
python scripts/extract_formula_topology.py --month 2026-05

# 2. 运行流水线（模块计算 → 聚合生成提成汇总）
python main.py compute

# 3. 对账比对（计算结果 vs 金标准 Excel）
python main.py reconcile

# 4. 计算后自动对账
python main.py compute --reconcile
```

### 快速工作流（省时间）

| 场景 | 命令 | 大致耗时 |
|------|------|----------|
| 完整重算 + 对账 | `python main.py compute --reconcile` | ~10–17 分钟 |
| **仅对账**（output 已存在，只改 parity/批注配置） | `python main.py reconcile` | ~3–4 分钟 |
| **改单个岗位计算器**（Hub 快照增量） | `python main.py compute --from hub --only sales-advisor` | ~2–5 分钟 |
| 只重算、不对账 | `python main.py compute` | ~7–13 分钟 |

`reconcile` 读取 `output/<月>/提成汇总.xlsx`，**不会**重跑 Hub 引擎与 overlay。改源 Excel / 拓扑 / 绩效配置后必须跑全量 `compute`；改岗位计算器可用 `--from hub --only`。详见 [docs/design/incremental-pipeline.md](docs/design/incremental-pipeline.md)。

## 观察台（财务对账界面）

本地 Streamlit 界面，用于查看各锚点表对账结论、差异下钻与验收摘要导出。

```bash
pip install -r requirements.txt   # 含 streamlit
python run_console.py
# 或：PYTHONPATH=. streamlit run salary_pipeline/app/streamlit_app.py
```

浏览器打开 `http://127.0.0.1:8501`。侧边栏可切换账期；**开发者模式**下可查看公式告警与注册新月份。

## 新月份接入

1. 将三套 Excel 放入 `data/raw/2026-06/`
2. 复制 `salary_pipeline/config/month.yaml` 中的路径为 `2026-06`（或新增 `month-2026-06.yaml` 后切换）
3. 运行 `extract_formula_topology.py --month 2026-06`
4. `python main.py compute --reconcile`

## 设计要点

- **`提成汇总` 是输出表**：由各 `modules/` 计算结果经 `CommissionSummaryBuilder` 聚合生成，不作为输入导入。
- **对账模式**：`reconcile` 将计算版与 `data/raw/` 中金标准 sheet 列级比对，输出 `output/<月>/reports/差异报告_*.md`；某岗位差异为 0 即该岗位逻辑通过。

详细迭代计划见 [docs/迭代文档.md](docs/迭代文档.md)。
