"""非一线岗位判定 — 管理区块与支持部门区块。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal

import yaml

from salary_pipeline.data_ingestion.data_loader import normalize_name
from salary_pipeline.paths import CONFIG_DIR

NonFrontlineTier = Literal["management", "support"]

NON_FRONTLINE_POSITION_COL = "岗位绩效"
NON_FRONTLINE_PERFORMANCE_COL = "业绩绩效"

# Legacy flat mapping (management only); prefer tier config in YAML.
HUB_TO_SEMANTIC = {
    "整车绩效": NON_FRONTLINE_POSITION_COL,
    "加装绩效": NON_FRONTLINE_PERFORMANCE_COL,
}

ALL_SEMANTIC_COLUMNS = [
    "售后总产值",
    "配件外销",
    "售后产值",
    "出库",
    "入库",
    "台次",
    "提成系数",
    "提成系数2",
    NON_FRONTLINE_POSITION_COL,
    NON_FRONTLINE_PERFORMANCE_COL,
    "新能源专项",
    "业绩绩效1",
    "业绩绩效2",
]


@lru_cache(maxsize=1)
def load_non_frontline_config(config_dir: Path | None = None) -> dict[str, Any]:
    path = (config_dir or CONFIG_DIR) / "non_frontline_roles.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _norm(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and value != value):
        return None
    return normalize_name(value)


def _tier_block(cfg: dict[str, Any], tier: NonFrontlineTier) -> dict[str, Any]:
    block = cfg.get(tier)
    if isinstance(block, dict):
        return block
    if tier == "management" and "shops" in cfg:
        return {
            "shops": cfg.get("shops") or (),
            "role_patterns": cfg.get("role_patterns") or (),
            "column_mapping": cfg.get("column_mapping") or HUB_TO_SEMANTIC,
        }
    return {}


def is_management_non_frontline_row(
    shop: Any,
    role: Any,
    *,
    config: dict[str, Any] | None = None,
) -> bool:
    """销售管理部 / 事业部 / 总经办等管理区块。"""
    cfg = config or load_non_frontline_config()
    block = _tier_block(cfg, "management")
    shop_n = _norm(shop) or ""
    role_n = _norm(role) or ""

    allowed_shops = frozenset(block.get("shops") or ())
    if shop_n in allowed_shops:
        return True

    for pattern in block.get("role_patterns") or ():
        if pattern and pattern in role_n:
            if "销售总监" in role_n and shop_n and shop_n not in allowed_shops:
                return False
            return True

    return False


def is_support_non_frontline_row(
    shop: Any,
    role: Any = None,
    *,
    config: dict[str, Any] | None = None,
) -> bool:
    """财务部 / 市场部 / 物流等支持部门区块。"""
    cfg = config or load_non_frontline_config()
    block = _tier_block(cfg, "support")
    shop_n = _norm(shop) or ""
    return shop_n in frozenset(block.get("shops") or ())


def non_frontline_tier(
    shop: Any,
    role: Any,
    *,
    config: dict[str, Any] | None = None,
) -> NonFrontlineTier | None:
    """Return tier for row, or None when frontline."""
    cfg = config or load_non_frontline_config()
    if is_management_non_frontline_row(shop, role, config=cfg):
        return "management"
    if is_support_non_frontline_row(shop, role, config=cfg):
        return "support"
    return None


def is_non_frontline_row(
    shop: Any,
    role: Any,
    *,
    config: dict[str, Any] | None = None,
) -> bool:
    """True for any non-frontline tier (management or support)."""
    return non_frontline_tier(shop, role, config=config) is not None


def column_mapping_for_tier(
    tier: NonFrontlineTier,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, str]:
    cfg = config or load_non_frontline_config()
    block = _tier_block(cfg, tier)
    mapping = block.get("column_mapping") or {}
    return {str(k): str(v) for k, v in mapping.items()}


def all_semantic_columns(*, config: dict[str, Any] | None = None) -> list[str]:
    """Canonical display order for semantic columns present in config."""
    cfg = config or load_non_frontline_config()
    defined: set[str] = set()
    for tier in ("management", "support"):
        defined.update(column_mapping_for_tier(tier, config=cfg).values())
    return [col for col in ALL_SEMANTIC_COLUMNS if col in defined]


def highlight_column_for_row(
    shop: Any,
    role: Any,
    column: str,
    *,
    config: dict[str, Any] | None = None,
) -> str:
    """Map a golden physical column to the exported display column for highlighting."""
    cfg = config or load_non_frontline_config()
    tier = non_frontline_tier(shop, role, config=cfg)
    if tier is None:
        return column
    mapping = column_mapping_for_tier(tier, config=cfg)
    return mapping.get(column, column)


def parity_compare_columns(
    shop: Any,
    role: Any,
    column: str,
    *,
    config: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Return (golden_column, computed_column) for parity on migrated non-frontline rows."""
    cfg = config or load_non_frontline_config()
    tier = non_frontline_tier(shop, role, config=cfg)
    if tier is None:
        return column, column
    mapping = column_mapping_for_tier(tier, config=cfg)
    if column in mapping:
        return column, mapping[column]
    return column, column


def expand_highlight_columns(
    columns: Iterable[str],
    *,
    config: dict[str, Any] | None = None,
) -> set[str]:
    """Include both physical hub columns and semantic targets for highlight clearing."""
    expanded = set(columns)
    cfg = config or load_non_frontline_config()
    for tier in ("management", "support"):
        mapping = column_mapping_for_tier(tier, config=cfg)  # type: ignore[arg-type]
        for physical, semantic in mapping.items():
            if physical in expanded:
                expanded.add(semantic)
            if semantic in expanded:
                expanded.add(physical)
    return expanded
