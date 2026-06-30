from __future__ import annotations

from typing import Any

from salary_pipeline.observability.loaders import load_observability_config


def get_golden_bootstrap_view() -> dict[str, Any]:
    obs = load_observability_config()
    gb = obs.get("golden_bootstrap", {})
    return {
        "intro": gb.get("finance_intro", "").strip(),
        "sections": gb.get("sections", []),
    }


def get_hub_performance_columns() -> list[str]:
    obs = load_observability_config()
    return list(obs.get("hub_performance_columns", []))
