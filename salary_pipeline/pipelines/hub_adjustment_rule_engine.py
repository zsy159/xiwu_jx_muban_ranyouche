"""声明式 Hub AM–AP 调整列规则引擎（全员 SUMIF，与职务无关）。"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from salary_pipeline.data_ingestion.composite_summary_sheet import (
    COMPOSITE_SUMMARY_SHEET,
    load_composite_summary_sumif_frame,
    load_overdue_campaign_hub_frame,
)
from salary_pipeline.data_ingestion.closure_input_sheets import OVERDUE_CAMPAIGN_SHEET
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name
from salary_pipeline.ops.basic import sumif_by_key
from salary_pipeline.paths import CONFIG_DIR

logger = logging.getLogger(__name__)

HUB_ADJUSTMENT_RULES_PATH = CONFIG_DIR / "hub_adjustment_rules.yaml"
DEFAULT_ACTIVITY_COLUMN_NAME = "04月活动"


@lru_cache(maxsize=1)
def load_hub_adjustment_rules(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or HUB_ADJUSTMENT_RULES_PATH
    with cfg_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def resolve_activity_column_name(month_config: dict[str, Any] | None) -> str:
    hub_cfg = (month_config or {}).get("hub") or {}
    name = hub_cfg.get("activity_column_name")
    if name:
        return str(name).strip()
    return DEFAULT_ACTIVITY_COLUMN_NAME


def _empty_perf_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["P", "AU"])


class HubAdjustmentRuleEngine:
    """按 hub_adjustment_rules.yaml 声明式计算提成汇总调整列。"""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        month_config: dict[str, Any] | None = None,
    ) -> None:
        self.config = config or load_hub_adjustment_rules()
        self.month_config = month_config
        self.columns: list[dict[str, Any]] = self.config.get("columns", [])

    def apply(
        self,
        summary: pd.DataFrame,
        *,
        computed_perf_frame: pd.DataFrame | None,
        loader: WorkbookLoader | None,
    ) -> pd.DataFrame:
        if summary.empty:
            return summary

        out = summary.copy()
        names = out["姓名"].map(normalize_name)
        perf_frame = (
            computed_perf_frame
            if computed_perf_frame is not None and not computed_perf_frame.empty
            else _empty_perf_frame()
        )
        composite_frame = self._load_composite_frame(loader)
        overdue_frame = self._load_overdue_frame(loader)

        for spec in self.columns:
            hub_col = self._resolve_hub_column(spec)
            if spec.get("op") != "sumif":
                raise ValueError(f"Unknown hub_adjustment_rules op: {spec.get('op')!r}")
            frame = self._frame_for_sheet(
                spec["source_sheet"],
                composite_frame,
                overdue_frame,
                perf_frame,
                header_row=spec.get("header_row"),
            )
            out[hub_col] = self._op_sumif(spec, names, frame)

        logger.info(
            "Hub adjustment rule engine: computed %s columns for %s rows",
            len(self.columns),
            len(out),
        )
        return out

    def _resolve_hub_column(self, spec: dict[str, Any]) -> str:
        if "hub_column" in spec:
            return str(spec["hub_column"])
        month_key = spec.get("hub_column_from_month")
        if month_key == "hub.activity_column_name":
            return resolve_activity_column_name(self.month_config)
        raise ValueError(f"hub_adjustment_rules: missing hub_column in spec {spec!r}")

    def _load_composite_frame(self, loader: WorkbookLoader | None) -> pd.DataFrame:
        if loader is None:
            return pd.DataFrame(columns=["B", "J", "L"])
        frame = load_composite_summary_sumif_frame(loader)
        return frame if frame is not None else pd.DataFrame(columns=["B", "J", "L"])

    def _load_overdue_frame(self, loader: WorkbookLoader | None) -> pd.DataFrame:
        if loader is None:
            return pd.DataFrame(columns=["Q", "X"])
        frame = load_overdue_campaign_hub_frame(loader)
        return frame if frame is not None else pd.DataFrame(columns=["Q", "X"])

    def _frame_for_sheet(
        self,
        sheet: str,
        composite_frame: pd.DataFrame,
        overdue_frame: pd.DataFrame,
        perf_frame: pd.DataFrame,
        *,
        header_row: int | None,
    ) -> pd.DataFrame:
        if sheet == COMPOSITE_SUMMARY_SHEET:
            if header_row is not None and header_row != 4:
                logger.warning(
                    "hub_adjustment: composite header_row=%s ignored (loader pre-sliced)",
                    header_row,
                )
            return composite_frame
        if sheet == OVERDUE_CAMPAIGN_SHEET:
            if header_row is not None and header_row != 3:
                logger.warning(
                    "hub_adjustment: overdue header_row=%s ignored (loader pre-sliced)",
                    header_row,
                )
            return overdue_frame
        if sheet == "绩效整理表":
            return perf_frame
        raise ValueError(f"hub_adjustment_rules: unsupported source_sheet {sheet!r}")

    def _op_sumif(
        self,
        spec: dict[str, Any],
        names: pd.Series,
        frame: pd.DataFrame,
    ) -> pd.Series:
        key_col, value_col = spec["key_col"], spec["value_col"]
        if key_col not in frame.columns or value_col not in frame.columns:
            return pd.Series(0.0, index=names.index)
        result = sumif_by_key(frame, key_col, value_col, names)
        return result if isinstance(result, pd.Series) else pd.Series(result, index=names.index)
