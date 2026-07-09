"""西物-翼真新媒体（蒋利）— W–AI 无乘数 + 翼真考核 SUMIF 写 AK。"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from salary_pipeline.config.hub_performance_loader import load_hub_performance_config
from salary_pipeline.config.hub_performance_match import row_matches_family
from salary_pipeline.data_ingestion.data_loader import build_workbook_loader
from salary_pipeline.data_ingestion.yizhen_assessment_sheet import (
    SHEET as YIZHEN_SHEET,
    load_yizhen_assessment_frame,
    lookup_yizhen_completion,
)
from salary_pipeline.modules.base import (
    SUMMARY_KEY_COLUMNS,
    BaseCommissionModule,
    ModuleResult,
)
from salary_pipeline.pipelines.hub_rule_engine import HubRuleEngine

logger = logging.getLogger(__name__)

FAMILY_ID = "新媒体翼真"
HUB_COLUMN_AK = "整车完成考核"


class YizhenNewMediaPerformanceModule(BaseCommissionModule):
    """
    蒋利（西物-翼真 / 新媒体）：不走新媒体子表 SUMIF；
    W–AI = SUMIFS(绩效整理表) 无完成率乘数；AK = SUMIF(翼真考核!C, 姓名, AC)。
    """

    name = "yizhen_new_media_performance"
    roles = ["新媒体"]

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
        yizhen_available = loader.has_sheet(YIZHEN_SHEET)
        if not yizhen_available:
            logger.warning(
                "%s: sheet %r missing; AK column leaves empty for 翼真新媒体",
                self.name,
                YIZHEN_SHEET,
            )
        yizhen = load_yizhen_assessment_frame(loader)
        engine = HubRuleEngine()
        rule_family = engine.role_families.get(FAMILY_ID, {})
        hub_cols = list(family.get("hub_columns") or [])

        rows: list[dict[str, Any]] = []
        for _, person in skeleton.iterrows():
            if not row_matches_family(person, match):
                continue
            name = str(person["姓名"])
            hub_metrics = engine.compute_row(
                name=name,
                store=person.get("店别"),
                h_rate=0.0,
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
            if HUB_COLUMN_AK in hub_cols:
                row_data[HUB_COLUMN_AK] = lookup_yizhen_completion(yizhen, name)
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
                "source_sheet": YIZHEN_SHEET,
                "yizhen_sheet_available": yizhen_available,
            },
        )
