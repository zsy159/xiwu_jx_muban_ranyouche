"""邀约专员岗位族绩效 — DCC 写 W 列，崇州直营写 AK 列。"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from salary_pipeline.calculators.invite_specialist.extract import lookup_role_performance
from salary_pipeline.calculators.invite_specialist.finance_inputs import (
    load_finance_hub_overrides,
)
from salary_pipeline.calculators.invite_specialist.registry import (
    get_role,
    hub_column_for_role,
    list_roles,
)
from salary_pipeline.config.hub_performance_loader import load_hub_performance_config
from salary_pipeline.data_ingestion.data_loader import build_workbook_loader, normalize_name
from salary_pipeline.data_ingestion.invite_specialist_sheet import (
    load_invite_specialist_frame,
    lookup_vehicle_performance,
)
from salary_pipeline.modules.base import (
    SUMMARY_KEY_COLUMNS,
    BaseCommissionModule,
    ModuleResult,
)

logger = logging.getLogger(__name__)

FAMILY_ID = "邀约专员"
HUB_COLUMN_DCC = "整车绩效"
HUB_COLUMN_CHONGZHOU = "整车完成考核"
ROLE_DCC = "DCC邀约专员"
ROLE_CHONGZHOU = "邀约专员"
STORE_CHONGZHOU = "崇州直营店"

_ROLE_BY_NAME = {r["name"]: r for r in list_roles()}


class InviteSpecialistPerformanceModule(BaseCommissionModule):
    """
    形态 B：主账套「邀约专员提成」子表计算。

    - DCC邀约专员：hub =SUMIF(邀约专员提成!C:C, 姓名, AF) → 整车绩效 W
    - 崇州邀约专员（杨婷）：子表 AD，hub 引用 AF15 → 整车完成考核 AK
    """

    name = "invite_specialist_performance"
    roles = [ROLE_DCC, ROLE_CHONGZHOU]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        hub_cfg = load_hub_performance_config()
        family = hub_cfg.get("role_families", {}).get(FAMILY_ID, {})

        skeleton = context.get("summary_skeleton")
        if skeleton is None or skeleton.empty:
            logger.warning("%s: empty summary_skeleton", self.name)
            return ModuleResult(
                module_name=self.name,
                roles=self.roles,
                metrics=pd.DataFrame(columns=[*SUMMARY_KEY_COLUMNS, HUB_COLUMN_DCC]),
                metadata={"status": "no_skeleton"},
            )

        loader = build_workbook_loader(context)
        source = load_invite_specialist_frame(loader)
        month = context.get("month_config", {}).get("month", "")
        finance_overrides = load_finance_hub_overrides(month) if month else {}

        rows: list[dict[str, Any]] = []
        for _, person in skeleton.iterrows():
            title = normalize_name(str(person["职务"]))
            store = str(person.get("店别") or "")
            name = str(person["姓名"])

            if title == normalize_name(ROLE_DCC):
                hub_col = HUB_COLUMN_DCC
            elif (
                title == normalize_name(ROLE_CHONGZHOU)
                and store == STORE_CHONGZHOU
                and name in _ROLE_BY_NAME
            ):
                hub_col = hub_column_for_role(_ROLE_BY_NAME[name])
            else:
                continue

            if name in finance_overrides:
                perf = finance_overrides[name]
            elif hub_col == HUB_COLUMN_DCC:
                perf = lookup_vehicle_performance(source, name)
            else:
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
            family.get("rules_sheet", "邀约专员提成"),
        )
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=metrics,
            metadata={
                "family_id": FAMILY_ID,
                "rules_sheet": family.get("rules_sheet"),
                "algorithm": "calculator_with_sumif_fallback",
                "source_sheet": "邀约专员提成",
                "finance_overrides": len(finance_overrides),
                "rows": len(metrics),
            },
        )
