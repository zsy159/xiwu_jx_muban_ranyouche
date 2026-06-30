from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from salary_pipeline.data_ingestion.data_loader import (
    filter_comparable_rows,
    read_aftersales_metric_frame,
    read_computed_aftersales_excel,
    read_computed_summary_excel,
    read_golden_summary_sheet,
    summary_frame_from_builder,
)
from salary_pipeline.config.hub_performance_loader import load_hub_performance_config
from salary_pipeline.config.hub_performance_match import (
    combined_gated_row_mask,
    gated_families,
    gated_performance_columns,
)
from salary_pipeline.calculators.sales_advisor.registry import is_parity_deferred_cell
from salary_pipeline.validation.golden_perf_skips import (
    erwang_blank_ah_adjustments_for_paths,
    hub_parity_skip_erwang_blank_ah,
)

logger = logging.getLogger(__name__)


def _cell_float(value: object) -> float | None:
    try:
        num = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if num != num:
        return None
    return num


@dataclass
class ColumnDiff:
    column: str
    mismatch_count: int
    max_abs_diff: float | None
    sample_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class CellMismatch:
    """One computed cell that differs from golden within a parity comparison."""

    join_values: tuple[tuple[str, Any], ...]
    column: str
    golden_value: float | None = None
    computed_value: float | None = None

    def join_dict(self) -> dict[str, Any]:
        return dict(self.join_values)


@dataclass
class RoleParityResult:
    role: str
    row_count: int
    golden_row_count: int
    missing_rows: int
    compared_columns: int
    mismatch_cells: int
    passed: bool
    column_diffs: list[ColumnDiff] = field(default_factory=list)


@dataclass
class ParityReport:
    generated_at: str
    golden_source: str
    computed_source: str
    join_keys: list[str]
    total_rows_golden: int
    total_rows_computed: int
    missing_in_computed: int
    missing_in_golden: int
    overall_passed: bool
    roles: list[RoleParityResult] = field(default_factory=list)
    summary: str = ""
    section: str = "metrics"
    compared_columns: list[str] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HubParityBundle:
    """提成汇总双层对账：F–P 硬验收 + W–AI 绩效跟踪 + parity_gate 算薪族子集。"""

    metrics: ParityReport
    performance: ParityReport | None = None
    gated_performance: ParityReport | None = None

    def to_dict(self) -> dict[str, Any]:
        data = self.metrics.to_dict()
        data["section"] = "metrics"
        sections: dict[str, Any] = {}
        if self.performance is not None:
            sections["performance"] = self.performance.to_dict()
        if self.gated_performance is not None:
            sections["gated_performance"] = self.gated_performance.to_dict()
        if sections:
            data["sections"] = sections
        return data


class CommissionSummaryParity:
    """Column-level diff: computed 提成汇总 vs golden Excel sheet."""

    def __init__(
        self,
        join_keys: list[str] | None = None,
        numeric_tolerance: float = 1e-6,
        max_samples_per_column: int = 5,
        columns: list[str] | None = None,
        role_column: str | None = None,
        golden_workbook: Path | None = None,
        computed_perf_path: Path | None = None,
        deferred_cells: dict[str, frozenset[str]] | None = None,
    ) -> None:
        self.join_keys = join_keys or ["店别", "职务", "姓名"]
        self.numeric_tolerance = numeric_tolerance
        self.max_samples_per_column = max_samples_per_column
        self.columns = columns
        self.role_column = role_column
        self.golden_workbook = golden_workbook
        self.computed_perf_path = computed_perf_path
        self.deferred_cells = deferred_cells
        self._erwang_ah_adjustments: dict[str, float] | None = None

    def compare(
        self,
        computed: pd.DataFrame,
        golden: pd.DataFrame,
        *,
        golden_source: str = "golden",
        computed_source: str = "computed",
    ) -> ParityReport:
        computed = filter_comparable_rows(summary_frame_from_builder(computed))
        golden = filter_comparable_rows(summary_frame_from_builder(golden))

        merged = golden.merge(
            computed,
            on=self.join_keys,
            how="outer",
            indicator=True,
            suffixes=("_golden", "_computed"),
        )

        missing_in_computed = int((merged["_merge"] == "left_only").sum())
        missing_in_golden = int((merged["_merge"] == "right_only").sum())
        both = merged[merged["_merge"] == "both"].copy()

        compare_columns = self._compare_columns(golden, computed)
        role_results: list[RoleParityResult] = []

        roles = sorted(
            golden[self._role_column(golden)].dropna().astype(str).unique().tolist(),
            key=lambda x: str(x),
        )
        total_mismatch_cells = 0
        for role in roles:
            role_col_g = self._role_column(golden)
            role_golden = golden[golden[role_col_g].astype(str) == role]
            role_col_b = self._role_column(both)
            role_both = both[both[role_col_b].astype(str) == role]
            role_missing = int(len(role_golden) - len(role_both))
            role_result = self._compare_role_block(
                role, role_both, compare_columns, missing_rows=role_missing
            )
            role_results.append(role_result)
            total_mismatch_cells += role_result.mismatch_cells + role_missing * max(
                len(compare_columns), 1
            )

        overall_passed = (
            missing_in_computed == 0
            and missing_in_golden == 0
            and all(r.passed for r in role_results)
        )

        report = ParityReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            golden_source=golden_source,
            computed_source=computed_source,
            join_keys=self.join_keys,
            total_rows_golden=len(golden),
            total_rows_computed=len(computed),
            missing_in_computed=missing_in_computed,
            missing_in_golden=missing_in_golden,
            overall_passed=overall_passed,
            roles=role_results,
            summary=self._build_summary(overall_passed, role_results),
            section="metrics" if self.columns else "all",
            compared_columns=compare_columns,
        )
        logger.info("Parity overall_passed=%s", overall_passed)
        return report

    def compare_files(
        self,
        computed_path: Path,
        golden_workbook: Path,
        golden_sheet: str,
        *,
        header_row: int = 2,
        data_start_row: int = 3,
    ) -> ParityReport:
        computed = read_computed_summary_excel(computed_path)
        golden = read_golden_summary_sheet(
            golden_workbook,
            golden_sheet,
            header_row=header_row,
            data_start_row=data_start_row,
        )
        checker = self._with_workbook_paths(golden_workbook, computed_path)
        return checker.compare(
            computed,
            golden,
            golden_source=f"{golden_workbook.name}!{golden_sheet}",
            computed_source=str(computed_path),
        )

    def collect_cell_mismatches(
        self,
        computed: pd.DataFrame,
        golden: pd.DataFrame,
    ) -> list[CellMismatch]:
        """Return per-cell mismatches using the same rules as ``compare``."""
        computed = filter_comparable_rows(summary_frame_from_builder(computed))
        golden = filter_comparable_rows(summary_frame_from_builder(golden))

        merged = golden.merge(
            computed,
            on=self.join_keys,
            how="inner",
            suffixes=("_golden", "_computed"),
        )
        if merged.empty:
            return []

        compare_columns = self._compare_columns(golden, computed)
        roles = sorted(
            golden[self._role_column(golden)].dropna().astype(str).unique().tolist(),
            key=lambda x: str(x),
        )

        cells: list[CellMismatch] = []
        for role in roles:
            role_col_b = self._role_column(merged)
            role_both = merged[merged[role_col_b].astype(str) == role]
            cells.extend(
                self._collect_cell_mismatches_for_role(
                    role_both, compare_columns, role=str(role)
                )
            )
        return cells

    def collect_mismatches_from_files(
        self,
        computed_path: Path,
        golden_workbook: Path,
        golden_sheet: str,
        *,
        header_row: int = 2,
        data_start_row: int = 3,
        golden_header_row: int | None = None,
        golden_data_start_row: int | None = None,
    ) -> list[CellMismatch]:
        computed = read_computed_summary_excel(
            computed_path,
            header_row=header_row,
            data_start_row=data_start_row,
        )
        golden = read_golden_summary_sheet(
            golden_workbook,
            golden_sheet,
            header_row=golden_header_row if golden_header_row is not None else header_row,
            data_start_row=(
                golden_data_start_row if golden_data_start_row is not None else data_start_row
            ),
        )
        checker = self._with_workbook_paths(golden_workbook, computed_path)
        return checker.collect_cell_mismatches(computed, golden)

    def compare_aftersales_files(
        self,
        computed_path: Path,
        golden_workbook: Path,
        golden_sheet: str,
        column_map: dict[str, str],
        *,
        data_start_row: int = 6,
    ) -> ParityReport:
        computed = read_computed_aftersales_excel(
            computed_path, golden_sheet, column_map
        )
        golden = read_aftersales_metric_frame(
            golden_workbook,
            golden_sheet,
            column_map,
            data_start_row=data_start_row,
        )
        return self.compare(
            computed,
            golden,
            golden_source=f"{golden_workbook.name}!{golden_sheet}",
            computed_source=str(computed_path),
        )

    def compare_payout_files(
        self,
        computed_path: Path,
        golden_workbook: Path,
        golden_sheet: str,
        column_map: dict[str, str],
        *,
        data_start_row: int = 3,
    ) -> ParityReport:
        from salary_pipeline.data_ingestion.data_loader import (
            read_computed_payout_excel,
            read_payout_metric_frame,
        )

        computed = read_computed_payout_excel(computed_path, golden_sheet)
        golden = read_payout_metric_frame(
            golden_workbook,
            golden_sheet,
            column_map,
            data_start_row=data_start_row,
        )
        return self.compare(
            computed,
            golden,
            golden_source=f"{golden_workbook.name}!{golden_sheet}",
            computed_source=str(computed_path),
        )

    def _with_workbook_paths(
        self,
        golden_workbook: Path,
        computed_path: Path,
    ) -> CommissionSummaryParity:
        perf_path = self.computed_perf_path
        if perf_path is None:
            perf_path = computed_path.parent / "绩效整理表-系统生成.xlsx"
        if self.golden_workbook is not None and self.computed_perf_path is not None:
            return self
        return CommissionSummaryParity(
            join_keys=self.join_keys,
            numeric_tolerance=self.numeric_tolerance,
            max_samples_per_column=self.max_samples_per_column,
            columns=self.columns,
            role_column=self.role_column,
            golden_workbook=golden_workbook,
            computed_perf_path=perf_path,
        )

    def _erwang_adjustments(self) -> dict[str, float]:
        if self._erwang_ah_adjustments is None:
            self._erwang_ah_adjustments = erwang_blank_ah_adjustments_for_paths(
                self.golden_workbook,
                self.computed_perf_path,
            )
        return self._erwang_ah_adjustments

    def _apply_parity_skips(
        self,
        merged: pd.DataFrame,
        mismatches: pd.Series,
        *,
        role: str,
        column: str,
        g_col: str,
        c_col: str,
    ) -> pd.Series:
        if role == "销售顾问":
            name_col = "姓名_golden" if "姓名_golden" in merged.columns else "姓名"
            if name_col in merged.columns:
                deferred = self.deferred_cells
                if deferred is not None:
                    deferred_mask = merged[name_col].map(
                        lambda n: is_parity_deferred_cell(str(n), column, deferred)
                    )
                else:
                    from salary_pipeline.calculators.sales_advisor.registry import (
                        is_wa_parity_deferred,
                    )

                    deferred_mask = merged[name_col].map(
                        lambda n: is_wa_parity_deferred(str(n), column)
                    )
                mismatches = mismatches & ~deferred_mask
        adjustments = self._erwang_adjustments()
        if adjustments:
            name_col = "姓名_golden" if "姓名_golden" in merged.columns else "姓名"
            if name_col in merged.columns and g_col in merged.columns and c_col in merged.columns:
                skip_mask = merged.apply(
                    lambda row: hub_parity_skip_erwang_blank_ah(
                        str(row[name_col]),
                        column,
                        row[g_col],
                        row[c_col],
                        adjustments,
                        tolerance=self.numeric_tolerance,
                    ),
                    axis=1,
                )
                mismatches = mismatches & ~skip_mask
        return mismatches

    def _role_column(self, frame: pd.DataFrame) -> str:
        if self.role_column:
            for name in (f"{self.role_column}_golden", self.role_column):
                if name in frame.columns:
                    return name
        for name in ("职务_golden", "职务", "店别_golden", "店别"):
            if name in frame.columns:
                return name
        raise KeyError("role column not found for grouping")

    def _compare_columns(
        self, golden: pd.DataFrame, computed: pd.DataFrame
    ) -> list[str]:
        skip = set(self.join_keys) | {"序号"}
        golden_cols = set(golden.columns) - skip
        computed_cols = set(computed.columns) - skip
        common = sorted(golden_cols & computed_cols, key=str)
        if self.columns:
            allowed = set(self.columns)
            common = [col for col in common if col in allowed]
        return common

    def _compare_role_block(
        self,
        role: str,
        merged: pd.DataFrame,
        compare_columns: list[str],
        *,
        missing_rows: int = 0,
    ) -> RoleParityResult:
        column_diffs: list[ColumnDiff] = []
        mismatch_cells = 0

        for col in compare_columns:
            g_col = f"{col}_golden" if f"{col}_golden" in merged.columns else col
            c_col = f"{col}_computed" if f"{col}_computed" in merged.columns else col
            if g_col not in merged.columns or c_col not in merged.columns:
                continue

            g_series = merged[g_col]
            c_series = merged[c_col]
            mismatches = ~self._values_equal(g_series, c_series)
            mismatches = self._apply_parity_skips(
                merged,
                mismatches,
                role=str(role),
                column=col,
                g_col=g_col,
                c_col=c_col,
            )
            count = int(mismatches.sum())
            if count == 0:
                continue

            mismatch_cells += count
            max_diff = self._max_abs_diff(g_series[mismatches], c_series[mismatches])
            samples: list[dict[str, Any]] = []
            for idx in merged.index[mismatches][: self.max_samples_per_column]:
                row = merged.loc[idx]
                sample = {k: row.get(k) for k in self.join_keys}
                sample["golden"] = row[g_col]
                sample["computed"] = row[c_col]
                samples.append(sample)

            column_diffs.append(
                ColumnDiff(
                    column=col,
                    mismatch_count=count,
                    max_abs_diff=max_diff,
                    sample_rows=samples,
                )
            )

        golden_row_count = len(merged) + missing_rows
        passed = (
            missing_rows == 0
            and mismatch_cells == 0
            and golden_row_count > 0
        )

        return RoleParityResult(
            role=str(role),
            row_count=len(merged),
            golden_row_count=golden_row_count,
            missing_rows=missing_rows,
            compared_columns=len(compare_columns),
            mismatch_cells=mismatch_cells,
            passed=passed,
            column_diffs=column_diffs,
        )

    def _collect_cell_mismatches_for_role(
        self,
        merged: pd.DataFrame,
        compare_columns: list[str],
        *,
        role: str,
    ) -> list[CellMismatch]:
        cells: list[CellMismatch] = []
        for col in compare_columns:
            g_col = f"{col}_golden" if f"{col}_golden" in merged.columns else col
            c_col = f"{col}_computed" if f"{col}_computed" in merged.columns else col
            if g_col not in merged.columns or c_col not in merged.columns:
                continue

            g_series = merged[g_col]
            c_series = merged[c_col]
            mismatches = ~self._values_equal(g_series, c_series)
            mismatches = self._apply_parity_skips(
                merged,
                mismatches,
                role=role,
                column=col,
                g_col=g_col,
                c_col=c_col,
            )
            if not mismatches.any():
                continue

            for idx in merged.index[mismatches]:
                row = merged.loc[idx]
                join_values = tuple(
                    (key, row.get(f"{key}_golden", row.get(key)))
                    for key in self.join_keys
                )
                g_val = row[g_col]
                c_val = row[c_col]
                cells.append(
                    CellMismatch(
                        join_values=join_values,
                        column=col,
                        golden_value=_cell_float(g_val),
                        computed_value=_cell_float(c_val),
                    )
                )
        return cells

    def _values_equal(self, left: pd.Series, right: pd.Series) -> pd.Series:
        if len(left) == 0:
            return pd.Series(dtype=bool)

        out = left.isna() & right.isna()
        valid = ~out
        if not valid.any():
            return out

        l = left[valid]
        r = right[valid]
        lnum = pd.to_numeric(l, errors="coerce")
        rnum = pd.to_numeric(r, errors="coerce")
        numeric = lnum.notna() & rnum.notna()

        out_valid = pd.Series(False, index=l.index)
        if numeric.any():
            out_valid.loc[numeric] = (
                (lnum[numeric] - rnum[numeric]).abs() <= self.numeric_tolerance
            )
        text = ~numeric
        if text.any():
            out_valid.loc[text] = l[text].map(str).str.strip().eq(
                r[text].map(str).str.strip()
            )

        out.loc[valid] = out_valid
        return out

    def _max_abs_diff(self, left: pd.Series, right: pd.Series) -> float | None:
        left_num = pd.to_numeric(left, errors="coerce")
        right_num = pd.to_numeric(right, errors="coerce")
        if left_num.notna().any() or right_num.notna().any():
            return float((left_num - right_num).abs().max())
        return None

    def _build_summary(
        self, overall_passed: bool, roles: list[RoleParityResult]
    ) -> str:
        passed_roles = [r.role for r in roles if r.passed]
        failed_roles = [r.role for r in roles if not r.passed]
        lines = [
            f"整体: {'通过' if overall_passed else '未通过'}",
            f"岗位通过 ({len(passed_roles)}): {', '.join(passed_roles[:20])}"
            + (" ..." if len(passed_roles) > 20 else ""),
        ]
        if failed_roles:
            lines.append(
                f"岗位未通过 ({len(failed_roles)}): {', '.join(failed_roles[:20])}"
                + (" ..." if len(failed_roles) > 20 else "")
            )
        return "\n".join(lines)


def compare_hub_parity_bundle(
    computed_path: Path,
    golden_workbook: Path,
    golden_sheet: str,
    parity_cfg: dict[str, Any],
    *,
    deferred_cells: dict[str, frozenset[str]] | None = None,
) -> HubParityBundle:
    """Run F–P gate parity and optional W–AI performance tracking."""
    join_keys = parity_cfg.get("join_keys", ["店别", "职务", "姓名"])
    tolerance = float(parity_cfg.get("numeric_tolerance", 1e-6))
    header_row = int(parity_cfg.get("header_row", 2))
    data_start_row = int(parity_cfg.get("data_start_row", 3))

    metrics_checker = CommissionSummaryParity(
        join_keys=join_keys,
        numeric_tolerance=tolerance,
        columns=parity_cfg.get("columns"),
        deferred_cells=deferred_cells,
    )
    metrics = metrics_checker.compare_files(
        computed_path,
        golden_workbook,
        golden_sheet,
        header_row=header_row,
        data_start_row=data_start_row,
    )
    metrics.section = "metrics"

    perf_cols = parity_cfg.get("performance_columns") or []
    perf_path = computed_path.parent / "绩效整理表-系统生成.xlsx"
    performance = None
    if perf_cols:
        perf_checker = CommissionSummaryParity(
            join_keys=join_keys,
            numeric_tolerance=tolerance,
            columns=perf_cols,
            golden_workbook=golden_workbook,
            computed_perf_path=perf_path,
            deferred_cells=deferred_cells,
        )
        performance = perf_checker.compare_files(
            computed_path,
            golden_workbook,
            golden_sheet,
            header_row=header_row,
            data_start_row=data_start_row,
        )
        performance.section = "performance"
        performance.summary = (
            f"绩效块 W–AI（{len(perf_cols)} 列）: "
            + performance.summary.replace("整体:", "本层:")
        )

    gated_performance = _compare_gated_performance(
        computed_path,
        golden_workbook,
        golden_sheet,
        parity_cfg,
        perf_cols,
    )

    return HubParityBundle(
        metrics=metrics,
        performance=performance,
        gated_performance=gated_performance,
    )


def _compare_gated_performance(
    computed_path: Path,
    golden_workbook: Path,
    golden_sheet: str,
    parity_cfg: dict[str, Any],
    perf_cols: list[str],
) -> ParityReport | None:
    hub_cfg = load_hub_performance_config()
    if not gated_families(hub_cfg):
        return None

    gated_cols = [
        c for c in gated_performance_columns(hub_cfg) if c in perf_cols
    ]
    if not gated_cols:
        return None

    join_keys = parity_cfg.get("join_keys", ["店别", "职务", "姓名"])
    tolerance = float(parity_cfg.get("numeric_tolerance", 1e-6))
    header_row = int(parity_cfg.get("header_row", 2))
    data_start_row = int(parity_cfg.get("data_start_row", 3))

    computed = read_computed_summary_excel(computed_path)
    golden = read_golden_summary_sheet(
        golden_workbook,
        golden_sheet,
        header_row=header_row,
        data_start_row=data_start_row,
    )
    mask_g = combined_gated_row_mask(golden, hub_cfg)
    mask_c = combined_gated_row_mask(computed, hub_cfg)
    golden_sub = golden.loc[mask_g].copy()
    computed_sub = computed.loc[mask_c].copy()
    if golden_sub.empty and computed_sub.empty:
        return None

    family_names = ", ".join(gated_families(hub_cfg).keys())
    perf_path = computed_path.parent / "绩效整理表-系统生成.xlsx"
    checker = CommissionSummaryParity(
        join_keys=join_keys,
        numeric_tolerance=tolerance,
        columns=gated_cols,
        golden_workbook=golden_workbook,
        computed_perf_path=perf_path,
    )
    report = checker.compare(
        computed_sub,
        golden_sub,
        golden_source=f"{golden_workbook.name}!{golden_sheet} (parity_gate)",
        computed_source=f"{computed_path} (parity_gate)",
    )
    report.section = "gated_performance"
    report.summary = (
        f"算薪岗位族 parity_gate（{len(gated_cols)} 列 · {family_names}）: "
        + report.summary.replace("整体:", "本层:")
    )
    return report


def write_diff_report(report: ParityReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"差异报告_{stamp}.json"
    md_path = output_dir / f"差异报告_{stamp}.md"

    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    md_path.write_text(_render_markdown_report(report), encoding="utf-8")
    logger.info("Wrote diff report -> %s , %s", json_path, md_path)
    return json_path, md_path


def write_hub_diff_report(
    bundle: HubParityBundle, output_dir: Path
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"差异报告_{stamp}.json"
    md_path = output_dir / f"差异报告_{stamp}.md"

    json_path.write_text(
        json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    md_path.write_text(_render_hub_markdown_report(bundle), encoding="utf-8")
    logger.info("Wrote hub diff report -> %s , %s", json_path, md_path)
    return json_path, md_path


def _render_hub_markdown_report(bundle: HubParityBundle) -> str:
    lines = [
        "# 提成汇总 对账差异报告",
        "",
        "## F–P 验收层（硬门禁）",
        "",
    ]
    lines.append(_render_markdown_report(bundle.metrics).split("\n", 1)[1])
    if bundle.performance is not None:
        lines.extend(
            [
                "",
                "---",
                "",
                "## W–AI 绩效层（跟踪，不阻断 F–P）",
                "",
                f"- **本层结论: {'✅ 通过' if bundle.performance.overall_passed else '❌ 未通过'}**",
                f"- 对账列: {', '.join(bundle.performance.compared_columns)}",
                "",
                "```",
                bundle.performance.summary,
                "```",
                "",
                "### 分岗位（绩效层）",
                "",
                "| 岗位 | 金标准人数 | 匹配行数 | 缺失行数 | 不一致单元格 | 结论 |",
                "|------|------------|----------|----------|--------------|------|",
            ]
        )
        for role in bundle.performance.roles:
            status = "✅ 通过" if role.passed else "❌ 未通过"
            lines.append(
                f"| {role.role} | {role.golden_row_count} | {role.row_count} | "
                f"{role.missing_rows} | {role.mismatch_cells} | {status} |"
            )
    if bundle.gated_performance is not None:
        gp = bundle.gated_performance
        lines.extend(
            [
                "",
                "---",
                "",
                "## 算薪岗位族 W–AI（parity_gate 硬门禁）",
                "",
                f"- **本层结论: {'✅ 通过' if gp.overall_passed else '❌ 未通过'}**",
                f"- 对账列: {', '.join(gp.compared_columns)}",
                "",
                "```",
                gp.summary,
                "```",
                "",
                "### 分岗位（parity_gate）",
                "",
                "| 岗位 | 金标准人数 | 匹配行数 | 缺失行数 | 不一致单元格 | 结论 |",
                "|------|------------|----------|----------|--------------|------|",
            ]
        )
        for role in gp.roles:
            status = "✅ 通过" if role.passed else "❌ 未通过"
            lines.append(
                f"| {role.role} | {role.golden_row_count} | {role.row_count} | "
                f"{role.missing_rows} | {role.mismatch_cells} | {status} |"
            )
    return "\n".join(lines)


def _render_markdown_report(report: ParityReport) -> str:
    lines = [
        "# 提成汇总 对账差异报告",
        "",
        f"- 生成时间: {report.generated_at}",
        f"- 金标准: `{report.golden_source}`",
        f"- 计算结果: `{report.computed_source}`",
        f"- 关联键: {', '.join(report.join_keys)}",
        f"- 金标准行数: {report.total_rows_golden}",
        f"- 计算结果行数: {report.total_rows_computed}",
        f"- 金标准有但计算缺失: {report.missing_in_computed}",
        f"- 计算有但金标准缺失: {report.missing_in_golden}",
        f"- **整体结论: {'✅ 通过（差异为 0）' if report.overall_passed else '❌ 未通过'}**",
        "",
        "## 摘要",
        "",
        "```",
        report.summary,
        "```",
        "",
        "## 分岗位对账",
        "",
        "| 岗位 | 金标准人数 | 匹配行数 | 缺失行数 | 不一致单元格 | 结论 |",
        "|------|------------|----------|----------|--------------|------|",
    ]

    for role in report.roles:
        status = "✅ 通过" if role.passed else "❌ 未通过"
        lines.append(
            f"| {role.role} | {role.golden_row_count} | {role.row_count} | "
            f"{role.missing_rows} | {role.mismatch_cells} | {status} |"
        )

    failed = [r for r in report.roles if not r.passed and r.column_diffs]
    if failed:
        lines.extend(["", "## 列级差异明细（仅未通过岗位）", ""])
        for role in failed:
            lines.append(f"### {role.role}")
            lines.append("")
            for col_diff in role.column_diffs:
                lines.append(
                    f"- **{col_diff.column}**: {col_diff.mismatch_count} 处不一致"
                    + (
                        f", 最大绝对差 `{col_diff.max_abs_diff}`"
                        if col_diff.max_abs_diff is not None
                        else ""
                    )
                )
                for sample in col_diff.sample_rows:
                    keys = ", ".join(f"{k}={sample[k]}" for k in report.join_keys if k in sample)
                    lines.append(
                        f"  - {keys} | golden=`{sample.get('golden')}` "
                        f"computed=`{sample.get('computed')}`"
                    )
            lines.append("")

    lines.append(
        "\n> 说明：某岗位「通过」表示该岗位所有比对列与金标准差异为 0（在容差内）。"
    )
    return "\n".join(lines)
