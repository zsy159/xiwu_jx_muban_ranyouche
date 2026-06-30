"""Collect formula-anomaly annotations for 提成汇总 reconcile Excel output."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

import yaml

from salary_pipeline.calculators.sales_advisor.registry import (
    is_hub_linked,
    load_role_registry,
    wa_parity_deferred_cells,
)
from salary_pipeline.calculators.sales_advisor.topology_specs import (
    HUB_LETTERS_W_AI,
    _topology_cells,
    hub_column_name,
)
from salary_pipeline.paths import CONFIG_DIR

_ANNOTATION_PATH = CONFIG_DIR / "parity_annotation.yaml"


@dataclass(frozen=True)
class HubCellAnnotation:
    """One annotated Hub cell (姓名 + 列名)."""

    name: str
    column: str
    reason: str
    source: str = "registry"
    golden_value: float | None = None
    computed_value: float | None = None

    def key(self) -> tuple[str, str]:
        return (self.name.strip(), self.column.strip())

    def comment_text(self) -> str:
        lines = [self.reason.strip()]
        if self.golden_value is not None and self.computed_value is not None:
            diff = self.computed_value - self.golden_value
            lines.append(
                f"金标准={self.golden_value:g}  系统={self.computed_value:g}  差={diff:+g}"
            )
        return "\n".join(lines)


def load_annotation_registry(path: Path | None = None) -> list[HubCellAnnotation]:
    cfg_path = path or _ANNOTATION_PATH
    if not cfg_path.exists():
        return []
    with cfg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    out: list[HubCellAnnotation] = []
    for entry in data.get("hub_annotations") or []:
        name = str(entry.get("name", "")).strip()
        column = str(entry.get("column", "")).strip()
        reason = str(entry.get("reason", "")).strip()
        if name and column and reason:
            out.append(HubCellAnnotation(name=name, column=column, reason=reason))
    return out


def _deferred_as_annotations(registry: dict[str, Any] | None = None) -> list[HubCellAnnotation]:
    reg = registry or load_role_registry()
    out: list[HubCellAnnotation] = []
    for entry in reg.get("wa_parity_deferred") or []:
        name = str(entry.get("name", "")).strip()
        cols = entry.get("columns") or {}
        for column, reason in cols.items():
            column = str(column).strip()
            reason = str(reason).strip()
            if name and column and reason:
                out.append(
                    HubCellAnnotation(
                        name=name,
                        column=column,
                        reason=reason,
                        source="deferred",
                    )
                )
    return out


def detect_topology_formula_anomalies(
    registry: dict[str, Any] | None = None,
) -> list[HubCellAnnotation]:
    """Scan golden Hub topology for broken refs (tail constants → blue deferred)."""
    reg = registry or load_role_registry()
    cells = _topology_cells()
    advisors = [
        (str(r["name"]).strip(), int(r["hub_excel_row"]))
        for r in reg.get("roles") or []
        if is_hub_linked(r) and r.get("hub_excel_row")
    ]
    if not advisors:
        return []

    out: list[HubCellAnnotation] = []
    for letter in HUB_LETTERS_W_AI:
        column = hub_column_name(letter)
        for name, excel_row in advisors:
            key = f"提成汇总!{letter}{excel_row}"
            cell = cells.get(key, {})
            formula = str(cell.get("formula") or "").strip()

            reason: str | None = None
            if formula and "#REF!" in formula.upper():
                reason = (
                    f"金标准 {column} 公式含 #REF! 断裂引用：{formula[:100]}"
                )

            if reason:
                out.append(
                    HubCellAnnotation(
                        name=name,
                        column=column,
                        reason=reason,
                        source="topology",
                    )
                )
    return out


def collect_hub_cell_annotations(
    *,
    registry: dict[str, Any] | None = None,
    parity_values: dict[tuple[str, str], tuple[float | None, float | None]] | None = None,
    include_topology: bool = True,
    include_deferred: bool = False,
) -> list[HubCellAnnotation]:
    """Merge YAML registry + optional topology auto-detect; enrich with parity diff."""
    merged: dict[tuple[str, str], HubCellAnnotation] = {}

    for ann in load_annotation_registry():
        merged[ann.key()] = ann

    if include_topology:
        for ann in detect_topology_formula_anomalies(registry):
            merged.setdefault(ann.key(), ann)

    if include_deferred:
        for ann in _deferred_as_annotations(registry):
            merged.setdefault(ann.key(), ann)

    if parity_values:
        enriched: dict[tuple[str, str], HubCellAnnotation] = {}
        for key, ann in merged.items():
            golden, computed = parity_values.get(key, (None, None))
            if golden is not None or computed is not None:
                enriched[key] = replace(
                    ann,
                    golden_value=golden,
                    computed_value=computed,
                )
            else:
                enriched[key] = ann
        merged = enriched

    return list(merged.values())


def parity_values_for_annotations(
    computed_path: Path,
    golden_workbook: Path,
    golden_sheet: str,
    annotation_keys: Iterable[tuple[str, str]],
    *,
    join_keys: list[str] | None = None,
    header_row: int = 2,
    data_start_row: int = 3,
) -> dict[tuple[str, str], tuple[float | None, float | None]]:
    """Load golden vs computed values for annotated (姓名, 列) pairs."""
    from salary_pipeline.data_ingestion.data_loader import (
        read_computed_summary_excel,
        read_golden_summary_sheet,
        summary_frame_from_builder,
    )
    from salary_pipeline.validation.parity import filter_comparable_rows

    keys = list(annotation_keys)
    if not keys:
        return {}

    join_keys = join_keys or ["店别", "职务", "姓名"]
    columns = sorted({col for _, col in keys})
    computed = filter_comparable_rows(
        summary_frame_from_builder(read_computed_summary_excel(computed_path))
    )
    golden = filter_comparable_rows(
        summary_frame_from_builder(
            read_golden_summary_sheet(
                golden_workbook,
                golden_sheet,
                header_row=header_row,
                data_start_row=data_start_row,
            )
        )
    )
    merged = golden.merge(
        computed,
        on=join_keys,
        how="inner",
        suffixes=("_golden", "_computed"),
    )
    if merged.empty:
        return {}

    out: dict[tuple[str, str], tuple[float | None, float | None]] = {}
    name_col = "姓名_golden" if "姓名_golden" in merged.columns else "姓名"
    for name, col in keys:
        g_col = f"{col}_golden" if f"{col}_golden" in merged.columns else col
        c_col = f"{col}_computed" if f"{col}_computed" in merged.columns else col
        if g_col not in merged.columns or c_col not in merged.columns:
            continue
        rows = merged[merged[name_col].astype(str).str.strip() == name.strip()]
        if rows.empty:
            continue
        row = rows.iloc[0]
        g_val = row[g_col]
        c_val = row[c_col]
        try:
            g_num = float(g_val) if g_val == g_val else None  # NaN check
        except (TypeError, ValueError):
            g_num = None
        try:
            c_num = float(c_val) if c_val == c_val else None
        except (TypeError, ValueError):
            c_num = None
        out[(name, col)] = (g_num, c_num)
    return out


def annotations_for_workbook(
    *,
    registry: dict[str, Any] | None = None,
    parity_values: dict[tuple[str, str], tuple[float | None, float | None]] | None = None,
    deferred_cells: dict[str, frozenset[str]] | None = None,
) -> list[HubCellAnnotation]:
    """Annotations for reconcile: registry + topology; skip deferred / manual-formula cells."""
    reg = registry or load_role_registry()
    deferred = deferred_cells if deferred_cells is not None else wa_parity_deferred_cells(reg)
    annotations = collect_hub_cell_annotations(
        registry=reg,
        parity_values=parity_values,
        include_topology=True,
        include_deferred=False,
    )
    filtered: list[HubCellAnnotation] = []
    for ann in annotations:
        if ann.column in deferred.get(ann.name, frozenset()):
            continue
        filtered.append(ann)
    return filtered
