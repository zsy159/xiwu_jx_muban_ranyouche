"""Phase B: 绩效整理表 formula layer — builder output for HubFormulaEngine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import build_workbook_loader
from salary_pipeline.pipelines.performance_sheet_builder import (
    IMPLEMENTED_COLUMNS,
    PerformanceSheetBuilder,
)

logger = logging.getLogger(__name__)


@dataclass
class PerformanceSheetResult:
    """Builder output placed in pipeline context (not a commission ModuleResult)."""

    module_name: str = "performance_sheet"
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    metadata: dict[str, Any] = field(default_factory=dict)


class PerformanceSheetModule:
    """
    Build order-level 绩效整理表 from detail inputs (Phase B).

    Produces ``computed_perf_frame`` for ``HubFormulaEngine`` overlay (T1).
    Runs in ``SalesPipeline`` before hub formula evaluation.
    """

    name = "performance_sheet"

    def run(self, context: dict[str, Any]) -> PerformanceSheetResult:
        month_config = context.get("month_config", {})
        perf_cfg = month_config.get("performance_sheet", {})
        if not perf_cfg.get("use_computed", True):
            logger.info("%s: use_computed=false, skip builder", self.name)
            return PerformanceSheetResult(
                metadata={"status": "skipped", "use_computed": False},
            )

        loader = build_workbook_loader(context)
        billing_month = perf_cfg.get("billing_month") or month_config.get("month")
        builder = PerformanceSheetBuilder(loader, billing_month=billing_month)
        frame = builder.build()

        context["computed_perf_frame"] = frame
        logger.info(
            "%s: rows=%s implemented_cols=%s",
            self.name,
            len(frame),
            [c for c in IMPLEMENTED_COLUMNS if c in frame.columns],
        )
        return PerformanceSheetResult(
            frame=frame,
            metadata={
                "rows": len(frame),
                "columns": list(frame.columns),
                "implemented_columns": [
                    c for c in IMPLEMENTED_COLUMNS if c in frame.columns
                ],
                "source": "computed",
            },
        )
