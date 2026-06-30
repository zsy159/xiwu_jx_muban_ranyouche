"""Extract formula topology from uploaded sales workbook."""

from __future__ import annotations

import json
from pathlib import Path

from salary_pipeline.paths import PROJECT_ROOT, resolve_project_path, topology_month_dir
from salary_pipeline.pipelines.run_cache import file_fingerprint

_TOPOLOGY_SOURCE_SUFFIX = ".workbook.fp"


def extract_sales_topology(
    workbook_path: Path,
    month_id: str,
    *,
    password: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    """
    Run extract_workbook_topology on the sales workbook; write JSON under
    data/topology/<month>/ (or output_dir when staging).
    """
    from scripts.extract_formula_topology import extract_workbook_topology

    out_dir = output_dir or topology_month_dir(month_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{workbook_path.stem}.topology.json"

    topology = extract_workbook_topology(workbook_path, password)
    out_path.write_text(
        json.dumps(topology, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    record_topology_workbook_fingerprint(workbook_path, out_path)
    rel = out_path.relative_to(PROJECT_ROOT)
    return Path(str(rel))


def topology_source_fingerprint_path(topology_path: Path) -> Path:
    return topology_path.with_name(topology_path.name + _TOPOLOGY_SOURCE_SUFFIX)


def record_topology_workbook_fingerprint(
    workbook_path: Path,
    topology_path: Path,
) -> None:
    fp_path = topology_source_fingerprint_path(topology_path)
    fp_path.write_text(file_fingerprint(workbook_path), encoding="utf-8")


def topology_is_current(workbook_path: Path, topology_rel: str | Path) -> bool:
    """True when topology JSON exists and matches the consolidated workbook."""
    topo_path = resolve_project_path(topology_rel)
    if not topo_path.exists():
        return False
    fp_path = topology_source_fingerprint_path(topo_path)
    if not fp_path.exists():
        return False
    stored = fp_path.read_text(encoding="utf-8").strip()
    return stored == file_fingerprint(workbook_path)
