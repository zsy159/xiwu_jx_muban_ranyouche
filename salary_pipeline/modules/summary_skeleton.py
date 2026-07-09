"""Summary row skeleton (keys only) — 店别/职务/姓名 from upload or reference layout."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import (
    read_personnel_skeleton_keys,
    read_summary_skeleton_keys,
    resolve_summary_skeleton_source,
)
from salary_pipeline.modules.base import PERSONNEL_SHEET
from salary_pipeline.modules.base import SUMMARY_KEY_COLUMNS, BaseCommissionModule, ModuleResult

logger = logging.getLogger(__name__)


class SummarySkeletonModule(BaseCommissionModule):
    """
    Provide 店别/职务/姓名 row keys for 提成汇总 aggregation.

    Priority: sales 提成汇总 → optional 人员信息 upload → golden/canonical
    提成汇总 (structure only, not metric bootstrap).
    """

    name = "summary_skeleton"
    roles = ["*"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        config = context["month_config"]
        parity = config.get("parity", {})
        sheet = config["outputs"]["commission_summary_sheet"]
        data_start_row = int(parity.get("data_start_row", 3))
        workbook_path, source, read_sheet = resolve_summary_skeleton_source(
            config, sheet_name=sheet
        )
        if workbook_path is None:
            logger.warning(
                "summary_skeleton: no workbook with sheet %s or %s; empty skeleton",
                sheet,
                PERSONNEL_SHEET,
            )
            metrics = pd.DataFrame(columns=[*SUMMARY_KEY_COLUMNS, "_excel_row"])
            return ModuleResult(
                module_name=self.name,
                roles=self.roles,
                metrics=metrics,
                metadata={"bootstrap": "empty", "rows": 0},
            )

        if source not in ("sales", "golden_workbook"):
            logger.info(
                "summary_skeleton: using %s workbook for row keys (sheet %s)",
                source,
                read_sheet,
            )
        if read_sheet == PERSONNEL_SHEET:
            skeleton = read_personnel_skeleton_keys(
                workbook_path,
                data_start_row=data_start_row,
            )
        else:
            skeleton = read_summary_skeleton_keys(
                workbook_path,
                read_sheet,
                header_row=int(parity.get("header_row", 2)),
                data_start_row=data_start_row,
            )
        metrics = skeleton.copy()
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=metrics,
            metadata={"bootstrap": source or "golden_keys", "rows": len(metrics)},
        )
