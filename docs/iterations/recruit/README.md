# 招聘岗位族（2026-05）

**最后更新：** 2026-06-25

## 定义

- **「招聘」** = 销售提成**主工作簿**子表 `招聘`（招聘报表），**不是** `提成依据.xlsx` 里的 sheet。
- **团队分配公式**：`个人提成 = 到岗数 × 单人招聘提成 × 分配比例`
- Hub 挂钩（3 人）：`提成汇总.保险绩效` = 招聘子表该人 **W 列**（与公式结果一致）
- 模块：`recruit_performance`；`hub_performance.yaml` 已登记，`parity_gate: true`

## 2026-05 团队分配（金标准）

| 输入 | 值 |
|------|-----|
| 5月招聘到岗数（S4） | 6 |
| 单人招聘提成（T4） | 100 |
| 团队提成合计（U4） | 600 |

| 姓名 | 分配比例 | 计算提成 | Hub 行 | 保险绩效 |
|------|----------|----------|--------|----------|
| 周小红 | 0.34 | 204 | 197 | 204 |
| 何婷婷 | 0.26 | 156 | 199 | 156 |
| 李玲 | 0.22 | 132 | — | — |
| 刘晓琴 | 0.18 | 108 | 198 | 108 |

> Hub 上 **无** 职务含「招聘」的行；业务叫「招聘提成」，组织职务是行政线。  
> **李玲** 在招聘子表有分配行（W6=132），**不在提成汇总**（`hub_linked: false`），仅在独立模块 / 观察台算薪。

## 数据在哪

| 数据 | 文件 | Sheet / 单元格 |
|------|------|----------------|
| 团队分配块 | `data/raw/2026-05/燃油车-…销售提成(终)(1).xlsx` | **招聘** 行 4–7（Q/S/T/U/V/W） |
| Hub 保险绩效 | 同上 | **提成汇总**（行 197–199，Z 列） |
| 规则文字 | `data/raw/2026-05/提成依据.xlsx` | **销售提成标准** |

`提成依据.xlsx` 仅 6 张 sheet，**没有「招聘」**；`commission_rules/manifest.yaml` **无 `招聘.json`**。

## 实现

| 路径 | 说明 |
|------|------|
| `config/recruit_roles.yaml` | 4 人 + `team_block` 列映射 |
| `calculators/recruit/` | 团队分配公式 + 子表抽取 |
| `modules/recruit_performance.py` | Hub overlay（仅 hub_linked 3 人） |
| `app/pages/算薪/7_招聘.py` | 观察台：团队输入 + 四人分配明细 |
| `config/role_field_alignment/recruit.yaml` + `calculators/field_alignment/recruit.py` | 字段拉通（团队分配块） |
| `tests/test_recruit_performance.py` | 金标准 204 / 156 / 132 / 108 |

## Hub overlay 范围

- **写入 Hub**：周小红、刘晓琴、何婷婷（有 `hub_excel_row`）
- **仅模块算薪**：李玲（`hub_linked: false`，对标客户专员李璐秀模式）

## 验收（2026-06-25）

- [x] `python -m unittest tests.test_recruit_performance -v` — 四人公式与金标准一致
- [x] `python main.py compute --reconcile` — 算薪族 `parity_gate` 通过（招聘 3 人保险绩效）
- [x] `hub_performance.yaml` 登记 + `parity_gate: true`（match 仍仅 3 人）
- [x] 李玲纳入 `recruit_roles.yaml` 与观察台，不写入 Hub overlay
- [x] 字段拉通页已接入（`recruit` 岗位族）
