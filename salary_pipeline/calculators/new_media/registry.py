"""新媒体岗位模板登记与统一计算入口。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from salary_pipeline.calculators.new_media.formulas import (
    compute_live_anchor,
    compute_manual,
    compute_ops_manager,
    compute_video_ops,
)
from salary_pipeline.calculators.new_media.types import (
    LiveAnchorInput,
    ManualPerformanceInput,
    MetricPair,
    OpsManagerInput,
    PerformanceResult,
    VideoOpsInput,
)
from salary_pipeline.paths import CONFIG_DIR

_REGISTRY_PATH = CONFIG_DIR / "new_media_roles.yaml"


def load_role_registry(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or _REGISTRY_PATH
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def list_roles(registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    reg = registry or load_role_registry()
    return list(reg.get("roles", []))


def get_role(name: str, registry: dict[str, Any] | None = None) -> dict[str, Any] | None:
    for role in list_roles(registry):
        if role["name"] == name:
            return role
    return None


def default_input_for_role(role: dict[str, Any]) -> Any:
    template = role["template"]
    defaults = role.get("defaults", {})
    if template == "live_anchor":
        return LiveAnchorInput(
            live_sessions=_pair(defaults, "live_sessions"),
            leads=_pair(defaults, "leads"),
            fans=_pair(defaults, "fans"),
            videos=_pair(defaults, "videos"),
            kpi_base=float(defaults.get("kpi_base", 7000)),
            score_weights=tuple(defaults.get("score_weights", [40, 40, 10, 10])),
            terminal_unit_rate=float(defaults.get("terminal_unit_rate", 50)),
            lead_excess_unit_rate=float(defaults.get("lead_excess_unit_rate", 10)),
            session_excess_unit_rate=float(defaults.get("session_excess_unit_rate", 100)),
            track_session_excess=bool(defaults.get("track_session_excess", False)),
        )
    if template == "video_ops":
        return VideoOpsInput(
            videos=_pair(defaults, "videos"),
            play_count=_pair(defaults, "play_count"),
            short_video_fans=_pair(defaults, "short_video_fans"),
            xiaohongshu=_pair(defaults, "xiaohongshu"),
            kpi_base=float(defaults.get("kpi_base", 6000)),
            score_weights=tuple(defaults.get("score_weights", [40, 20, 20, 20])),
            terminal_unit_rate=float(defaults.get("terminal_unit_rate", 20)),
            quality_video_unit_rate=float(defaults.get("quality_video_unit_rate", 50)),
            excess_video_unit_rate=float(defaults.get("excess_video_unit_rate", 50)),
        )
    if template == "ops_manager":
        return OpsManagerInput(
            live_sessions=_pair(defaults, "live_sessions"),
            video_creations=_pair(defaults, "video_creations"),
            leads=_pair(defaults, "leads"),
            store_visits=_pair(defaults, "store_visits"),
            kpi_base=float(defaults.get("kpi_base", 8000)),
            score_weights=tuple(defaults.get("score_weights", [25, 25, 25, 25])),
            terminal_unit_rate=float(defaults.get("terminal_unit_rate", 40)),
        )
    if template == "manual":
        return ManualPerformanceInput(
            performance_salary=float(defaults.get("performance_salary", 0)),
        )
    raise ValueError(f"unknown template: {template}")


def _pair(defaults: dict[str, Any], key: str) -> MetricPair:
    raw = defaults.get(key, {})
    return MetricPair(
        target=float(raw.get("target", 0)),
        actual=float(raw.get("actual", 0)),
    )


def compute_for_role(role_name: str, inputs: Any) -> PerformanceResult:
    role = get_role(role_name)
    if role is None:
        raise KeyError(f"role not found: {role_name}")
    template = role["template"]
    if template == "live_anchor":
        assert isinstance(inputs, LiveAnchorInput)
        return compute_live_anchor(inputs)
    if template == "video_ops":
        assert isinstance(inputs, VideoOpsInput)
        return compute_video_ops(inputs)
    if template == "ops_manager":
        assert isinstance(inputs, OpsManagerInput)
        return compute_ops_manager(inputs)
    if template == "manual":
        assert isinstance(inputs, ManualPerformanceInput)
        return compute_manual(inputs)
    raise ValueError(f"unknown template: {template}")


def inputs_to_dict(inputs: Any) -> dict[str, Any]:
    return asdict(inputs)
