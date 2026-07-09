"""直营店块销量小计 — 供内勤「店面台次×系数」整车完成考核。"""

from __future__ import annotations

import pandas as pd

_SKIP_NAMES = frozenset({"空白", "0", "0.0", "小计"})
_SKIP_TITLES = frozenset({"空白", "0", "小计"})


def store_block_actual_sales(summary: pd.DataFrame, store: str) -> float:
    """Sum 实际销量 within a forward-filled 店别 block (excludes占位行)."""
    if summary.empty or "店别" not in summary.columns:
        return 0.0
    stores = summary["店别"].ffill().astype(str)
    mask = stores == str(store).strip()
    total = 0.0
    for _, row in summary[mask].iterrows():
        name = str(row.get("姓名", "")).strip()
        title = str(row.get("职务", "")).strip()
        if name in _SKIP_NAMES or title in _SKIP_TITLES:
            continue
        sales = row.get("实际销量")
        if pd.notna(sales):
            total += float(sales)
    return total
