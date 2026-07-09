"""Helpers for the 新月接入 Streamlit page (testable without Streamlit)."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from salary_pipeline.ingestion_upload.file_intake import (
    IntakeResult,
    SheetMatchStatus,
    intake_uploads,
    preferred_conflict_source_index,
)
from salary_pipeline.ingestion_upload.sheet_merge import build_consolidated_workbook
from salary_pipeline.observability.loaders import discover_months
from salary_pipeline.ingestion_upload.default_rules import canonical_month_label
from salary_pipeline.paths import PROJECT_ROOT, raw_month_dir

_MONTH_ID_RE = re.compile(r"^\d{4}-\d{2}$")

RULE_CANONICAL = "canonical"
RULE_INHERIT = "inherit"
RULE_EXTRACT = "extract"
UPLOAD_MODE_FULL = "full"
UPLOAD_MODE_SHEETS = "sheets"


def validate_month_id(month_id: str) -> str | None:
    """Return an error message when invalid, else None."""
    trimmed = month_id.strip()
    if not trimmed:
        return "账期不能为空"
    if not _MONTH_ID_RE.match(trimmed):
        return "账期格式须为 YYYY-MM（如 2026-07）"
    return None


def default_label_for_month(month_id: str) -> str:
    """e.g. 2026-07 → 2026年07月"""
    trimmed = month_id.strip()
    if _MONTH_ID_RE.match(trimmed):
        year, month = trimmed.split("-")
        return f"{year}年{month}月"
    return trimmed


def sales_save_path(month_id: str, uploaded_filename: str) -> Path:
    month_dir = raw_month_dir(month_id)
    if uploaded_filename.lower().endswith(".xlsx"):
        name = Path(uploaded_filename).name
    else:
        name = f"销售账套-合并-{month_id}.xlsx"
    return month_dir / name


def save_sales_workbook(
    month_id: str, uploaded_bytes: bytes, uploaded_filename: str
) -> Path:
    dest = sales_save_path(month_id, uploaded_filename)
    os.makedirs(dest.parent, exist_ok=True)
    dest.write_bytes(uploaded_bytes)
    return dest


def sales_relative_path(saved_path: Path) -> str:
    resolved = saved_path.resolve()
    root = PROJECT_ROOT.resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def list_inherit_source_months(target_month_id: str) -> list[str]:
    target = target_month_id.strip()
    return [m.month_id for m in discover_months() if m.month_id != target]


def default_rule_mode_label() -> str:
    _, label = canonical_month_label()
    return label


@dataclass
class OnboardSheetResult:
    """Outcome of per-sheet upload processing for onboarding."""

    sales_path: Path | None = None
    sheet_sources_path: Path | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def auto_conflict_resolutions(intake: IntakeResult) -> dict[str, str]:
    """Pick a default source file for each conflicting required sheet."""
    resolutions: dict[str, str] = {}
    for match in intake.matches:
        if match.status != SheetMatchStatus.CONFLICT:
            continue
        idx = preferred_conflict_source_index(
            match.sources,
            sales_workbook=intake.sales_workbook,
        )
        resolutions[match.required.name] = match.sources[idx]
    return resolutions


def consolidated_workbook_path(month_id: str) -> Path:
    return raw_month_dir(month_id) / f"销售账套-合并-{month_id}.xlsx"


def prepare_onboard_from_sheet_uploads(
    month_id: str,
    uploads: list[tuple[str, bytes]],
) -> OnboardSheetResult:
    """
    Match per-sheet uploads, persist to data/raw/<month>/uploads/,
    merge into 销售账套-合并-<month>.xlsx, and write sheet_sources.json.
    """
    result = OnboardSheetResult()
    if not uploads:
        result.errors.append("请至少上传一个 Excel 或 ZIP 文件")
        return result

    staging_root = raw_month_dir(month_id) / ".onboard_staging"
    intake = intake_uploads(month_id, uploads, staging_root=staging_root)
    if intake.errors:
        result.errors.extend(intake.errors)
        return result

    resolutions = auto_conflict_resolutions(intake)
    blockers = intake.proceed_blockers(resolutions)
    if blockers:
        result.errors.extend(blockers)
        return result

    upload_dir = raw_month_dir(month_id) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    for uf in intake.uploads:
        shutil.copy2(uf.path, upload_dir / uf.filename)

    formal_pairs = [(p.name, p.read_bytes()) for p in sorted(upload_dir.glob("*.xlsx"))]
    intake = intake_uploads(month_id, formal_pairs, staging_root=staging_root)
    if intake.errors:
        result.errors.extend(intake.errors)
        return result

    resolutions = auto_conflict_resolutions(intake)
    blockers = intake.proceed_blockers(resolutions)
    if blockers:
        result.errors.extend(blockers)
        return result

    month_dir = raw_month_dir(month_id)
    month_dir.mkdir(parents=True, exist_ok=True)
    consolidated = consolidated_workbook_path(month_id)

    try:
        build_consolidated_workbook(
            intake,
            consolidated,
            conflict_resolutions=resolutions,
        )
    except (ValueError, OSError) as exc:
        result.errors.append(f"合并销售账套失败: {exc}")
        return result

    result.warnings.extend(intake.warnings)
    result.sales_path = consolidated
    result.sheet_sources_path = intake.sheet_sources_path
    return result
