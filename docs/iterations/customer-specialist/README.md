# 客户专员岗位族 — 收尾记录

> 算薪 + Hub 绩效 + 字段拉通 + 观察台，2026-06 批次。

## 验收结论（2026-06-24）

| 层 | 范围 | 结果 |
|----|------|------|
| **算薪（子表）** | 6 人 | ✅ 金标准一致 |
| **Hub W–AI** | 3 人（提成汇总有行） | ✅ 与金标准一致 |
| **Hub F–P** | 客户关系部 3 行 | ✅ 随整体 F–P 通过 |
| **字段拉通** | `line_item_catalog.py` + 页 8 | ✅ 必做/机动/增值 分组 |

### 人员分工

| 姓名 | 提成汇总 | 说明 |
|------|----------|------|
| 张保珍 | ✅ | 整车绩效固定 2000 + 加装绩效 H42 |
| 邓芳 | ✅ | 权限结余 AT7 + 加装 F42 |
| 周舟 | ✅ | 加装 AD3 |
| 李璐秀 | — | 仅子表保客合计 AT14，**不在提成汇总** |
| 郭静 | — | 仅子表保客合计 AT22 |
| 古瑞婷 | — | 仅子表保客合计 AT30 |

`hub_linked: false` 三人不需要补 `hub_mapping`；算薪在观察台 **算薪 → 客户专员** 页完成。

## 关键路径

| 用途 | 路径 |
|------|------|
| 人员配置 | `salary_pipeline/config/customer_specialist_roles.yaml` |
| Hub 模块 | `salary_pipeline/modules/customer_specialist_performance.py` |
| 计算器 | `salary_pipeline/calculators/customer_specialist/` |
| 字段拉通 | `salary_pipeline/config/role_field_alignment/customer_specialist.yaml` |
| 观察台页 | `salary_pipeline/app/pages/算薪/5_客户专员.py` |
| 测试 | `tests/test_customer_specialist_performance.py` |

## 验证命令

```bash
python -m unittest tests.test_customer_specialist_performance tests.test_salary_summary -v
python main.py compute --reconcile
```

## 未做 / 刻意不做

- **parity_gate: true** — 已接线；观察台提成汇总卡显示「算薪族 W–AI 已过」
- **字段拉通完整表单**：必做/机动/增值 38 项已在页 8 分组展示；保客块仍在算薪子页
- **李璐秀等进 Hub**：金标准中无对应行，不扩 scope

## 相关文档

- 做完本批后看什么：[下一步应该做什么.md](../../下一步应该做什么.md)
- Hub 分治设计：[hub-绩效岗位分治.md](../../design/hub-绩效岗位分治.md)
