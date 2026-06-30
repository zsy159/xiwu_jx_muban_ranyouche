"""新媒体岗位族 W 列（整车绩效）— 试点：依据子表 SUMIF，非 hub 拓扑回放。"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from salary_pipeline.calculators.new_media.finance_inputs import load_finance_hub_overrides
from salary_pipeline.config.hub_performance_loader import load_hub_performance_config
from salary_pipeline.data_ingestion.data_loader import build_workbook_loader, normalize_name
from salary_pipeline.data_ingestion.new_media_sheet import (
    lookup_vehicle_performance,
    load_new_media_performance_frame,
)
from salary_pipeline.modules.base import (
    SUMMARY_KEY_COLUMNS,
    BaseCommissionModule,
    ModuleResult,
)

logger = logging.getLogger(__name__)

FAMILY_ID = "新媒体"
HUB_COLUMN = "整车绩效"


def _row_matches_family(row: pd.Series, match: dict[str, str]) -> bool:
    for col, expected in match.items():
        if col not in row.index:
            return False
        if normalize_name(str(row[col])) != normalize_name(expected):
            return False
    return True


class NewMediaPerformanceModule(BaseCommissionModule):
    """
    形态 B：主账套「新媒体」子表 Y→AB，等价于 hub 公式
    =SUMIF(新媒体!Y:Y, Dn, 新媒体!AB:AB)。

    不含「西物-翼真 / 新媒体」等走绩效整理表 SUMIFS 的行（另一算法族）。
    """

    name = "new_media_performance"
    roles = ["新媒体销售部", "新媒体运维主管", "短视频专员", "运维专员", "主播"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        hub_cfg = load_hub_performance_config()
        family = hub_cfg.get("role_families", {}).get(FAMILY_ID, {})
        match = family.get("match", {"店别": "新媒体销售部"})

        skeleton = context.get("summary_skeleton")
        if skeleton is None or skeleton.empty:
            logger.warning("%s: empty summary_skeleton", self.name)
            return ModuleResult(
                module_name=self.name,
                roles=self.roles,
                metrics=pd.DataFrame(columns=[*SUMMARY_KEY_COLUMNS, HUB_COLUMN]),
                metadata={"status": "no_skeleton"},
            )

        loader = build_workbook_loader(context)
        source = load_new_media_performance_frame(loader)
        month = context.get("month_config", {}).get("month", "")
        finance_overrides = load_finance_hub_overrides(month) if month else {}

        rows: list[dict[str, Any]] = []
        for _, person in skeleton.iterrows():
            if not _row_matches_family(person, match):
                continue
            name = str(person["姓名"])
            if name in finance_overrides:
                perf = finance_overrides[name]
                source_algo = "finance_ui"
            else:
                perf = lookup_vehicle_performance(source, name)
                source_algo = "sumif_subsheet"
            rows.append(
                {
                    "店别": person["店别"],
                    "职务": person["职务"],
                    "姓名": name,
                    HUB_COLUMN: perf,
                    "_source": source_algo,
                }
            )

        metrics = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=[*SUMMARY_KEY_COLUMNS, HUB_COLUMN]
        )
        if "_source" in metrics.columns:
            metrics = metrics.drop(columns=["_source"])
        logger.info(
            "%s: matched=%s rules_sheet=%s",
            self.name,
            len(metrics),
            family.get("rules_sheet", "新媒体"),
        )
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=metrics,
            metadata={
                "family_id": FAMILY_ID,
                "rules_sheet": family.get("rules_sheet"),
                "algorithm": "calculator_with_sumif_fallback",
                "finance_overrides": len(finance_overrides),
                "source_sheet": "新媒体",
                "rows": len(metrics),
            },
        )
