"""Load hub_performance.yaml role-family configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from salary_pipeline.paths import CONFIG_DIR


@lru_cache(maxsize=1)
def load_hub_performance_config(config_dir: Path | None = None) -> dict[str, Any]:
    path = (config_dir or CONFIG_DIR) / "hub_performance.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
