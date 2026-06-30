"""直营店经理岗位族绩效 — 销售经理写 Hub 整车完成考核（AK）。"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from salary_pipeline.calculators.direct_store_manager.extract import (
    lookup_role_performance,
)
from salary_pipeline.calculators.direct_store_manager.registry import (
    hub_column_for_role,
    list_roles,
)
from salary_pipeline.config.hub_performance_loader import load_hub_performance_config
from salary_pipeline.data_ingestion.data_loader import build_workbook_loader
from salary_pipeline.modules.base import (
    SUMMARY_KEY_COLUMNS,
    BaseCommissionModule,
    ModuleResult,
)

logger = logging.getLogger(__name__)

FAMILY_ID = "直营店经理"
HUB_COLUMN = "整车完成考核"
_ROLE_BY_NAME = {r["name"]: r for r in list_roles()}


class DirectStoreManagerPerformanceModule(BaseCommissionModule):
    """
    形态 B：主账套「直营店经理提成 (财务)」子表 R 列 → hub 整车完成考核。

    5 名直营店销售经理；钟涛为华阳 + 华阳领克双行合计。
    """

    name = "direct_store_manager_performance"
    roles = ["销售经理"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        hub_cfg = load_hub_performance_config()
        family = hub_cfg.get("role_families", {}).get(FAMILY_ID, {})

        skeleton = context.get("summary_skeleton")
        if skeleton is None or skeleton.empty:
            logger.warning("%s: empty summary_skeleton", self.name)
            return ModuleResult(
                module_name=self.name,
                roles=self.roles,
                metrics=pd.DataFrame(columns=[*SUMMARY_KEY_COLUMNS, HUB_COLUMN]),
                metadata={"status": "no_skeleton"},
            )

        loader = build_workbook_loader(context)
        rows: list[dict[str, Any]] = []
        for _, person in skeleton.iterrows():
            name = str(person["姓名"])
            role = _ROLE_BY_NAME.get(name)
            if role is None:
                continue

            hub_col = hub_column_for_role(role)
            perf = lookup_role_performance(loader, name)
            rows.append(
                {
                    "店别": person["店别"],
                    "职务": person["职务"],
                    "姓名": name,
                    hub_col: perf,
                }
            )

        metric_cols = sorted(
            {c for row in rows for c in row if c not in SUMMARY_KEY_COLUMNS}
        )
        metrics = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=[*SUMMARY_KEY_COLUMNS, *metric_cols])
        )
        logger.info(
            "%s: matched=%s rules_sheet=%s",
            self.name,
            len(metrics),
            family.get("rules_sheet", "直营店经理提成 (财务)"),
        )
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=metrics,
            metadata={
                "family_id": FAMILY_ID,
                "rules_sheet": family.get("rules_sheet"),
                "algorithm": "store_block_with_attach_row",
                "source_sheet": "直营店经理提成 (财务)",
                "rows": len(metrics),
            },
        )
