"""Post-export payout formatting: parity highlights and manual-fill markers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from salary_pipeline.calculators.sales_advisor.topology_specs import (
    collect_topology_static_fill_cells,
)
from salary_pipeline.data_ingestion.data_loader import resolve_computed_payout_read_rows
from salary_pipeline.paths import resolve_project_path
from salary_pipeline.pipelines.commission_summary_formatting import (
    HighlightStats,
    parity_highlight_mode,
    resolve_highlight_golden_path,
)
from salary_pipeline.pipelines.xw_payout_formula_engine import PAYOUT_CHANNEL_COLUMN_MAPS
from salary_pipeline.utils.excel_format import (
    add_commission_summary_color_legend,
    highlight_commission_summary_deferred_cells,
    highlight_commission_summary_mismatches,
)
from salary_pipeline.validation.parity import CommissionSummaryParity

logger = logging.getLogger(__name__)

PAYOUT_PARITY_KEYS = {
    "xw": "payout_parity",
    "direct_store": "direct_store_parity",
    "cs": "cs_parity",
}

from salary_pipeline.pipelines.payout_column_sources import (
    PAYOUT_DATA_START_ROW,
    PAYOUT_HEADER_ROW,
    PAYOUT_SOURCE_ROW,
)

PAYOUT_LEGEND_INSERT_ROW = PAYOUT_SOURCE_ROW
PAYOUT_COMPUTED_HEADER_ROW = PAYOUT_HEADER_ROW
PAYOUT_COMPUTED_DATA_START_ROW = PAYOUT_DATA_START_ROW

# Golden payout sheet: header row 2, data row 3+.
PAYOUT_GOLDEN_HEADER_ROW = 2
PAYOUT_GOLDEN_DATA_START_ROW = 3


def _parity_config(month_config: dict[str, Any], channel: str) -> dict[str, Any]:
    key = PAYOUT_PARITY_KEYS.get(channel, "payout_parity")
    return month_config.get(key, month_config.get("payout_parity", {}))


def _anchor_sheet(month_config: dict[str, Any], channel: str) -> str:
    payout_cfg = month_config.get("payout", {}).get(channel, {})
    defaults = {
        "xw": "XW提成-发",
        "direct_store": "直营店提成-发",
        "cs": "CS提成-发",
    }
    return payout_cfg.get("anchor_sheet") or defaults.get(channel, "XW提成-发")


def resolve_payout_compare_columns(
    parity_cfg: dict[str, Any],
    column_map: dict[str, str],
) -> list[str]:
    """Core gate columns plus extended payout metrics for parity/highlighting.

    ``columns`` lists the primary acceptance metrics. By default, every other
    channel metric from ``column_map`` is also compared so component diffs
    (e.g. 权限结余绩效) surface as amber cells, not only rollup totals.
    """
    core = list(parity_cfg.get("columns") or [])
    explicit = parity_cfg.get("extended_columns")
    if explicit is not None:
        extra = list(explicit)
    elif parity_cfg.get("compare_all_metrics", True):
        extra = [name for name in column_map.values() if name not in core]
    else:
        extra = []
    return list(dict.fromkeys(core + extra))


def apply_payout_highlighting(
    month_config: dict[str, Any],
    computed_path: Path,
    channel: str,
    *,
    golden_path: Path | None = None,
) -> HighlightStats:
    """
    Apply color legend, parity mismatch fills, and manual-fill markers on payout xlsx.

    Compares computed output vs golden (read-only); never writes golden values into output.
    """
    parity_cfg = _parity_config(month_config, channel)
    if parity_cfg.get("auto_highlight", True) is False:
        return HighlightStats()

    column_map = PAYOUT_CHANNEL_COLUMN_MAPS[channel]
    compare_columns = resolve_payout_compare_columns(parity_cfg, column_map)
    if not compare_columns:
        return HighlightStats()

    golden = golden_path
    if golden is None:
        payout_cfg = month_config.get("payout", {}).get(channel, {})
        raw = payout_cfg.get("golden_workbook")
        if raw:
            candidate = resolve_project_path(raw)
            if candidate.exists():
                golden = candidate
    if golden is None:
        golden = resolve_highlight_golden_path(month_config)
    if golden is None:
        logger.info("Skipping payout highlighting (%s): no golden workbook", channel)
        return HighlightStats()

    sheet = _anchor_sheet(month_config, channel)
    golden_data_start = int(
        parity_cfg.get("data_start_row", PAYOUT_GOLDEN_DATA_START_ROW)
    )
    join_keys = parity_cfg.get("join_keys", ["店别", "职务", "姓名"])

    add_commission_summary_color_legend(
        computed_path, sheet, insert_at_row=PAYOUT_LEGEND_INSERT_ROW
    )
    highlight_header_row, highlight_data_start = resolve_computed_payout_read_rows(
        computed_path,
        sheet,
        header_row=PAYOUT_COMPUTED_HEADER_ROW,
        data_start_row=PAYOUT_COMPUTED_DATA_START_ROW,
        legend_insert_row=PAYOUT_LEGEND_INSERT_ROW,
    )

    checker = CommissionSummaryParity(
        join_keys=join_keys,
        numeric_tolerance=float(parity_cfg.get("numeric_tolerance", 1e-4)),
        columns=compare_columns,
        role_column=parity_cfg.get("role_column", "店别"),
        literal_columns=True,
    )
    mismatches = checker.collect_payout_mismatches_from_files(
        computed_path,
        golden,
        sheet,
        column_map,
        data_start_row=golden_data_start,
    )
    mismatch_count = highlight_commission_summary_mismatches(
        computed_path,
        sheet,
        mismatches,
        join_keys,
        compare_columns,
        header_row=highlight_header_row,
        data_start_row=highlight_data_start,
    )

    deferred_count = 0
    hub_parity_cfg = month_config.get("parity", {})
    if parity_highlight_mode(hub_parity_cfg) == "full":
        letter_by_column = {name: letter for letter, name in column_map.items()}
        static_cells = collect_topology_static_fill_cells(
            golden_workbook_path=golden,
            sheet_name=sheet,
            header_row=PAYOUT_GOLDEN_HEADER_ROW,
            data_start_row=golden_data_start,
            data_columns=frozenset(compare_columns),
            letter_by_column=letter_by_column,
        )
        deferred_count = highlight_commission_summary_deferred_cells(
            computed_path,
            sheet,
            {},
            static_cells=static_cells,
            header_row=highlight_header_row,
            data_start_row=highlight_data_start,
        )

    stats = HighlightStats(
        mismatches=mismatch_count,
        deferred=deferred_count,
        annotated=0,
    )
    logger.info(
        "Payout highlighting (%s) -> %s (mismatches=%s, static=%s)",
        channel,
        computed_path,
        stats.mismatches,
        stats.deferred,
    )
    return stats
