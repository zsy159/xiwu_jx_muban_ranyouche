"""直营店内勤岗位族 — Hub W–AI（门店块×BA）+ 整车完成考核（店面台次×20）。"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import pandas as pd
import yaml

from salary_pipeline.calculators.store_clerk.store_block import store_block_actual_sales
from salary_pipeline.config.hub_performance_loader import load_hub_performance_config
from salary_pipeline.config.hub_performance_match import row_matches_family
from salary_pipeline.data_ingestion.data_loader import build_workbook_loader
from salary_pipeline.modules.base import (
    SUMMARY_KEY_COLUMNS,
    BaseCommissionModule,
    ModuleResult,
)
from salary_pipeline.paths import CONFIG_DIR
from salary_pipeline.pipelines.hub_rule_engine import HubRuleEngine

logger = logging.getLogger(__name__)

FAMILY_ID = "内勤"
HUB_COLUMN_AK = "整车完成考核"
_ROLES_PATH = CONFIG_DIR / "store_clerk_roles.yaml"


@lru_cache(maxsize=1)
def _load_store_clerk_roles() -> dict[str, Any]:
    with _ROLES_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


class StoreClerkPerformanceModule(BaseCommissionModule):
    """
    形态 C：computed 绩效整理表 + HubRuleEngine（store_ba 模板）写 W–AI；
    整车完成考核 AK = 同店块实际销量小计 × ak_per_unit_sales（默认 20）。
    """

    name = "store_clerk_performance"
    roles = ["内勤", "出纳+内勤"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        hub_cfg = load_hub_performance_config()
        family = hub_cfg.get("role_families", {}).get(FAMILY_ID, {})
        match = family.get("match", {})

        skeleton = context.get("summary_skeleton")
        perf_frame = context.get("computed_perf_frame")
        if skeleton is None or skeleton.empty:
            logger.warning("%s: empty summary_skeleton", self.name)
            return ModuleResult(
                module_name=self.name,
                roles=self.roles,
                metrics=pd.DataFrame(columns=SUMMARY_KEY_COLUMNS),
                metadata={"status": "no_skeleton"},
            )
        if perf_frame is None or perf_frame.empty:
            logger.warning("%s: missing computed_perf_frame", self.name)
            return ModuleResult(
                module_name=self.name,
                roles=self.roles,
                metrics=pd.DataFrame(columns=SUMMARY_KEY_COLUMNS),
                metadata={"status": "no_perf_frame"},
            )

        clerk_cfg = _load_store_clerk_roles()
        ak_names = frozenset(clerk_cfg.get("ak_eligible_names") or [])
        ak_rate = float(clerk_cfg.get("ak_per_unit_sales", 20))

        loader = build_workbook_loader(context)
        engine = HubRuleEngine()
        rule_family = engine.role_families.get(FAMILY_ID, {})
        hub_cols = list(family.get("hub_columns") or [])

        rows: list[dict[str, Any]] = []
        for _, person in skeleton.iterrows():
            if not row_matches_family(person, match):
                continue
            name = str(person["姓名"])
            store = str(person.get("店别") or "")
            rate = person.get("销量完成率")
            h_rate = float(rate) if pd.notna(rate) else 0.0
            hub_metrics = engine.compute_row(
                name=name,
                store=store or None,
                h_rate=h_rate,
                perf_frame=perf_frame,
                family_cfg=rule_family,
                loader=loader,
            )
            row_data: dict[str, Any] = {
                "店别": person["店别"],
                "职务": person["职务"],
                "姓名": name,
            }
            for col in hub_cols:
                if col in hub_metrics:
                    row_data[col] = hub_metrics[col]
            if name in ak_names and HUB_COLUMN_AK in hub_cols:
                block_sales = store_block_actual_sales(skeleton, store)
                row_data[HUB_COLUMN_AK] = block_sales * ak_rate
            rows.append(row_data)

        metric_cols = sorted(
            {c for row in rows for c in row if c not in SUMMARY_KEY_COLUMNS}
        )
        metrics = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=[*SUMMARY_KEY_COLUMNS, *metric_cols])
        )
        logger.info("%s: matched=%s ak_eligible=%s", self.name, len(metrics), len(ak_names))
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=metrics,
            metadata={
                "family_id": FAMILY_ID,
                "algorithm": "hub_rule_engine",
                "rows": len(metrics),
                "ak_per_unit_sales": ak_rate,
            },
        )
