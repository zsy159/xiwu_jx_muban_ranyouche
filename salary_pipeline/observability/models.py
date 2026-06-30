from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from salary_pipeline.validation.parity import (
    ColumnDiff,
    ParityReport,
    RoleParityResult,
)


def parity_report_from_dict(data: dict[str, Any]) -> ParityReport:
    roles = []
    for role in data.get("roles", []):
        col_diffs = [
            ColumnDiff(**cd) for cd in role.get("column_diffs", [])
        ]
        roles.append(
            RoleParityResult(
                role=role["role"],
                row_count=role["row_count"],
                golden_row_count=role["golden_row_count"],
                missing_rows=role["missing_rows"],
                compared_columns=role["compared_columns"],
                mismatch_cells=role["mismatch_cells"],
                passed=role["passed"],
                column_diffs=col_diffs,
            )
        )
    return ParityReport(
        generated_at=data["generated_at"],
        golden_source=data["golden_source"],
        computed_source=data["computed_source"],
        join_keys=data["join_keys"],
        total_rows_golden=data["total_rows_golden"],
        total_rows_computed=data["total_rows_computed"],
        missing_in_computed=data["missing_in_computed"],
        missing_in_golden=data["missing_in_golden"],
        overall_passed=data["overall_passed"],
        roles=roles,
        summary=data.get("summary", ""),
        section=data.get("section", "metrics"),
        compared_columns=data.get("compared_columns", []),
        sections=data.get("sections", {}),
    )


def performance_report_from_dict(data: dict[str, Any]) -> ParityReport | None:
    perf = data.get("sections", {}).get("performance")
    if not perf:
        return None
    return parity_report_from_dict(perf)


def gated_performance_report_from_dict(data: dict[str, Any]) -> ParityReport | None:
    gated = data.get("sections", {}).get("gated_performance")
    if not gated:
        return None
    return parity_report_from_dict(gated)


@dataclass
class MonthInfo:
    month_id: str
    label: str
    status: str
    has_output: bool
    has_raw: bool
    config_file: str


@dataclass
class AnchorSnapshot:
    anchor_id: str
    label: str
    overall_passed: bool | None
    failed_roles: int
    total_roles: int
    mismatch_cells: int
    report_path: str | None
    report_time: str | None
    computed_path: str | None
    has_output: bool
    warnings_count: int
    warnings_path: str | None
    performance_passed: bool | None = None
    performance_mismatch_cells: int = 0
    gated_performance_passed: bool | None = None
    gated_performance_mismatch_cells: int = 0

    @property
    def status_icon(self) -> str:
        if not self.has_output:
            return "⏳"
        if self.overall_passed:
            if self.gated_performance_passed is False:
                return "⚠️"
            if self.gated_performance_passed is True:
                return "✅"
            if self.performance_passed is False:
                return "⚠️"
            return "✅"
        if self.failed_roles == 0 and self.mismatch_cells == 0:
            return "✅"
        return "⚠️"


@dataclass
class AcceptanceSummary:
    month_id: str
    month_label: str
    generated_at: str
    anchors: list[AnchorSnapshot] = field(default_factory=list)
    failed_role_details: list[dict[str, Any]] = field(default_factory=list)
