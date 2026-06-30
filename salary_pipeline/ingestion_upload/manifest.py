"""Required input sheet manifest for sales-side payroll upload."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from salary_pipeline.calculators.direct_store_manager.extract import (
    SHEET as DIRECT_STORE_MANAGER_SHEET,
)
from salary_pipeline.data_ingestion import closure_input_sheets as closure
from salary_pipeline.data_ingestion import (
    customer_specialist_sheet as customer,
    invite_specialist_sheet as invite,
    new_media_sheet as new_media,
)
from salary_pipeline.paths import CONFIG_DIR

# Formula tables — not required inputs; note if present in uploads.
FORMULA_SHEET_NOTES: tuple[str, ...] = (
    "销售任务及完成率",
)

FAMILY_SALES = "销售底层"

FAMILY_DISPLAY_ORDER: tuple[str, ...] = (
    FAMILY_SALES,
    "新媒体",
    "邀约专员",
    "客户专员",
    "直营店经理",
    "招聘",
)

CLOSURE_SHEETS: tuple[str, ...] = (
    closure.COMPARISON_SHEET,
    closure.COMMISSION_STANDARD_SHEET,
    closure.REGISTRATION_COMMISSION_SHEET,
    closure.CAR_INSURANCE_PRODUCT_SHEET,
    closure.TRADE_IN_SERVICE_SHEET,
    closure.USED_CAR_TRADE_SHEET,
    closure.BIG_CUSTOMER_SHEET,
    closure.OVERDUE_CAMPAIGN_SHEET,
    closure.SYSTEM_EXCESS_SHEET,
    closure.WARRANTY_COMMISSION_SHEET,
)

# (family_label, sheet_name, header_row) — role-specific inputs from data_ingestion.
ROLE_FAMILY_INPUTS: tuple[tuple[str, str, int], ...] = (
    ("新媒体", new_media.NEW_MEDIA_SHEET, 1),
    ("邀约专员", invite.INVITE_SHEET, 1),
    ("客户专员", customer.SHEET, 1),
    ("直营店经理", DIRECT_STORE_MANAGER_SHEET, 1),
    ("招聘", "招聘", 1),  # recruit_sheet.RECRUIT_SHEET — literal to avoid circular import
)


@dataclass(frozen=True)
class RequiredSheet:
    name: str
    header_row: int = 1
    source: str = "registry"  # registry | closure | role
    role: str = "input"
    optional_note: bool = False
    families: tuple[str, ...] = (FAMILY_SALES,)


def _load_registry() -> dict[str, Any]:
    path = CONFIG_DIR / "sheet_registry.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _merge_sheet(
    by_name: dict[str, RequiredSheet],
    sheet: RequiredSheet,
) -> None:
    """One manifest entry per sheet name; merge family labels when duplicated."""
    existing = by_name.get(sheet.name)
    if existing is None:
        by_name[sheet.name] = sheet
        return
    merged_families = tuple(
        dict.fromkeys(existing.families + sheet.families)
    )
    by_name[sheet.name] = replace(existing, families=merged_families)


def build_required_sheet_manifest(
    registry_path: Path | None = None,
) -> list[RequiredSheet]:
    """Build required input sheets from registry, closure, and role-family subsheets."""
    if registry_path is not None:
        with registry_path.open(encoding="utf-8") as handle:
            registry = yaml.safe_load(handle)
    else:
        registry = _load_registry()

    by_name: dict[str, RequiredSheet] = {}
    sales = registry.get("sales_workbook", {})
    for name, meta in sales.items():
        if meta.get("role") != "input":
            continue
        _merge_sheet(
            by_name,
            RequiredSheet(
                name=name,
                header_row=int(meta.get("header_row", 1)),
                source="registry",
                role="input",
                families=(FAMILY_SALES,),
            ),
        )

    registry_names = set(by_name)
    for name in CLOSURE_SHEETS:
        if name in registry_names:
            continue
        _merge_sheet(
            by_name,
            RequiredSheet(
                name=name,
                header_row=1,
                source="closure",
                role="input",
                families=(FAMILY_SALES,),
            ),
        )

    for family, name, header_row in ROLE_FAMILY_INPUTS:
        _merge_sheet(
            by_name,
            RequiredSheet(
                name=name,
                header_row=header_row,
                source="role",
                role="input",
                families=(family,),
            ),
        )

    for name in FORMULA_SHEET_NOTES:
        meta = sales.get(name, {})
        _merge_sheet(
            by_name,
            RequiredSheet(
                name=name,
                header_row=int(meta.get("header_row", 1)),
                source="registry",
                role=meta.get("role", "formula"),
                optional_note=True,
                families=(FAMILY_SALES,),
            ),
        )

    return list(by_name.values())


def required_input_sheets(manifest: list[RequiredSheet] | None = None) -> list[RequiredSheet]:
    """Only mandatory inputs (exclude optional formula notes)."""
    manifest = manifest or build_required_sheet_manifest()
    return [sheet for sheet in manifest if not sheet.optional_note]


def group_manifest_by_family(
    manifest: list[RequiredSheet] | None = None,
) -> list[tuple[str, list[RequiredSheet]]]:
    """Return (family_label, sheets) in display order; sheets sorted by name."""
    manifest = manifest or build_required_sheet_manifest()
    grouped: dict[str, list[RequiredSheet]] = {label: [] for label in FAMILY_DISPLAY_ORDER}
    for sheet in manifest:
        for family in sheet.families:
            if family not in grouped:
                grouped[family] = []
            if sheet not in grouped[family]:
                grouped[family].append(sheet)
    result: list[tuple[str, list[RequiredSheet]]] = []
    for label in FAMILY_DISPLAY_ORDER:
        sheets = sorted(grouped.get(label, []), key=lambda s: s.name)
        if sheets:
            result.append((label, sheets))
    return result


def normalize_sheet_name(name: str) -> str:
    """Match sheet names with optional trailing whitespace (e.g. 二手置换 )."""
    return name.strip()


def resolve_sheet_alias(name: str, available: set[str]) -> str | None:
    """Find actual sheet name in workbook for a manifest entry."""
    if name in available:
        return name
    normalized = normalize_sheet_name(name)
    for candidate in available:
        if normalize_sheet_name(candidate) == normalized:
            return candidate
    return None
