"""网络/区域顾问岗位族 — Hub W–AI（×BA 或 ×H，同销售顾问模板选择）。"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from salary_pipeline.config.hub_performance_loader import load_hub_performance_config
from salary_pipeline.config.hub_performance_match import row_matches_family
from salary_pipeline.data_ingestion.data_loader import build_workbook_loader
from salary_pipeline.modules.base import (
    SUMMARY_KEY_COLUMNS,
    BaseCommissionModule,
    ModuleResult,
)
from salary_pipeline.pipelines.hub_rule_engine import HubRuleEngine

logger = logging.getLogger(__name__)

FAMILY_ID = "网络顾问"


class NetworkAdvisorPerformanceModule(BaseCommissionModule):
    """
    余才万（网络部）、王海（销售内勤/区域顾问）、余才万3（渠道）等：
    W = SUMIFS(绩效整理表!AG) × BA 或 × H，规则见 hub_column_rules 网络顾问 family。
    """

    name = "network_advisor_performance"
    roles = ["网络部", "区域顾问", "销售内勤", "渠道"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        hub_cfg = load_hub_performance_config()
        family = hub_cfg.get("role_families", {}).get(FAMILY_ID, {})
        match = family.get("match", {})

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
        engine = HubRuleEngine()
        rule_family = engine.role_families.get(FAMILY_ID, {})
        hub_cols = list(family.get("hub_columns") or [])

        rows: list[dict[str, Any]] = []
        for _, person in skeleton.iterrows():
            if not row_matches_family(person, match):
                continue
            name = str(person["姓名"])
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
            for col in hub_cols:
                if col in hub_metrics:
                    row_data[col] = hub_metrics[col]
            rows.append(row_data)

        metric_cols = sorted(
            {c for row in rows for c in row if c not in SUMMARY_KEY_COLUMNS}
        )
        metrics = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=[*SUMMARY_KEY_COLUMNS, *metric_cols])
        )
        logger.info("%s: matched=%s", self.name, len(metrics))
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=metrics,
            metadata={
                "family_id": FAMILY_ID,
                "algorithm": "hub_rule_engine",
                "rows": len(metrics),
            },
        )
