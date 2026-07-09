"""销售顾问岗位族绩效 — Phase B 绩效整理表 + 声明式规则写 Hub W–AI。"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from salary_pipeline.calculators.sales_advisor.extract import match_advisor_row
from salary_pipeline.calculators.sales_advisor.registry import (
    hub_columns_for_gate,
    is_hub_linked,
    list_roles,
)
from salary_pipeline.config.hub_performance_loader import load_hub_performance_config
from salary_pipeline.data_ingestion.data_loader import build_workbook_loader
from salary_pipeline.pipelines.hub_rule_engine import HubRuleEngine
from salary_pipeline.modules.base import (
    SUMMARY_KEY_COLUMNS,
    BaseCommissionModule,
    ModuleResult,
)

logger = logging.getLogger(__name__)

FAMILY_ID = "销售顾问"
_ROLE_BY_NAME = {r["name"]: r for r in list_roles()}


class SalesAdvisorPerformanceModule(BaseCommissionModule):
    """
    形态 C：Phase B computed 绩效整理表 → Hub W–AI 显式算薪。

    - 读 ``computed_perf_frame``（PerformanceSheetModule 输出）
    - 公式来自 HubRuleEngine 声明式规则（config/hub_column_rules.yaml），按
      店别判定整车绩效乘数（门店块 ×BA / 个人 ×H），不再依赖 topology 行号回放
    - 仅 hub_linked 顾问写 overlay；子表全员见 销售提成标准
    - 2026-07-07 起 ``match_advisor_row`` 同时覆盖销售主管/销售助理（用户要求
      所有销售类岗位统一规则），三者共用同一 hub_column_rules 家族与本模块
    """

    name = "sales_advisor_performance"
    roles = ["销售顾问", "销售主管", "销售助理"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        hub_cfg = load_hub_performance_config()
        family = hub_cfg.get("role_families", {}).get(FAMILY_ID, {})

        skeleton = context.get("summary_skeleton")
        perf_frame = context.get("computed_perf_frame")
        if skeleton is None or skeleton.empty:
            logger.warning("%s: empty summary_skeleton", self.name)
            return ModuleResult(
                module_name=self.name,
                roles=self.roles,
                metrics=pd.DataFrame(columns=SUMMARY_KEY_COLUMNS),
                metadata={"status": "no_skeleton"},
            )
        if perf_frame is None or perf_frame.empty:
            logger.warning("%s: missing computed_perf_frame", self.name)
            return ModuleResult(
                module_name=self.name,
                roles=self.roles,
                metrics=pd.DataFrame(columns=SUMMARY_KEY_COLUMNS),
                metadata={"status": "no_perf_frame"},
            )

        loader = build_workbook_loader(context)
        gate_cols = hub_columns_for_gate()
        engine = HubRuleEngine()
        rule_family = engine.role_families.get(FAMILY_ID, {})

        rows: list[dict[str, Any]] = []
        for _, person in skeleton.iterrows():
            if not match_advisor_row(person):
                continue
            name = str(person["姓名"])
            role = _ROLE_BY_NAME.get(name)
            if role is not None and not is_hub_linked(role):
                continue

            rate = person.get("销量完成率")
            h_rate = float(rate) if pd.notna(rate) else 0.0
            hub_metrics = engine.compute_row(
                name=name,
                store=person.get("店别"),
                h_rate=h_rate,
                perf_frame=perf_frame,
                family_cfg=rule_family,
                loader=loader,
            )
            row_data: dict[str, Any] = {
                "店别": person["店别"],
                "职务": person["职务"],
                "姓名": name,
            }
            for col in gate_cols:
                if col in hub_metrics:
                    row_data[col] = hub_metrics[col]
            for col, val in hub_metrics.items():
                if col not in row_data:
                    row_data[col] = val
            rows.append(row_data)

        metric_cols = sorted(
            {c for row in rows for c in row if c not in SUMMARY_KEY_COLUMNS}
        )
        metrics = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=[*SUMMARY_KEY_COLUMNS, *metric_cols])
        )
        logger.info(
            "%s: matched=%s rules_sheet=%s perf_rows=%s",
            self.name,
            len(metrics),
            family.get("rules_sheet", "销售提成标准"),
            len(perf_frame),
        )
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=metrics,
            metadata={
                "family_id": FAMILY_ID,
                "rules_sheet": family.get("rules_sheet", "销售提成标准"),
                "algorithm": "hub_rule_engine",
                "source": "computed_perf_frame",
                "hub_linked_only": True,
                "rows": len(metrics),
                "hub_columns": list(gate_cols),
            },
        )
