"""按揭内勤 — Hub 加装绩效引用 按揭绩效 子表。"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import pandas as pd
import yaml

from salary_pipeline.config.hub_performance_match import row_matches_family
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, build_workbook_loader
from salary_pipeline.modules.base import (
    SUMMARY_KEY_COLUMNS,
    BaseCommissionModule,
    ModuleResult,
)
from salary_pipeline.paths import CONFIG_DIR

logger = logging.getLogger(__name__)

FAMILY_ID = "按揭内勤"
MORTGAGE_PERF_SHEET = "按揭绩效"
_CONFIG_PATH = CONFIG_DIR / "mortgage_clerk_roles.yaml"


@lru_cache(maxsize=1)
def _load_roles() -> dict[str, Any]:
    with _CONFIG_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _read_cell(loader: WorkbookLoader, sheet: str, address: str) -> float:
    val = loader.read_cell_value(sheet, address)
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


class MortgageClerkPerformanceModule(BaseCommissionModule):
    """熊宇 / 李彦林：Y（加装绩效）= 按揭绩效!AF 行引用。"""

    name = "mortgage_clerk_performance"
    roles = ["按揭内勤"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        cfg = _load_roles()
        sheet = str(cfg.get("sheet", MORTGAGE_PERF_SHEET))
        role_by_name = {str(r["name"]): r for r in cfg.get("roles") or []}
        match = {"职务": ["按揭内勤"]}

        skeleton = context.get("summary_skeleton")
        if skeleton is None or skeleton.empty:
            return ModuleResult(
                module_name=self.name,
                roles=self.roles,
                metrics=pd.DataFrame(columns=SUMMARY_KEY_COLUMNS),
                metadata={"status": "no_skeleton"},
            )

        loader = build_workbook_loader(context)
        sheet_available = loader.has_sheet(sheet)
        if not sheet_available:
            logger.warning(
                "%s: sheet %r missing from workbook/uploads; overlay leaves 加装绩效 empty",
                self.name,
                sheet,
            )
        rows: list[dict[str, Any]] = []
        for _, person in skeleton.iterrows():
            if not row_matches_family(person, match):
                continue
            name = str(person["姓名"])
            role = role_by_name.get(name)
            if role is None:
                continue
            hub_col = str(role.get("hub_column", "加装绩效"))
            cell = str(role.get("source_cell", ""))
            amount = (
                _read_cell(loader, sheet, cell)
                if cell and sheet_available
                else 0.0
            )
            rows.append(
                {
                    "店别": person["店别"],
                    "职务": person["职务"],
                    "姓名": name,
                    hub_col: amount,
                }
            )

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
                "source_sheet": sheet,
                "sheet_available": sheet_available,
                "rows": len(metrics),
            },
        )
