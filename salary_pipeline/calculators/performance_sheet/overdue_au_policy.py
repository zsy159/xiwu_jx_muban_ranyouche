"""Parse 绩效整理表 AU 阈值策略 from topology (per-VIN min_days / bonus)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.data_ingestion.performance_sheet_golden import (
    DATA_START_ROW,
    _normalize_vin,
)

DEFAULT_AU_POLICY = (180, 500)
_AU_FORMULA_RE = re.compile(r">=(\d+),(\d+)")


def parse_au_formula(formula: str | None) -> tuple[int, int] | None:
    match = _AU_FORMULA_RE.search(formula or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


@lru_cache(maxsize=4)
def load_au_policy_by_vin(
    workbook_path: str,
    topology_path: str,
    perf_sheet: str = "绩效整理表",
    policy_workbook_path: str | None = None,
) -> dict[str, tuple[int, int]]:
    """
    Map VIN → (min_inventory_days, bonus_amount) from golden AU formulas.

    Unknown VINs fall back to ``DEFAULT_AU_POLICY`` (IF(E>=180,500,0)).
    """
    topology = json.loads(Path(topology_path).read_text(encoding="utf-8"))
    cells = topology.get("cells") or {}

    golden_o = None
    for candidate_path in (workbook_path, policy_workbook_path):
        if not candidate_path:
            continue
        try:
            path = Path(candidate_path)
            if not path.is_file():
                continue
            loader = WorkbookLoader(path)
            golden_o = loader.read_sheet_columns(
                perf_sheet, {"O": "O"}, label="au policy"
            )
            break
        except (ValueError, FileNotFoundError, OSError):
            continue
    if golden_o is None:
        return {}

    golden_o = golden_o.iloc[DATA_START_ROW - 1 :].reset_index(drop=True)

    policy: dict[str, tuple[int, int]] = {}
    for offset, vin_raw in enumerate(golden_o["O"]):
        vin = _normalize_vin(vin_raw)
        if not vin:
            continue
        row = DATA_START_ROW + offset
        formula = cells.get(f"{perf_sheet}!AU{row}", {}).get("formula", "")
        parsed = parse_au_formula(formula)
        if parsed:
            policy[vin] = parsed
    return policy


def lookup_au_policy(
    vin: object,
    policy_by_vin: dict[str, tuple[int, int]],
) -> tuple[int, int]:
    key = _normalize_vin(vin)
    if not key:
        return DEFAULT_AU_POLICY
    return policy_by_vin.get(key, DEFAULT_AU_POLICY)
