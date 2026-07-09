"""客户专员岗位族绩效 — 按人映射子表单元格至 hub 列。"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from salary_pipeline.calculators.customer_specialist.finance_inputs import (
    load_finance_hub_overrides,
)
from salary_pipeline.calculators.customer_specialist.registry import (
    get_role,
    hub_mapping_for_role,
    list_roles,
)
from salary_pipeline.config.hub_performance_loader import load_hub_performance_config
from salary_pipeline.data_ingestion.customer_specialist_sheet import (
    SHEET as CUSTOMER_SHEET,
    lookup_hub_metrics,
    match_customer_row,
)
from salary_pipeline.data_ingestion.data_loader import build_workbook_loader, normalize_name
from salary_pipeline.modules.base import (
    SUMMARY_KEY_COLUMNS,
    BaseCommissionModule,
    ModuleResult,
)

logger = logging.getLogger(__name__)

FAMILY_ID = "客户专员"
_ROLE_BY_NAME = {r["name"]: r for r in list_roles()}


class CustomerSpecialistPerformanceModule(BaseCommissionModule):
    """
    形态 B：主账套「客户部提成」子表 → hub 多列直引（非 SUMIF）。

    - 张保珍：W=固定 2000，Y=H42
    - 邓芳：X=AT7，Y=F42
    - 周舟：Y=AD3
    """

    name = "customer_specialist_performance"
    roles = ["主管", "专员"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        hub_cfg = load_hub_performance_config()
        family = hub_cfg.get("role_families", {}).get(FAMILY_ID, {})

        skeleton = context.get("summary_skeleton")
        if skeleton is None or skeleton.empty:
            logger.warning("%s: empty summary_skeleton", self.name)
            return ModuleResult(
                module_name=self.name,
                roles=self.roles,
                metrics=pd.DataFrame(columns=SUMMARY_KEY_COLUMNS),
                metadata={"status": "no_skeleton"},
            )

        loader = build_workbook_loader(context)
        sheet = str(family.get("rules_sheet", CUSTOMER_SHEET))
        sheet_available = loader.has_sheet(sheet)
        if not sheet_available:
            logger.warning(
                "%s: sheet %r missing; overlay leaves customer specialist columns empty",
                self.name,
                sheet,
            )
        month = context.get("month_config", {}).get("month", "")
        finance_overrides = load_finance_hub_overrides(month) if month else {}

        rows: list[dict[str, Any]] = []
        for _, person in skeleton.iterrows():
            if not match_customer_row(person):
                continue
            name = str(person["姓名"])
            role = _ROLE_BY_NAME.get(name)
            if role is None or not role.get("hub_mapping"):
                continue

            row_data: dict[str, Any] = {
                "店别": person["店别"],
                "职务": person["职务"],
                "姓名": name,
            }
            if name in finance_overrides:
                for col, val in finance_overrides[name].items():
                    row_data[col] = val
            elif sheet_available:
                metrics = lookup_hub_metrics(loader, name)
                for hub_col in hub_mapping_for_role(role):
                    if hub_col in metrics:
                        row_data[hub_col] = metrics[hub_col]
            rows.append(row_data)

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
            family.get("rules_sheet", "客户部提成"),
        )
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=metrics,
            metadata={
                "family_id": FAMILY_ID,
                "rules_sheet": family.get("rules_sheet", "客户部提成"),
                "algorithm": "cell_ref_subsheet",
                "source_sheet": sheet,
                "sheet_available": sheet_available,
                "finance_overrides": len(finance_overrides),
                "rows": len(metrics),
            },
        )
