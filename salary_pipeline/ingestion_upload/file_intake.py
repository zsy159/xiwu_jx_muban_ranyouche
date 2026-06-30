"""Upload intake: validate, scan sheets, match manifest, stage files."""

from __future__ import annotations

import io
import shutil
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import BinaryIO

from openpyxl import load_workbook

from salary_pipeline.ingestion_upload.manifest import (
    RequiredSheet,
    build_required_sheet_manifest,
    normalize_sheet_name,
    required_input_sheets,
    resolve_sheet_alias,
)
from salary_pipeline.paths import PROJECT_ROOT, raw_month_dir

MAX_FILE_BYTES = 80 * 1024 * 1024  # 80 MB per file
MAX_TOTAL_BYTES = 200 * 1024 * 1024
ALLOWED_SUFFIXES = {".xlsx", ".zip"}


class SheetMatchStatus(str, Enum):
    READY = "ready"
    MISSING = "missing"
    CONFLICT = "conflict"
    NOTE = "note"  # optional formula sheet present


@dataclass
class UploadedFile:
    filename: str
    path: Path
    size_bytes: int
    sheet_names: list[str] = field(default_factory=list)


@dataclass
class SheetMatch:
    required: RequiredSheet
    status: SheetMatchStatus
    sources: list[str] = field(default_factory=list)
    resolved_name: str | None = None


@dataclass
class IntakeResult:
    month_id: str
    staging_dir: Path
    uploads: list[UploadedFile]
    matches: list[SheetMatch]
    sales_workbook: Path | None = None
    rules_workbook: Path | None = None
    consolidated_workbook: Path | None = None
    sheet_sources_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def all_required_ready(self) -> bool:
        required = [m for m in self.matches if not m.required.optional_note]
        return all(m.status == SheetMatchStatus.READY for m in required)

    @property
    def missing_sheets(self) -> list[str]:
        return [
            m.required.name
            for m in self.matches
            if not m.required.optional_note and m.status == SheetMatchStatus.MISSING
        ]

    @property
    def conflict_sheets(self) -> list[str]:
        return [
            m.required.name
            for m in self.matches
            if m.status == SheetMatchStatus.CONFLICT
        ]

    def can_proceed(
        self, conflict_resolutions: dict[str, str] | None = None
    ) -> bool:
        """True when no required sheet is missing and every conflict has a source."""
        return not self.proceed_blockers(conflict_resolutions)

    def proceed_blockers(
        self, conflict_resolutions: dict[str, str] | None = None
    ) -> list[str]:
        """Human-readable reasons merge/trial buttons stay disabled."""
        conflict_resolutions = conflict_resolutions or {}
        blockers: list[str] = []
        missing = self.missing_sheets
        if missing:
            preview = "、".join(missing[:5])
            if len(missing) > 5:
                preview += "…"
            blockers.append(f"尚有 {len(missing)} 张必需表缺失（{preview}）")
        unresolved = [
            name
            for name in self.conflict_sheets
            if not conflict_resolutions.get(name)
        ]
        if unresolved:
            preview = "、".join(unresolved[:5])
            if len(unresolved) > 5:
                preview += "…"
            blockers.append(
                f"请先为 {len(unresolved)} 处冲突工作表选择来源（{preview}）"
            )
        return blockers


def display_match_status(
    match: SheetMatch,
    conflict_resolutions: dict[str, str] | None = None,
) -> tuple[SheetMatchStatus, list[str]]:
    """Status/sources for UI after the user picks a conflict source."""
    conflict_resolutions = conflict_resolutions or {}
    if match.status == SheetMatchStatus.CONFLICT:
        chosen = conflict_resolutions.get(match.required.name)
        if chosen and chosen in match.sources:
            return SheetMatchStatus.READY, [chosen]
    return match.status, list(match.sources)


def preferred_conflict_source_index(
    sources: list[str],
    *,
    sales_workbook: Path | None = None,
) -> int:
    """Prefer the sales workbook when multiple uploads contain the same sheet."""
    if sales_workbook is not None:
        sales_name = sales_workbook.name
        if sales_name in sources:
            return sources.index(sales_name)
    for idx, name in enumerate(sources):
        lower = name.lower()
        if "售后" in name:
            continue
        if "销售" in name or "西物" in lower:
            return idx
    return 0


def scan_workbook_sheets(path: Path) -> list[str]:
    """Read sheet names with openpyxl read_only."""
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _validate_upload(name: str, data: bytes) -> str | None:
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        return f"{name}: 仅支持 .xlsx / .zip"
    if len(data) > MAX_FILE_BYTES:
        return f"{name}: 单文件超过 {MAX_FILE_BYTES // (1024 * 1024)} MB"
    if suffix == ".xlsx" and not data[:2] == b"PK":
        return f"{name}: 不是有效的 xlsx (ZIP) 文件"
    return None


def _extract_zip(data: bytes, dest: Path) -> list[tuple[str, Path]]:
    extracted: list[tuple[str, Path]] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            inner_name = Path(info.filename).name
            if not inner_name.lower().endswith(".xlsx"):
                continue
            if info.file_size > MAX_FILE_BYTES:
                raise ValueError(f"ZIP 内 {inner_name} 超过大小限制")
            target = dest / inner_name
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
            extracted.append((inner_name, target))
    return extracted


def _save_uploads(
    uploads: list[tuple[str, bytes]],
    staging_dir: Path,
) -> list[Path]:
    upload_dir = staging_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    total = 0
    for name, data in uploads:
        err = _validate_upload(name, data)
        if err:
            raise ValueError(err)
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise ValueError(f"上传总量超过 {MAX_TOTAL_BYTES // (1024 * 1024)} MB")
        suffix = Path(name).suffix.lower()
        if suffix == ".zip":
            saved.extend(path for _, path in _extract_zip(data, upload_dir))
        else:
            target = upload_dir / Path(name).name
            target.write_bytes(data)
            saved.append(target)
    return saved


def _build_file_index(paths: list[Path]) -> list[UploadedFile]:
    files: list[UploadedFile] = []
    for path in paths:
        try:
            sheets = scan_workbook_sheets(path)
        except Exception as exc:
            raise ValueError(f"无法读取 {path.name}: {exc}") from exc
        files.append(
            UploadedFile(
                filename=path.name,
                path=path,
                size_bytes=path.stat().st_size,
                sheet_names=sheets,
            )
        )
    return files


def _match_sheets(
    manifest: list[RequiredSheet],
    files: list[UploadedFile],
) -> list[SheetMatch]:
    # sheet_name -> list of source filenames
    index: dict[str, list[str]] = {}
    alias_index: dict[str, list[str]] = {}
    for uf in files:
        for sheet in uf.sheet_names:
            index.setdefault(sheet, []).append(uf.filename)
            alias_index.setdefault(normalize_sheet_name(sheet), []).append(uf.filename)

    matches: list[SheetMatch] = []
    for req in manifest:
        resolved: str | None = None
        sources: list[str] = []
        for uf in files:
            found = resolve_sheet_alias(req.name, set(uf.sheet_names))
            if found:
                resolved = found
                sources.append(uf.filename)
        # dedupe sources preserving order
        seen: set[str] = set()
        unique_sources = []
        for src in sources:
            if src not in seen:
                seen.add(src)
                unique_sources.append(src)
        sources = unique_sources

        if req.optional_note:
            if sources:
                status = SheetMatchStatus.NOTE
            else:
                continue  # don't show absent formula sheets
            matches.append(
                SheetMatch(
                    required=req,
                    status=status,
                    sources=sources,
                    resolved_name=resolved,
                )
            )
            continue

        if not sources:
            status = SheetMatchStatus.MISSING
        elif len(sources) > 1:
            status = SheetMatchStatus.CONFLICT
        else:
            status = SheetMatchStatus.READY

        matches.append(
            SheetMatch(
                required=req,
                status=status,
                sources=sources,
                resolved_name=resolved,
            )
        )
    return matches


def _score_sales_candidate(uf: UploadedFile, required_names: set[str]) -> int:
    score = 0
    available = set(uf.sheet_names)
    for name in required_names:
        if resolve_sheet_alias(name, available):
            score += 1
    # Prefer filenames hinting at sales workbook
    lower = uf.filename.lower()
    if "销售" in lower or "西物" in lower:
        score += 3
    if "提成依据" in uf.filename or "依据" in uf.filename:
        score -= 5
    if "售后" in lower:
        score -= 10
    return score


def _infer_workbooks(
    files: list[UploadedFile],
    matches: list[SheetMatch],
) -> tuple[Path | None, Path | None]:
    path_by_name = {uf.filename: uf.path for uf in files}
    required_names = {
        m.required.name for m in matches if not m.required.optional_note
    }

    sales_file: str | None = None
    best_score = -1
    for uf in files:
        score = _score_sales_candidate(uf, required_names)
        if score > best_score:
            best_score = score
            sales_file = uf.filename

    rules_file: str | None = None
    for uf in files:
        if "提成依据" in uf.filename or "依据" in uf.filename:
            rules_file = uf.filename
            break

    sales_path = path_by_name.get(sales_file) if sales_file else None
    rules_path = path_by_name.get(rules_file) if rules_file else None
    return sales_path, rules_path


def intake_uploads(
    month_id: str,
    uploads: list[tuple[str, bytes]],
    *,
    staging_root: Path | None = None,
    manifest: list[RequiredSheet] | None = None,
) -> IntakeResult:
    """
    Validate uploads, scan sheet names, match manifest, write to staging.

    uploads: list of (filename, raw_bytes) from Streamlit file_uploader.
    """
    manifest = manifest or build_required_sheet_manifest()
    staging_dir = staging_root or (raw_month_dir(month_id) / ".staging")
    staging_dir.mkdir(parents=True, exist_ok=True)

    result = IntakeResult(
        month_id=month_id,
        staging_dir=staging_dir,
        uploads=[],
        matches=[],
    )

    try:
        saved_paths = _save_uploads(uploads, staging_dir)
    except ValueError as exc:
        result.errors.append(str(exc))
        return result

    if not saved_paths:
        result.errors.append("未找到有效的 .xlsx 文件")
        return result

    try:
        result.uploads = _build_file_index(saved_paths)
    except ValueError as exc:
        result.errors.append(str(exc))
        return result

    result.matches = _match_sheets(manifest, result.uploads)
    sales_path, rules_path = _infer_workbooks(result.uploads, result.matches)
    result.sales_workbook = sales_path
    result.rules_workbook = rules_path

    if result.conflict_sheets:
        result.warnings.append(
            "以下工作表在多个文件中出现，需人工选择来源后再合并: "
            + ", ".join(result.conflict_sheets)
        )

    return result


def read_upload_bytes(upload: BinaryIO | bytes, filename: str) -> tuple[str, bytes]:
    data = upload.read() if hasattr(upload, "read") else upload
    return filename, data


def _is_rules_workbook(path: Path) -> bool:
    return "提成依据" in path.name or path.name.startswith("依据")


def _is_sales_workbook(path: Path) -> bool:
    lower = path.name.lower()
    if not lower.endswith(".xlsx"):
        return False
    if "售后" in path.name:
        return False
    return "销售提成" in path.name or "西物超市" in path.name or (
        "销售" in path.name and "西物" in path.name
    )


def discover_local_raw_workbooks(month_id: str) -> tuple[Path | None, Path | None]:
    """
    Locate sales and rules workbooks under data/raw/<month_id>/.

    Sales: filename hints 西物/销售提成 (excludes 售后提成).
    Rules: 提成依据.xlsx or similar.
    """
    month_dir = raw_month_dir(month_id)
    if not month_dir.is_dir():
        return None, None

    sales: Path | None = None
    rules: Path | None = None
    for path in sorted(month_dir.glob("*.xlsx")):
        if _is_rules_workbook(path):
            rules = path
            continue
        if _is_sales_workbook(path):
            if sales is None or "西物" in path.name:
                sales = path
    return sales, rules


def intake_local_raw(
    month_id: str,
    *,
    include_rules_workbook: bool = False,
    sales_path: Path | None = None,
    rules_path: Path | None = None,
    staging_root: Path | None = None,
    manifest: list[RequiredSheet] | None = None,
) -> IntakeResult:
    """
    Simulate upload intake using workbooks already on disk in data/raw/<month>/.

    Copies files into staging/uploads/ and runs the same matching as intake_uploads.
    """
    month_dir = raw_month_dir(month_id)
    discovered_sales, discovered_rules = discover_local_raw_workbooks(month_id)
    sales = sales_path or discovered_sales
    rules = rules_path or discovered_rules

    staging_dir = staging_root or (raw_month_dir(month_id) / ".staging")
    result = IntakeResult(
        month_id=month_id,
        staging_dir=staging_dir,
        uploads=[],
        matches=[],
    )

    if sales is None or not sales.exists():
        result.errors.append(
            f"未在 {month_dir.relative_to(PROJECT_ROOT)} 找到销售提成工作簿"
            "（文件名需含「销售提成」或「西物超市」，且非售后）"
        )
        return result

    uploads: list[tuple[str, bytes]] = [(sales.name, sales.read_bytes())]
    if include_rules_workbook:
        if rules is None or not rules.exists():
            result.warnings.append(
                f"已勾选包含提成依据，但 {month_dir.relative_to(PROJECT_ROOT)} 下未找到"
            )
        else:
            uploads.append((rules.name, rules.read_bytes()))

    intake = intake_uploads(
        month_id,
        uploads,
        staging_root=staging_dir,
        manifest=manifest,
    )
    intake.warnings = result.warnings + intake.warnings
    return intake
