from __future__ import annotations

import numpy as np
import pandas as pd


def lookup_match_index(
    lookup_keys: pd.Series,
    table_keys: pd.Series,
    table_values: pd.Series,
    *,
    default: float = 0.0,
) -> pd.Series:
    """Excel IFERROR(INDEX(values, MATCH(key, keys, 0)), default)."""
    return lookup_match_index_series(
        lookup_keys,
        table_keys,
        table_values,
        default=default,
        coerce="numeric",
    )


def lookup_match_index_series(
    lookup_keys: pd.Series,
    table_keys: pd.Series,
    table_values: pd.Series,
    *,
    default: object = 0.0,
    coerce: str = "numeric",
) -> pd.Series:
    """INDEX/MATCH with numeric or datetime values."""
    if coerce == "datetime":
        values = pd.to_datetime(table_values, errors="coerce")
    else:
        values = pd.to_numeric(table_values, errors="coerce")

    frame = pd.DataFrame(
        {
            "key": table_keys.map(_normalize_key),
            "value": values,
        }
    ).dropna(subset=["key"])
    if frame.empty:
        return pd.Series(default, index=lookup_keys.index)

    indexed = frame.drop_duplicates(subset=["key"], keep="last").set_index("key")["value"]
    keys = lookup_keys.map(_normalize_key)

    def _resolve(key: str | None) -> object:
        if not key or key not in indexed.index:
            return default
        val = indexed[key]
        if coerce == "numeric" and pd.isna(val):
            return default
        return val

    return keys.map(_resolve)


def sumifs_by_keys(
    source: pd.DataFrame,
    value_col: str,
    criteria: list[tuple[str, object]],
) -> float:
    """
    Excel SUMIFS(value_range, crit_range1, crit1, ...).

    criteria items are (column_name, expected_value). Use callable for ``>0`` style.
    """
    frame = source.copy()
    for col, expected in criteria:
        series = frame[col]
        if callable(expected):
            frame = frame[expected(series)]
        else:
            frame = frame[series.map(_normalize_key) == _normalize_key(expected)]
    if frame.empty:
        return 0.0
    return float(pd.to_numeric(frame[value_col], errors="coerce").sum(min_count=1))


def if_ladder(
    conditions: list[pd.Series | bool],
    choices: list[pd.Series | float],
    default: pd.Series | float = 0.0,
) -> pd.Series:
    """Excel nested IF / IFS via np.select."""
    if not conditions:
        return pd.Series(default)
    cond_arrays = [
        c.values if isinstance(c, pd.Series) else np.array([bool(c)])
        for c in conditions
    ]
    choice_arrays = [
        ch.values if isinstance(ch, pd.Series) else np.array([ch])
        for ch in choices
    ]
    default_array = default.values if isinstance(default, pd.Series) else np.array([default])
    index = choices[0].index if isinstance(choices[0], pd.Series) else None
    result = np.select(cond_arrays, choice_arrays, default=default_array)
    return pd.Series(result, index=index, dtype=float)


def _normalize_key(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None
