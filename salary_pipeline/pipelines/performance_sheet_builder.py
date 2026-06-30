"""Build partial 绩效整理表 from detail inputs (Phase B)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from salary_pipeline.calculators.performance_sheet import (
    compute_closure_columns,
    compute_decoration_columns,
    compute_insurance_columns,
    compute_mortgage_columns,
    compute_terminal_columns,
    compute_vehicle_cost_columns,
    compute_warranty_columns,
)
from salary_pipeline.calculators.performance_sheet.from_closure import (
    CLOSURE_PERF_COLUMNS,
)
from salary_pipeline.calculators.performance_sheet.order_skeleton import (
    build_performance_order_skeleton,
)
from salary_pipeline.calculators.performance_sheet.from_decoration import (
    DECORATION_PERF_MAP,
)
from salary_pipeline.calculators.performance_sheet.from_insurance import (
    INSURANCE_PERF_MAP,
)
from salary_pipeline.calculators.performance_sheet.from_mortgage import (
    MORTGAGE_PERF_MAP,
)
from salary_pipeline.calculators.performance_sheet.from_terminal import (
    TERMINAL_PERF_COLUMNS,
)
from salary_pipeline.calculators.performance_sheet.from_vehicle_cost import (
    VEHICLE_COST_INDEX_MAP,
)
from salary_pipeline.calculators.performance_sheet.from_overdue_stock import (
    OVERDUE_STOCK_COLUMNS,
    compute_overdue_stock_columns,
)
from salary_pipeline.calculators.performance_sheet.from_warranty import (
    WARRANTY_PERF_COLUMNS,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, load_month_config
from salary_pipeline.data_ingestion.performance_sheet_golden import (
    load_performance_order_skeleton,
)
from salary_pipeline.ops.basic import sumif_by_key
from salary_pipeline.paths import CONFIG_DIR, resolve_project_path

logger = logging.getLogger(__name__)

SLICE_1_COLUMNS = ("AB", "AJ", "AK")
SLICE_2_EXTRA_COLUMNS = ("AO", "AP")
SLICE_2_COLUMNS = SLICE_1_COLUMNS + SLICE_2_EXTRA_COLUMNS
SLICE_3_EXTRA_COLUMNS = ("AL", "BH", "AW", "AX", "AY", "AZ", "BA", "BB")
SLICE_3_COLUMNS = SLICE_2_COLUMNS + SLICE_3_EXTRA_COLUMNS
SLICE_4_COLUMNS = SLICE_3_COLUMNS
SLICE_5_COLUMNS = SLICE_4_COLUMNS + CLOSURE_PERF_COLUMNS
SLICE_5_EXTRA_COLUMNS = CLOSURE_PERF_COLUMNS
SLICE_6_EXTRA_COLUMNS = ("AT", "BC")
SLICE_6_COLUMNS = SLICE_5_COLUMNS + SLICE_6_EXTRA_COLUMNS
SLICE_7_EXTRA_COLUMNS = OVERDUE_STOCK_COLUMNS
SLICE_7_COLUMNS = SLICE_6_COLUMNS + SLICE_7_EXTRA_COLUMNS
ORDER_KEY_COLUMNS = ("O", "P", "K", "G")
IMPLEMENTED_COLUMNS = ORDER_KEY_COLUMNS + SLICE_7_COLUMNS
# Hub W–AI 值列已全部内化；金标准 xlsx 仅用于对账
GOLDEN_OVERLAY_COLUMNS: tuple[str, ...] = ()


def load_performance_sheet_config(config_dir: Path | None = None) -> dict[str, Any]:
    path = (config_dir or CONFIG_DIR) / "performance_sheet_columns.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class PerformanceSheetBuilder:
    """
    Recompute 绩效整理表 columns from registered detail sheets.

    Slice 1: insurance (AB/AJ) + mortgage (AK).
    Slice 2: + insurance AO/AP (BU/BV).
    Slice 3: + mortgage AL, decoration BH, vehicle cost AW–BB.
    Slice 4: order keys O/P/K/G from 系统销售毛利 (+ 终端明细表 registered).
    Slice 5: + closure columns AG/AH/AI/AM/AN/AS/AQ/AR for Hub W–AI.
    Slice 6: + AT (延保提成) / BC (终端返利).
    Slice 7: + E (库存天数) / AU (超期追加) → Hub「超期」列.
    """

    def __init__(
        self,
        loader: WorkbookLoader,
        config_dir: Path | None = None,
        *,
        billing_month: str | None = None,
    ) -> None:
        self.loader = loader
        self.config = load_performance_sheet_config(config_dir)
        self.billing_month = billing_month or self.config.get("order_skeleton", {}).get(
            "billing_month"
        )
        self._topology_path = self._resolve_topology_path()

    def _resolve_topology_path(self) -> Path | None:
        try:
            month_cfg = load_month_config()
            rel = (month_cfg.get("topology") or {}).get("sales")
            if rel:
                return resolve_project_path(rel)
        except (KeyError, TypeError, ValueError):
            pass
        return None

    def build_slice_7(self) -> pd.DataFrame:
        return self._build(
            SLICE_7_COLUMNS,
            skeleton_source="computed",
        )

    def build(self) -> pd.DataFrame:
        """Production entry: computed order skeleton + Slices 1–7 value columns."""
        return self.build_slice_7()

    def build_slice_1(self) -> pd.DataFrame:
        return self._build(SLICE_1_COLUMNS)

    def build_slice_2(self) -> pd.DataFrame:
        return self._build(SLICE_2_COLUMNS)

    def build_slice_3(self) -> pd.DataFrame:
        return self._build(
            SLICE_3_COLUMNS,
            skeleton_keys=("O", "P", "K", "G"),
        )

    def build_slice_4(self) -> pd.DataFrame:
        return self._build(
            SLICE_4_COLUMNS,
            skeleton_source="computed",
        )

    def build_slice_5(self) -> pd.DataFrame:
        return self._build(
            SLICE_5_COLUMNS,
            skeleton_source="computed",
        )

    def build_slice_6(self) -> pd.DataFrame:
        return self._build(
            SLICE_6_COLUMNS,
            skeleton_source="computed",
        )

    def load_order_skeleton(
        self,
        *,
        source: str = "computed",
        skeleton_keys: tuple[str, ...] = ("O", "P", "K", "G"),
    ) -> pd.DataFrame:
        if source == "golden":
            return load_performance_order_skeleton(
                self.loader, key_cols=skeleton_keys
            )
        skeleton_cfg = self.config.get("order_skeleton")
        if not skeleton_cfg:
            raise ValueError("order_skeleton config missing for computed skeleton")
        return build_performance_order_skeleton(
            self.loader,
            skeleton_cfg,
            billing_month=self.billing_month,
        )

    def _build(
        self,
        target_columns: tuple[str, ...],
        *,
        skeleton_keys: tuple[str, ...] = ("O", "P", "K"),
        skeleton_source: str = "golden",
    ) -> pd.DataFrame:
        if skeleton_source == "computed":
            skeleton = self.load_order_skeleton(source="computed")
        else:
            skeleton = load_performance_order_skeleton(
                self.loader, key_cols=skeleton_keys
            )
        insurance_cols = tuple(
            c for c in target_columns if c in INSURANCE_PERF_MAP
        )
        mortgage_cols = tuple(
            c for c in target_columns if c in MORTGAGE_PERF_MAP
        )
        decoration_cols = tuple(
            c for c in target_columns if c in DECORATION_PERF_MAP
        )
        vehicle_cost_cols = tuple(
            c for c in target_columns if c in VEHICLE_COST_INDEX_MAP
        )
        closure_cols = tuple(c for c in target_columns if c in CLOSURE_PERF_COLUMNS)
        overdue_stock_cols = tuple(
            c for c in target_columns if c in OVERDUE_STOCK_COLUMNS
        )
        warranty_cols = tuple(c for c in target_columns if c in WARRANTY_PERF_COLUMNS)
        terminal_cols = tuple(c for c in target_columns if c in TERMINAL_PERF_COLUMNS)
        insurance = compute_insurance_columns(
            skeleton, self.loader, target_cols=insurance_cols
        )
        mortgage = compute_mortgage_columns(
            skeleton, self.loader, target_cols=mortgage_cols
        )
        decoration = compute_decoration_columns(
            skeleton, self.loader, target_cols=decoration_cols
        )
        vehicle_cost = compute_vehicle_cost_columns(
            skeleton, self.loader, target_cols=vehicle_cost_cols
        )

        partial = skeleton.copy()
        for part in (insurance, mortgage, decoration, vehicle_cost):
            for col in target_columns:
                if col in part.columns:
                    partial[col] = part[col].values

        closure = compute_closure_columns(
            partial,
            self.loader,
            target_cols=closure_cols,
        )
        warranty = compute_warranty_columns(
            skeleton,
            self.loader,
            target_cols=warranty_cols,
        )
        terminal = compute_terminal_columns(
            skeleton,
            self.loader,
            target_cols=terminal_cols,
        )
        overdue_stock = compute_overdue_stock_columns(
            partial,
            self.loader,
            target_cols=overdue_stock_cols,
            topology_path=self._topology_path,
        )
        out = partial.copy()
        for col in closure_cols:
            if col in closure.columns:
                out[col] = closure[col].values
        for part in (warranty, terminal, overdue_stock):
            for col in target_columns:
                if col in part.columns:
                    out[col] = part[col].values

        out = self._apply_advisor_column_adjustments(out)

        logger.info(
            "PerformanceSheetBuilder: rows=%s cols=%s",
            len(out),
            [c for c in target_columns if c in out.columns],
        )
        return out

    def _apply_advisor_column_adjustments(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Append advisor-level manual tail rows (golden 无 VIN 手工尾项)."""
        adjustments = (self.config.get("order_skeleton") or {}).get(
            "advisor_column_adjustments"
        ) or []
        if not adjustments or frame.empty:
            return frame

        from salary_pipeline.data_ingestion.data_loader import normalize_name

        extra_rows: list[dict[str, Any]] = []
        for adj in adjustments:
            advisor = normalize_name(str(adj.get("advisor", "")))
            col = str(adj.get("column", "")).strip()
            amount = adj.get("amount")
            if not advisor or not col or amount is None:
                continue
            row: dict[str, Any] = {"O": pd.NA, "P": advisor, "K": pd.NA}
            row[col] = float(amount)
            extra_rows.append(row)

        if not extra_rows:
            return frame

        out = pd.concat([frame, pd.DataFrame(extra_rows)], ignore_index=True)
        start = int(self.config.get("data_start_row", 3))
        out["_excel_row"] = range(start, start + len(out))
        return out

    def aggregate_by_advisor(
        self,
        frame: pd.DataFrame,
        value_col: str,
        *,
        advisor_col: str = "P",
    ) -> pd.Series:
        """Hub semantics: SUMIF(绩效整理表!P:P, name, value_col)."""
        if frame.empty or advisor_col not in frame.columns:
            return pd.Series(dtype=float)
        grouped = (
            frame.groupby(advisor_col, dropna=True)[value_col]
            .sum(min_count=1)
            .fillna(0.0)
        )
        return grouped

    def lookup_golden_column(
        self,
        value_col: str,
    ) -> pd.DataFrame:
        """Read golden 绩效整理表 column for parity (development only)."""
        skeleton = load_performance_order_skeleton(self.loader, key_cols=("O", "P"))
        golden = self.loader.read_sheet_columns(
            self.config["sheet"],
            {value_col: value_col},
            label=f"golden {value_col}",
        )
        from salary_pipeline.data_ingestion.performance_sheet_golden import DATA_START_ROW

        values = golden.iloc[DATA_START_ROW - 1 :]
        values = values.reset_index(drop=True)
        values = values.iloc[: len(skeleton)].copy()
        values[value_col] = pd.to_numeric(values[value_col], errors="coerce")
        out = skeleton[["O", "P"]].copy()
        out[value_col] = values[value_col].values
        return out

    def parity_report(
        self,
        columns: tuple[str, ...],
        *,
        tolerance: float = 1e-4,
    ) -> dict[str, Any]:
        built = self._build(columns)
        report: dict[str, Any] = {"columns": {}, "rows": len(built)}
        for col in columns:
            golden = self.lookup_golden_column(col)
            merged = built[["O", col]].merge(
                golden[["O", col]], on="O", suffixes=("_built", "_golden")
            )
            diff = (
                merged[f"{col}_built"].fillna(0) - merged[f"{col}_golden"].fillna(0)
            ).abs()
            mismatches = int((diff > tolerance).sum())
            report["columns"][col] = {
                "mismatches": mismatches,
                "total": len(built),
                "match_rate": 1.0 - mismatches / max(len(built), 1),
            }
        return report

    def parity_report_slice_1(self, *, tolerance: float = 1e-4) -> dict[str, Any]:
        return self.parity_report(SLICE_1_COLUMNS, tolerance=tolerance)

    def parity_report_slice_2(self, *, tolerance: float = 1e-4) -> dict[str, Any]:
        return self.parity_report(SLICE_2_COLUMNS, tolerance=tolerance)

    def parity_report_slice_3(self, *, tolerance: float = 1e-4) -> dict[str, Any]:
        built = self.build_slice_3()
        report: dict[str, Any] = {"columns": {}, "rows": len(built)}
        for col in SLICE_3_EXTRA_COLUMNS:
            golden = self.lookup_golden_column(col)
            merged = built[["O", col]].merge(
                golden[["O", col]], on="O", suffixes=("_built", "_golden")
            )
            diff = (
                merged[f"{col}_built"].fillna(0) - merged[f"{col}_golden"].fillna(0)
            ).abs()
            mismatches = int((diff > tolerance).sum())
            report["columns"][col] = {
                "mismatches": mismatches,
                "total": len(built),
                "match_rate": 1.0 - mismatches / max(len(built), 1),
            }
        return report


def sumif_advisor_performance(
    perf_frame: pd.DataFrame,
    advisor_name: str,
    value_col: str,
) -> float:
    """Same as Hub ``SUMIF(绩效整理表!P:P, name, col:col)``."""
    return float(sumif_by_key(perf_frame, "P", value_col, advisor_name))
