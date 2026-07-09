"""Canonical calculation rules (2026-05 template topology) for onboard-month."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from salary_pipeline.paths import CONFIG_DIR, resolve_project_path

_DEFAULT_RULES_PATH = CONFIG_DIR / "default_rules.yaml"


def load_default_rules() -> dict[str, Any]:
    with _DEFAULT_RULES_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def canonical_topology() -> dict[str, str]:
    """Return sales / rules / aftersales topology paths from default_rules.yaml."""
    cfg = load_default_rules()
    topo = cfg.get("topology") or {}
    return {
        "sales": str(topo["sales"]),
        "rules": str(topo["rules"]),
        "aftersales": str(topo["aftersales"]),
    }


def canonical_month_label() -> tuple[str, str]:
    cfg = load_default_rules()
    month = str(cfg.get("canonical_month", "2026-05"))
    label = str(cfg.get("label", f"{month}样板（系统固化规则）"))
    return month, label


def validate_topology_paths(topo: dict[str, str]) -> list[str]:
    """Return human-readable errors for missing topology files."""
    errors: list[str] = []
    for name, rel in topo.items():
        if not rel:
            errors.append(f"default_rules.yaml 缺少 topology.{name}")
            continue
        path = resolve_project_path(rel)
        if not path.exists():
            errors.append(f"固化拓扑文件不存在: {rel}")
    return errors


def resolve_existing_canonical_topology() -> tuple[dict[str, str], list[str]]:
    topo = canonical_topology()
    return topo, validate_topology_paths(topo)
