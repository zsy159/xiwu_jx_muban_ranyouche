from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from salary_pipeline.observability.models import (
    AcceptanceSummary,
    AnchorSnapshot,
    MonthInfo,
    gated_performance_report_from_dict,
    parity_report_from_dict,
    performance_report_from_dict,
)
from salary_pipeline.paths import (
    CONFIG_DIR,
    OUTPUT_DIR,
    RAW_DATA_DIR,
    resolve_project_path,
)
from salary_pipeline.validation.parity import ParityReport

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def load_observability_config() -> dict[str, Any]:
    path = CONFIG_DIR / "observability.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_months_registry() -> dict[str, Any]:
    path = CONFIG_DIR / "months_registry.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def discover_months() -> list[MonthInfo]:
    registry = load_months_registry()
    known: dict[str, dict[str, Any]] = dict(registry.get("months", {}))

    for base in (RAW_DATA_DIR, OUTPUT_DIR):
        if not base.exists():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and _MONTH_RE.match(child.name):
                known.setdefault(
                    child.name,
                    {
                        "label": child.name,
                        "config": "month.yaml",
                        "status": "discovered",
                        "sources": {
                            "raw_dir": f"data/raw/{child.name}",
                            "output_dir": f"output/{child.name}",
                        },
                    },
                )

    months: list[MonthInfo] = []
    for month_id, entry in sorted(known.items()):
        sources = entry.get("sources", {})
        raw = resolve_project_path(sources.get("raw_dir", f"data/raw/{month_id}"))
        out = resolve_project_path(sources.get("output_dir", f"output/{month_id}"))
        months.append(
            MonthInfo(
                month_id=month_id,
                label=entry.get("label", month_id),
                status=entry.get("status", "discovered"),
                has_output=out.exists() and any(out.iterdir()) if out.exists() else False,
                has_raw=raw.exists() and any(raw.glob("*.xlsx")) if raw.exists() else False,
                config_file=entry.get("config", "month.yaml"),
            )
        )
    return months


def load_month_config_for(month_id: str) -> dict[str, Any]:
    registry = load_months_registry()
    entry = registry.get("months", {}).get(month_id, {})
    config_name = entry.get("config", "month.yaml")
    config_path = CONFIG_DIR / config_name
    with config_path.open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)

    if cfg.get("month") == month_id:
        return cfg

    patched = json.loads(json.dumps(cfg))
    patched["month"] = month_id

    def _patch_paths(obj: Any) -> Any:
        if isinstance(obj, str) and re.search(r"\d{4}-\d{2}", obj):
            return re.sub(r"\d{4}-\d{2}", month_id, obj)
        if isinstance(obj, dict):
            return {k: _patch_paths(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_patch_paths(v) for v in obj]
        return obj

    return _patch_paths(patched)


def register_month(
    month_id: str,
    label: str,
    raw_dir: str,
    *,
    config: str = "month.yaml",
) -> None:
    """Append a month entry to months_registry.yaml (MVP: manual path registration)."""
    if not _MONTH_RE.match(month_id):
        raise ValueError(f"Invalid month id: {month_id}")
    registry = load_months_registry()
    registry.setdefault("months", {})[month_id] = {
        "label": label,
        "config": config,
        "status": "imported",
        "sources": {
            "raw_dir": raw_dir,
            "output_dir": f"output/{month_id}",
        },
    }
    path = CONFIG_DIR / "months_registry.yaml"
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(registry, handle, allow_unicode=True, sort_keys=False)


def find_latest_parity_report(
    report_dir: Path,
    *,
    computed_match: str | None = None,
) -> Path | None:
    if not report_dir.exists():
        return None
    candidates: list[tuple[datetime, Path]] = []
    for path in report_dir.glob("差异报告_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        source = str(data.get("computed_source", ""))
        if computed_match and computed_match not in source:
            continue
        ts = _parse_report_timestamp(path.stem, data.get("generated_at"))
        candidates.append((ts, path))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _parse_report_timestamp(stem: str, iso: str | None) -> datetime:
    if iso:
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            pass
    # 差异报告_20260623_162610
    m = re.search(r"_(\d{8})_(\d{6})$", stem)
    if m:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    return datetime.min


def load_parity_report(path: Path) -> ParityReport:
    data = json.loads(path.read_text(encoding="utf-8"))
    return parity_report_from_dict(data)


def load_warnings(report_dir: Path, filename: str) -> list[str]:
    path = report_dir / filename
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def get_anchor_snapshots(month_id: str) -> list[AnchorSnapshot]:
    obs = load_observability_config()
    cfg = load_month_config_for(month_id)
    report_dir = resolve_project_path(cfg["outputs"]["report_dir"])
    anchors_cfg = obs.get("anchors", {})
    snapshots: list[AnchorSnapshot] = []

    for anchor_id, anchor in anchors_cfg.items():
        output_key = anchor["output_key"]
        computed_rel = cfg["outputs"].get(output_key)
        computed_path = resolve_project_path(computed_rel) if computed_rel else None
        has_output = computed_path is not None and computed_path.exists()

        report_path = find_latest_parity_report(
            report_dir,
            computed_match=anchor.get("computed_match"),
        )
        report: ParityReport | None = None
        if report_path:
            report = load_parity_report(report_path)

        warnings = load_warnings(report_dir, anchor.get("warnings_file", ""))
        failed_roles = 0
        mismatch_cells = 0
        total_roles = 0
        performance_passed: bool | None = None
        performance_mismatch_cells = 0
        gated_performance_passed: bool | None = None
        gated_performance_mismatch_cells = 0
        if report_path:
            raw = json.loads(report_path.read_text(encoding="utf-8"))
            perf_report = performance_report_from_dict(raw)
            if perf_report is not None:
                performance_passed = perf_report.overall_passed
                performance_mismatch_cells = sum(
                    r.mismatch_cells for r in perf_report.roles
                )
            gated_report = gated_performance_report_from_dict(raw)
            if gated_report is not None:
                gated_performance_passed = gated_report.overall_passed
                gated_performance_mismatch_cells = sum(
                    r.mismatch_cells for r in gated_report.roles
                )
        if report:
            total_roles = len(report.roles)
            failed_roles = sum(1 for r in report.roles if not r.passed)
            mismatch_cells = sum(r.mismatch_cells for r in report.roles)

        snapshots.append(
            AnchorSnapshot(
                anchor_id=anchor_id,
                label=anchor["label"],
                overall_passed=report.overall_passed if report else None,
                failed_roles=failed_roles,
                total_roles=total_roles,
                mismatch_cells=mismatch_cells,
                report_path=str(report_path) if report_path else None,
                report_time=report.generated_at if report else None,
                computed_path=str(computed_path) if computed_path else None,
                has_output=has_output,
                warnings_count=len(warnings),
                warnings_path=str(report_dir / anchor["warnings_file"])
                if anchor.get("warnings_file")
                else None,
                performance_passed=performance_passed,
                performance_mismatch_cells=performance_mismatch_cells,
                gated_performance_passed=gated_performance_passed,
                gated_performance_mismatch_cells=gated_performance_mismatch_cells,
            )
        )
    return snapshots


def build_acceptance_summary(month_id: str) -> AcceptanceSummary:
    months = {m.month_id: m for m in discover_months()}
    month = months.get(month_id)
    anchors = get_anchor_snapshots(month_id)
    failed_details: list[dict[str, Any]] = []

    for snap in anchors:
        if not snap.report_path:
            continue
        report = load_parity_report(Path(snap.report_path))
        for role in report.roles:
            if not role.passed:
                failed_details.append(
                    {
                        "表": snap.label,
                        "岗位": role.role,
                        "不一致单元格": role.mismatch_cells,
                        "缺失行": role.missing_rows,
                    }
                )

    return AcceptanceSummary(
        month_id=month_id,
        month_label=month.label if month else month_id,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        anchors=anchors,
        failed_role_details=failed_details,
    )


def render_acceptance_markdown(summary: AcceptanceSummary) -> str:
    lines = [
        f"# {summary.month_label} 薪酬系统验收摘要",
        "",
        f"生成时间：{summary.generated_at}",
        "",
        "## 各表对账结论",
        "",
        "| 表 | 结论 | 未通过岗位 | 不一致单元格 |",
        "|----|------|------------|--------------|",
    ]
    for snap in summary.anchors:
        if not snap.has_output:
            verdict = "未跑批"
        elif snap.overall_passed:
            verdict = "通过"
        else:
            verdict = "未通过"
        lines.append(
            f"| {snap.label} | {verdict} | {snap.failed_roles} | {snap.mismatch_cells} |"
        )

    if summary.failed_role_details:
        lines.extend(["", "## 未通过岗位明细", ""])
        for item in summary.failed_role_details:
            lines.append(
                f"- **{item['表']} / {item['岗位']}**："
                f"{item['不一致单元格']} 处不一致，缺失 {item['缺失行']} 行"
            )
    else:
        lines.extend(["", "## 未通过岗位明细", "", "（无）"])

    return "\n".join(lines)
