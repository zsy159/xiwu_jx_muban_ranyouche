"""Post-export 提成汇总 formatting: parity highlights and formula annotations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from salary_pipeline.calculators.sales_advisor.parity_annotations import (
    annotations_for_workbook,
    enrich_cell_mismatches,
    parity_values_for_annotations,
)
from salary_pipeline.calculators.sales_advisor.registry import (
    build_reconcile_deferred_cells,
    wa_parity_deferred_reasons,
)
from salary_pipeline.calculators.sales_advisor.topology_specs import (
    collect_topology_static_fill_cells,
)
from salary_pipeline.paths import resolve_project_path
from salary_pipeline.utils.excel_format import (
    add_commission_summary_annotations,
    add_commission_summary_color_legend,
    highlight_commission_summary_deferred_cells,
    highlight_commission_summary_mismatches,
)
from salary_pipeline.validation.parity import CommissionSummaryParity

logger = logging.getLogger(__name__)


@dataclass
class HighlightStats:
    mismatches: int = 0
    deferred: int = 0
    annotated: int = 0


def resolve_highlight_golden_path(month_config: dict[str, Any]) -> Path | None:
    """Golden workbook used for reconcile highlighting (not upload skeleton)."""
    parity = month_config.get("parity", {})
    for key in ("reference_golden_workbook", "highlight_golden_workbook", "golden_workbook"):
        raw = parity.get(key)
        if not raw:
            continue
        path = resolve_project_path(raw)
        if path.exists():
            return path
    return None


def apply_commission_summary_highlighting(
    month_config: dict[str, Any],
    computed_path: Path,
    *,
    golden_path: Path | None = None,
) -> HighlightStats:
    """
    Apply color legend, parity mismatch fills, deferred/static fills, and annotations.

    Intended to run after ``CommissionSummaryBuilder.export_excel`` on both
    ``compute`` and upload trial paths so generated workbooks match reconcile output.
    """
    parity_cfg = month_config.get("parity", {})
    if parity_cfg.get("auto_highlight", True) is False:
        return HighlightStats()

    golden = golden_path or resolve_highlight_golden_path(month_config)
    if golden is None:
        logger.info("Skipping commission summary highlighting: no golden workbook")
        return HighlightStats()

    sheet = month_config["outputs"].get("commission_summary_sheet", "提成汇总")
    header_row = int(parity_cfg.get("header_row", 2))
    data_start_row = int(parity_cfg.get("data_start_row", 3))
    compare_columns = list(parity_cfg.get("columns") or []) + list(
        parity_cfg.get("performance_columns") or []
    )
    if not compare_columns:
        return HighlightStats()

    perf_raw = month_config["outputs"].get("performance_sheet_file")
    perf_path = (
        resolve_project_path(perf_raw)
        if perf_raw
        else computed_path.parent / "绩效整理表-系统生成.xlsx"
    )
    deferred_for_highlight = build_reconcile_deferred_cells(
        golden,
        perf_path=perf_path,
        header_row=header_row,
        data_start_row=data_start_row,
    )

    add_commission_summary_color_legend(computed_path, sheet, insert_at_row=2)
    highlight_header_row = header_row + 1
    highlight_data_start = data_start_row + 1
    highlight_checker = CommissionSummaryParity(
        join_keys=parity_cfg.get("join_keys", ["店别", "职务", "姓名"]),
        numeric_tolerance=float(parity_cfg.get("numeric_tolerance", 1e-6)),
        columns=compare_columns,
        deferred_cells=deferred_for_highlight,
    )
    mismatches = highlight_checker.collect_mismatches_from_files(
        computed_path,
        golden,
        sheet,
        header_row=highlight_header_row,
        data_start_row=highlight_data_start,
        golden_header_row=header_row,
        golden_data_start_row=data_start_row,
    )
    mismatches = enrich_cell_mismatches(
        mismatches,
        golden_workbook=golden,
        golden_data_start_row=data_start_row,
    )
    mismatch_count = highlight_commission_summary_mismatches(
        computed_path,
        sheet,
        mismatches,
        parity_cfg.get("join_keys", ["店别", "职务", "姓名"]),
        compare_columns,
        header_row=highlight_header_row,
        data_start_row=highlight_data_start,
    )
    static_cells = collect_topology_static_fill_cells(
        golden_workbook_path=golden,
        header_row=header_row,
        data_start_row=data_start_row,
    )
    deferred_count = highlight_commission_summary_deferred_cells(
        computed_path,
        sheet,
        deferred_for_highlight,
        static_cells=static_cells,
        deferred_reasons=wa_parity_deferred_reasons(),
        header_row=highlight_header_row,
        data_start_row=highlight_data_start,
    )

    base_annotations = annotations_for_workbook(
        deferred_cells=deferred_for_highlight,
        golden_workbook=golden,
        golden_data_start_row=data_start_row,
    )
    parity_values = parity_values_for_annotations(
        computed_path,
        golden,
        sheet,
        [ann.key() for ann in base_annotations],
        join_keys=parity_cfg.get("join_keys", ["店别", "职务", "姓名"]),
        header_row=highlight_header_row,
        data_start_row=highlight_data_start,
        golden_header_row=header_row,
        golden_data_start_row=data_start_row,
    )
    annotations = annotations_for_workbook(
        parity_values=parity_values,
        deferred_cells=deferred_for_highlight,
        golden_workbook=golden,
        golden_data_start_row=data_start_row,
    )
    annotated_count = add_commission_summary_annotations(
        computed_path,
        sheet,
        annotations,
        header_row=highlight_header_row,
        data_start_row=highlight_data_start,
    )

    stats = HighlightStats(
        mismatches=mismatch_count,
        deferred=deferred_count,
        annotated=annotated_count,
    )
    logger.info(
        "Commission summary highlighting -> %s (mismatches=%s, deferred=%s, annotated=%s)",
        computed_path,
        stats.mismatches,
        stats.deferred,
        stats.annotated,
    )
    return stats
