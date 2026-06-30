from __future__ import annotations

import numpy as np
import pandas as pd


def sumif_by_key(
    source: pd.DataFrame,
    key_col: str,
    value_col: str,
    criteria: pd.Series | str,
) -> float | pd.Series:
    """
    Excel SUMIF(range_key, criteria, range_value) over a DataFrame.

  When *criteria* is a scalar, returns a single sum.
  When *criteria* is a Series, returns a Series aligned to its index.
    """
    frame = source[[key_col, value_col]].copy()
    frame[key_col] = frame[key_col].map(_normalize_key)
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    frame = frame.dropna(subset=[key_col])

    totals = frame.groupby(key_col, dropna=True)[value_col].sum(min_count=1)
    totals = totals.fillna(0.0)

    if isinstance(criteria, str):
        return float(totals.get(_normalize_key(criteria), 0.0))

    keys = criteria.map(_normalize_key)
    return keys.map(lambda k: float(totals.get(k, 0.0)) if k else 0.0)


def ratio_with_cap(
    numerator: pd.Series | float,
    denominator: pd.Series | float,
    cap: float = 1.2,
) -> pd.Series | float:
    """Excel: IF(den<>0, IF(num/den>cap, cap, num/den), 0)."""
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")

    if isinstance(num, pd.Series) or isinstance(den, pd.Series):
        num_s = num if isinstance(num, pd.Series) else pd.Series([num])
        den_s = den if isinstance(den, pd.Series) else pd.Series([den])
        out = pd.Series(0.0, index=num_s.index, dtype=float)
        mask = den_s.notna() & (den_s != 0)
        ratio = num_s[mask] / den_s[mask]
        out.loc[mask] = np.minimum(ratio, cap)
        return out

    if den is None or pd.isna(den) or den == 0:
        return 0.0
    return float(min(num / den, cap))


def _normalize_key(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None
