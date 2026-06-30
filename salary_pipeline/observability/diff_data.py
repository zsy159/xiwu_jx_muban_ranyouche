from __future__ import annotations

from typing import Any

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import (
    read_computed_aftersales_excel,
    read_computed_payout_excel,
    read_computed_summary_excel,
    read_golden_summary_sheet,
    read_payout_metric_frame,
)
from salary_pipeline.observability.loaders import load_month_config_for, load_observability_config
from salary_pipeline.paths import resolve_project_path
from salary_pipeline.pipelines.aftersales_formula_engine import (
    AIRPORT_CONFIG,
    WUHOU_CONFIG,
)
from salary_pipeline.pipelines.hub_formula_engine import HUB_COLUMN_MAP
from salary_pipeline.pipelines.xw_payout_formula_engine import XW_COLUMN_MAP
from salary_pipeline.data_ingestion.data_loader import read_aftersales_metric_frame


def get_anchor_config(anchor_id: str) -> dict[str, Any]:
    return load_observability_config()["anchors"][anchor_id]


def acceptance_columns(month_id: str, anchor_id: str) -> list[str]:
    cfg = load_month_config_for(month_id)
    anchor = get_anchor_config(anchor_id)
    section = cfg.get(anchor["parity_section"], {})
    cols = section.get("columns")
    if cols:
        return list(cols)
    if anchor_id == "hub":
        return list(HUB_COLUMN_MAP.values())
    if anchor_id == "xw_payout":
        return list(XW_COLUMN_MAP.values())
    return []


def performance_columns(anchor_id: str) -> list[str]:
    if anchor_id != "hub":
        return []
    obs = load_observability_config()
    return list(obs.get("hub_performance_columns", []))


def load_comparison_frames(
    month_id: str,
    anchor_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    cfg = load_month_config_for(month_id)
    anchor = get_anchor_config(anchor_id)
    output_key = anchor["output_key"]
    computed_path = resolve_project_path(cfg["outputs"][output_key])
    golden_wb = resolve_project_path(cfg["workbooks"][anchor["golden_workbook_key"]])

    join_keys = cfg.get(anchor["parity_section"], {}).get(
        "join_keys", ["店别", "职务", "姓名"]
    )

    if anchor_id == "hub":
        sheet = cfg["outputs"]["commission_summary_sheet"]
        golden = read_golden_summary_sheet(
            golden_wb,
            sheet,
            header_row=int(cfg["parity"]["header_row"]),
            data_start_row=int(cfg["parity"]["data_start_row"]),
        )
        computed = read_computed_summary_excel(computed_path, sheet)
    elif anchor_id == "xw_payout":
        sheet = anchor.get("golden_sheet", "XW提成-发")
        golden = read_payout_metric_frame(
            golden_wb,
            sheet,
            XW_COLUMN_MAP,
            data_start_row=int(cfg["payout"]["data_start_row"]),
        )
        computed = read_computed_payout_excel(computed_path, sheet)
    elif anchor_id.startswith("aftersales_"):
        store = anchor["store"]
        store_cfg = cfg["aftersales"]["stores"][store]
        sheet = store_cfg["anchor_sheet"]
        engine_cfg = WUHOU_CONFIG if store == "wuhou" else AIRPORT_CONFIG
        data_start = int(cfg["aftersales_parity"].get("data_start_row", 5))
        golden = read_aftersales_metric_frame(
            resolve_project_path(store_cfg.get("golden_workbook") or cfg["workbooks"]["aftersales"]),
            sheet,
            engine_cfg.column_map,
            data_start_row=data_start,
        )
        computed = read_computed_aftersales_excel(
            computed_path, sheet, engine_cfg.column_map
        )
        join_keys = cfg["aftersales_parity"].get("join_keys", ["店别", "姓名"])
    else:
        raise KeyError(anchor_id)

    return golden, computed, join_keys


def _dedupe_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop duplicate column labels (merged Excel headers)."""
    if not frame.columns.duplicated().any():
        return frame
    return frame.loc[:, ~frame.columns.duplicated()].copy()


def build_diff_table(
    golden: pd.DataFrame,
    computed: pd.DataFrame,
    join_keys: list[str],
    columns: list[str],
    *,
    tolerance: float = 1e-4,
) -> pd.DataFrame:
    golden = _dedupe_columns(golden)
    computed = _dedupe_columns(computed)
    keys = [k for k in join_keys if k in golden.columns and k in computed.columns]
    if not keys:
        return pd.DataFrame()

    cols = [c for c in columns if c in golden.columns or c in computed.columns]
    g = golden[keys + [c for c in cols if c in golden.columns]].copy()
    c = computed[keys + [c for c in cols if c in computed.columns]].copy()
    merged = g.merge(c, on=keys, how="outer", suffixes=("_金标准", "_系统"))

    rows: list[dict[str, Any]] = []
    for col in cols:
        gc = f"{col}_金标准" if f"{col}_金标准" in merged.columns else col
        cc = f"{col}_系统" if f"{col}_系统" in merged.columns else col
        if gc not in merged.columns and col in merged.columns:
            gc = col
        if cc not in merged.columns:
            continue
        for _, row in merged.iterrows():
            gv, cv = row.get(gc), row.get(cc)
            if pd.isna(gv) and pd.isna(cv):
                continue
            delta = None
            mismatch = False
            if pd.isna(gv) or pd.isna(cv):
                mismatch = True
            else:
                try:
                    delta = float(cv) - float(gv)
                    mismatch = abs(delta) > tolerance
                except (TypeError, ValueError):
                    mismatch = str(gv) != str(cv)
            if mismatch:
                rows.append(
                    {
                        **{k: row[k] for k in keys},
                        "列": col,
                        "金标准": gv,
                        "系统": cv,
                        "差异": delta,
                    }
                )
    return pd.DataFrame(rows)
