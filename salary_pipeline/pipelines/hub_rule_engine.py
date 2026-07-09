"""声明式 Hub W–AI 绩效列规则引擎（取代按行号回放 topology 公式）。

设计对比 ``HubFormulaEngine``：
- 不解析/回放 Excel 拓扑公式，也不依赖「金标准行号」与生产数据行号对齐
- 按 config/hub_column_rules.yaml 的岗位族声明（SUMIF/SUMIFS 来源列 + 乘数规则）计算
- 仅对已登记 ``columns`` 的岗位族生效（当前：销售顾问）；其余岗位族由各自独立模块
  或 HubFormulaEngine 拓扑回放兜底（见 hub_column_rules.yaml ``delegate`` 标注）
- 完成率来源：BA=销售任务及完成率!AG 按姓名匹配（``lookup_combined_completion_rate``，
  不做系统封顶）；H=当期 summary 行「销量完成率」列（F–P 计算结果，不读金标准）
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from salary_pipeline.config.hub_performance_match import row_matches_family
from salary_pipeline.data_ingestion.data_loader import (
    WorkbookLoader,
    lookup_combined_completion_rate,
    normalize_name,
)
from salary_pipeline.paths import CONFIG_DIR

logger = logging.getLogger(__name__)

HUB_COLUMN_RULES_PATH = CONFIG_DIR / "hub_column_rules.yaml"


@lru_cache(maxsize=1)
def load_hub_column_rules(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or HUB_COLUMN_RULES_PATH
    with cfg_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def resolve_sales_advisor_template(
    *,
    name: str,
    store: str | None,
    family_cfg: dict[str, Any],
) -> tuple[str, float]:
    """按姓名覆盖优先、其次店别，返回 (template, insurance_add_const)。"""
    selector = family_cfg.get("template_selector", {}) or {}
    overrides = selector.get("name_overrides", {}) or {}
    override = overrides.get(str(name).strip())
    if override:
        return (
            str(override.get("template", "insurance_add")),
            float(override.get("insurance_add_const", 0.0)),
        )

    store_ba_shops = {str(s) for s in selector.get("store_ba_shops", [])}
    if store and str(store).strip() in store_ba_shops:
        return "store_ba", 0.0

    default_template = str(
        selector.get("default_template")
        or selector.get("fallback_template")
        or "personal_h"
    )
    return default_template, 0.0


def _sum_perf_columns(
    perf: pd.DataFrame,
    name_col: str,
    value_cols: list[str],
    advisor_name: str,
) -> float:
    if perf.empty or name_col not in perf.columns:
        return 0.0
    key = normalize_name(advisor_name)
    mask = perf[name_col].astype(str).map(normalize_name) == key
    total = 0.0
    for col in value_cols:
        if col not in perf.columns:
            continue
        total += float(pd.to_numeric(perf.loc[mask, col], errors="coerce").fillna(0).sum())
    return total


class HubRuleEngine:
    """按 hub_column_rules.yaml 声明式计算 提成汇总 W–AI 绩效列。"""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or load_hub_column_rules()
        self.role_families: dict[str, Any] = self.config.get("role_families", {})

    def _match_family(self, row: pd.Series) -> tuple[str, dict[str, Any]] | None:
        for family_id, family_cfg in self.role_families.items():
            match = family_cfg.get("match")
            if not match:
                continue
            if row_matches_family(row, match):
                return family_id, family_cfg
        return None

    def compute_row(
        self,
        *,
        name: str,
        store: str | None,
        h_rate: float,
        perf_frame: pd.DataFrame,
        family_cfg: dict[str, Any],
        loader: WorkbookLoader | None = None,
    ) -> dict[str, float]:
        """计算单个岗位族已登记 columns 的 Hub 值（供业务模块 overlay 调用）。"""
        columns = family_cfg.get("columns")
        if not columns:
            return {}
        name_col = family_cfg.get("perf_name_column", "P")

        template, insurance_add_const = resolve_sales_advisor_template(
            name=name, store=store, family_cfg=family_cfg
        )

        ba_rate: float | None = None
        if template == "store_ba":
            if loader is not None:
                ba_rate = lookup_combined_completion_rate(loader, name)
            if ba_rate is None:
                ba_rate = h_rate

        metrics: dict[str, float] = {}
        for spec in columns:
            hub_col = spec["hub_column"]
            base = _sum_perf_columns(perf_frame, name_col, list(spec["perf_columns"]), name)
            multiplier = spec.get("multiplier", "none")
            if multiplier == "none":
                rate = 1.0
            elif multiplier == "H":
                rate = h_rate
            elif multiplier == "template":
                rate = ba_rate if template == "store_ba" else h_rate
            else:
                rate = 1.0
            value = base * rate
            if spec.get("allow_add_const") and template == "insurance_add":
                value += insurance_add_const
            metrics[hub_col] = value
        return metrics

    def apply(
        self,
        summary: pd.DataFrame,
        *,
        computed_perf_frame: pd.DataFrame,
        loader: WorkbookLoader | None = None,
    ) -> pd.DataFrame:
        """按已登记岗位族规则填充 summary 的 Hub W–AI 列（未登记族保持不变）。"""
        if summary.empty:
            return summary
        out = summary.copy()
        all_hub_cols = {
            col
            for family_cfg in self.role_families.values()
            for spec in (family_cfg.get("columns") or [])
            for col in [spec["hub_column"]]
        }
        for col in all_hub_cols:
            if col not in out.columns:
                out[col] = pd.NA

        computed = 0
        for idx, row in out.iterrows():
            matched = self._match_family(row)
            if matched is None:
                continue
            _family_id, family_cfg = matched
            if not family_cfg.get("columns"):
                continue
            name = str(row.get("姓名", ""))
            if not name or name == "空白":
                continue
            store = row.get("店别")
            rate = row.get("销量完成率")
            h_rate = float(rate) if pd.notna(rate) else 0.0
            metrics = self.compute_row(
                name=name,
                store=store,
                h_rate=h_rate,
                perf_frame=computed_perf_frame,
                family_cfg=family_cfg,
                loader=loader,
            )
            for col, value in metrics.items():
                out.at[idx, col] = value
            computed += 1

        logger.info("Hub rule engine: computed=%s rows", computed)
        return out
