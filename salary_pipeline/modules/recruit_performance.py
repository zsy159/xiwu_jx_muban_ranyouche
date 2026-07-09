"""招聘岗位族绩效 — 行政人事部写 Hub 保险绩效（Z）。"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from salary_pipeline.calculators.recruit.extract import lookup_role_performance
from salary_pipeline.calculators.recruit.registry import (
    hub_column_for_role,
    is_hub_linked,
    list_roles,
)
from salary_pipeline.config.hub_performance_loader import load_hub_performance_config
from salary_pipeline.config.hub_performance_match import row_matches_family
from salary_pipeline.data_ingestion.data_loader import build_workbook_loader
from salary_pipeline.data_ingestion.recruit_sheet import RECRUIT_SHEET
from salary_pipeline.modules.base import (
    SUMMARY_KEY_COLUMNS,
    BaseCommissionModule,
    ModuleResult,
)

logger = logging.getLogger(__name__)

FAMILY_ID = "招聘"
HUB_COLUMN = "保险绩效"
_ROLE_BY_NAME = {r["name"]: r for r in list_roles()}


class RecruitPerformanceModule(BaseCommissionModule):
    """
    形态 B：主账套「招聘」子表团队分配块 → 保险绩效。

    公式：个人提成 = 到岗数 × 单人招聘提成 × 分配比例
    Hub overlay 仅 hub_linked 三人（周小红 / 刘晓琴 / 何婷婷）。
    李玲在子表有分配行，不在提成汇总，仅观察台算薪。
    """

    name = "recruit_performance"
    roles = ["行政主管", "行政助理", "招聘专员"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        hub_cfg = load_hub_performance_config()
        family = hub_cfg.get("role_families", {}).get(FAMILY_ID, {})
        match = family.get("match", {})

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
        sheet = str(family.get("source", {}).get("sheet", RECRUIT_SHEET))
        sheet_available = loader.has_sheet(sheet)
        if not sheet_available:
            logger.warning(
                "%s: sheet %r missing; overlay leaves recruit columns empty",
                self.name,
                sheet,
            )

        rows: list[dict[str, Any]] = []
        for _, person in skeleton.iterrows():
            if not row_matches_family(person, match):
                continue
            name = str(person["姓名"])
            role = _ROLE_BY_NAME.get(name)
            if role is None or not is_hub_linked(role):
                continue

            hub_col = hub_column_for_role(role)
            perf = lookup_role_performance(loader, name) if sheet_available else 0.0
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
            "%s: matched=%s rules_sheet=%s source_rows=%s",
            self.name,
            len(metrics),
            family.get("rules_sheet", "销售提成标准"),
            len(rows),
        )
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=metrics,
            metadata={
                "family_id": FAMILY_ID,
                "rules_sheet": family.get("rules_sheet"),
                "algorithm": "team_allocation",
                "formula": "onboard_count * commission_per_hire * allocation_ratio",
                "source_sheet": sheet,
                "sheet_available": sheet_available,
                "rows": len(metrics),
                "hub_linked_only": True,
            },
        )
