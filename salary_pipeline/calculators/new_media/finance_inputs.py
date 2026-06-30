"""Load finance UI inputs saved from Streamlit 新媒体算薪 page."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from salary_pipeline.paths import resolve_project_path

logger = logging.getLogger(__name__)

INPUTS_FILENAME = "new_media_inputs.json"


def finance_inputs_path(month: str) -> Path:
    return resolve_project_path(f"output/{month}/inputs/{INPUTS_FILENAME}")


def load_finance_hub_overrides(month: str) -> dict[str, float]:
    """
    Return 姓名 → 整车绩效 from saved UI results, if present.
    Finance fills the form in 观察台 → saves JSON → pipeline prefers these values.
    """
    path = finance_inputs_path(month)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("cannot read finance inputs %s: %s", path, exc)
        return {}
    overrides: dict[str, float] = {}
    for name, entry in payload.items():
        if not isinstance(entry, dict):
            continue
        result = entry.get("result")
        if isinstance(result, dict) and "hub_vehicle_performance" in result:
            overrides[str(name)] = float(result["hub_vehicle_performance"])
    if overrides:
        logger.info("new_media finance overrides: %s names from %s", len(overrides), path)
    return overrides
