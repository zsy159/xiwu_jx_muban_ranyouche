"""声明式 Hub F–P 指标列规则引擎（取代 HubFormulaEngine 拓扑逐格回放）。

设计对比 ``HubFormulaEngine``：
- 不解析/回放 Excel 拓扑公式，也不依赖「金标准行号」与生产数据行号对齐
- 按 config/hub_metrics_rules.yaml 的固定规则计算（SUMIF/比值/分组封顶），
  同列的店别差异（如 H 列完成率封顶）以显式分组（cap_overrides）表达，
  不做按行号推断
- 适用范围为「提成汇总」全部人员行，按姓名匹配底层表；未匹配 = 0
"""

from __future__ import annotations

import logging
import operator
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name
from salary_pipeline.ops.basic import sumif_by_key
from salary_pipeline.ops.lookup import lookup_match_index
from salary_pipeline.paths import CONFIG_DIR

logger = logging.getLogger(__name__)

HUB_METRICS_RULES_PATH = CONFIG_DIR / "hub_metrics_rules.yaml"

_FILTER_OPS = {
    "gt": operator.gt,
    "ge": operator.ge,
    "lt": operator.lt,
    "le": operator.le,
    "eq": operator.eq,
    "ne": operator.ne,
}


@lru_cache(maxsize=1)
def load_hub_metrics_rules(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or HUB_METRICS_RULES_PATH
    with cfg_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _empty_perf_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["P", "K", "S", "BG", "BI", "AB", "AC"])


def _empty_task_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["姓名", "考核量", "实际销量", "集客达成率"])


def _eval_denominator_expr(expr: str, frame: pd.DataFrame) -> pd.Series:
    """极简表达式求值：仅支持 ``<列名>`` 或 ``<列名> * <常数>``。"""
    text = expr.strip()
    if "*" in text:
        col, const = text.split("*", 1)
        series = pd.to_numeric(frame[col.strip()], errors="coerce")
        return series * float(const.strip())
    return pd.to_numeric(frame[text], errors="coerce")


class HubMetricsRuleEngine:
    """按 hub_metrics_rules.yaml 声明式计算 提成汇总 F–P 指标列。"""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or load_hub_metrics_rules()
        self.columns: list[dict[str, Any]] = self.config.get("columns", [])

    def apply(
        self,
        summary: pd.DataFrame,
        *,
        computed_perf_frame: pd.DataFrame | None,
        loader: WorkbookLoader | None,
    ) -> pd.DataFrame:
        if summary.empty:
            return summary

        out = summary.copy()
        names = out["姓名"].map(normalize_name)
        task_frame = self._load_task_frame(loader)
        perf_frame = (
            computed_perf_frame
            if computed_perf_frame is not None and not computed_perf_frame.empty
            else _empty_perf_frame()
        )

        for spec in self.columns:
            hub_col = spec["hub_column"]
            op = spec["op"]
            if op == "sumif":
                out[hub_col] = self._op_sumif(spec, names, task_frame, perf_frame)
            elif op == "lookup_first":
                out[hub_col] = self._op_lookup_first(spec, names, task_frame, perf_frame)
            elif op == "ratio_with_cap_group":
                out[hub_col] = self._op_ratio_with_cap_group(spec, out)
            elif op == "ratio":
                out[hub_col] = self._op_ratio(spec, out)
            elif op == "filtered_ratio":
                out[hub_col] = self._op_filtered_ratio(spec, names, perf_frame)
            else:
                raise ValueError(f"Unknown hub_metrics_rules op: {op!r} ({hub_col})")

        logger.info(
            "Hub metrics rule engine: computed %s columns for %s rows",
            len(self.columns),
            len(out),
        )
        return out

    def _load_task_frame(self, loader: WorkbookLoader | None) -> pd.DataFrame:
        if loader is None:
            return _empty_task_frame()
        try:
            if not loader.has_sheet("销售任务及完成率"):
                return _empty_task_frame()
            return loader.read_sales_task_sheet()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("hub_metrics_rule_engine: read task sheet failed: %s", exc)
            return _empty_task_frame()

    def _frame_for_sheet(
        self,
        sheet: str,
        task_frame: pd.DataFrame,
        perf_frame: pd.DataFrame,
    ) -> pd.DataFrame:
        if sheet == "绩效整理表":
            return perf_frame
        if sheet == "销售任务及完成率":
            return task_frame
        raise ValueError(f"hub_metrics_rules: unsupported source_sheet {sheet!r}")

    def _op_sumif(
        self,
        spec: dict[str, Any],
        names: pd.Series,
        task_frame: pd.DataFrame,
        perf_frame: pd.DataFrame,
    ) -> pd.Series:
        frame = self._frame_for_sheet(spec["source_sheet"], task_frame, perf_frame)
        key_col, value_col = spec["key_col"], spec["value_col"]
        if key_col not in frame.columns or value_col not in frame.columns:
            return pd.Series(0.0, index=names.index)
        result = sumif_by_key(frame, key_col, value_col, names)
        return result if isinstance(result, pd.Series) else pd.Series(result, index=names.index)

    def _op_lookup_first(
        self,
        spec: dict[str, Any],
        names: pd.Series,
        task_frame: pd.DataFrame,
        perf_frame: pd.DataFrame,
    ) -> pd.Series:
        frame = self._frame_for_sheet(spec["source_sheet"], task_frame, perf_frame)
        key_col, value_col = spec["key_col"], spec["value_col"]
        if key_col not in frame.columns or value_col not in frame.columns:
            return pd.Series(0.0, index=names.index)
        return lookup_match_index(names, frame[key_col], frame[value_col])

    def _op_ratio_with_cap_group(self, spec: dict[str, Any], out: pd.DataFrame) -> pd.Series:
        num = pd.to_numeric(out[spec["numerator"]], errors="coerce")
        den = pd.to_numeric(out[spec["denominator"]], errors="coerce")
        cap = pd.Series(float(spec["default_cap"]), index=out.index, dtype=float)
        group_col = spec["group_by"]
        for override in spec.get("cap_overrides", []):
            values = {str(v) for v in override.get(group_col, [])}
            if not values or group_col not in out.columns:
                continue
            mask = out[group_col].astype(str).isin(values)
            cap.loc[mask] = float(override["cap"])

        result = pd.Series(0.0, index=out.index, dtype=float)
        mask = den.notna() & (den != 0)
        ratio = num[mask] / den[mask]
        result.loc[mask] = np.minimum(ratio, cap[mask])
        return result

    def _op_ratio(self, spec: dict[str, Any], out: pd.DataFrame) -> pd.Series:
        num = pd.to_numeric(out[spec["numerator"]], errors="coerce")
        den = _eval_denominator_expr(spec["denominator_expr"], out)
        result = pd.Series(0.0, index=out.index, dtype=float)
        mask = den.notna() & (den != 0)
        result.loc[mask] = num[mask] / den[mask]
        return result

    def _op_filtered_ratio(
        self,
        spec: dict[str, Any],
        names: pd.Series,
        perf_frame: pd.DataFrame,
    ) -> pd.Series:
        key_col, value_col = spec["key_col"], spec["value_col"]
        filter_col = spec["filter_col"]
        if key_col not in perf_frame.columns or value_col not in perf_frame.columns:
            return pd.Series(0.0, index=names.index)
        cmp = _FILTER_OPS[spec.get("filter_op", "gt")]
        filter_series = pd.to_numeric(perf_frame.get(filter_col), errors="coerce")
        mask = cmp(filter_series, float(spec["filter_value"]))
        numer = sumif_by_key(perf_frame[mask], key_col, value_col, names)
        denom = sumif_by_key(perf_frame, key_col, value_col, names)
        numer = numer if isinstance(numer, pd.Series) else pd.Series(numer, index=names.index)
        denom = denom if isinstance(denom, pd.Series) else pd.Series(denom, index=names.index)
        result = pd.Series(0.0, index=names.index, dtype=float)
        nz = denom.notna() & (denom != 0)
        result.loc[nz] = numer[nz] / denom[nz]
        return result
