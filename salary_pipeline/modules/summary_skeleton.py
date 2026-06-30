"""Summary row skeleton (keys only) — iteration 1 bootstrap from golden layout."""

from __future__ import annotations

from typing import Any

from salary_pipeline.data_ingestion.data_loader import (
    read_summary_skeleton_keys,
)
from salary_pipeline.modules.base import BaseCommissionModule, ModuleResult
from salary_pipeline.paths import resolve_project_path


class SummarySkeletonModule(BaseCommissionModule):
    """
    Provide 店别/职务/姓名 row keys matching the golden workbook layout.

    Iteration 1 only: keys are read from the golden sheet so metric columns
    can be filled before the pipeline produces a full employee universe.
    """

    name = "summary_skeleton"
    roles = ["*"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        config = context["month_config"]
        parity = config.get("parity", {})
        golden_path = resolve_project_path(parity["golden_workbook"])
        sheet = config["outputs"]["commission_summary_sheet"]
        skeleton = read_summary_skeleton_keys(
            golden_path,
            sheet,
            header_row=int(parity.get("header_row", 2)),
            data_start_row=int(parity.get("data_start_row", 3)),
        )
        metrics = skeleton.copy()
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=metrics,
            metadata={"bootstrap": "golden_keys", "rows": len(metrics)},
        )
