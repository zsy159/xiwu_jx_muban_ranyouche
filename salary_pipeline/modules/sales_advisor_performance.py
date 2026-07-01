"""销售顾问岗位族绩效 — Phase B 绩效整理表 + topology 业务规则写 Hub W–AI。"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from salary_pipeline.calculators.sales_advisor.extract import (
    compute_for_advisor,
    match_advisor_row,
)
from salary_pipeline.calculators.sales_advisor.registry import (
    hub_columns_for_gate,
    is_hub_linked,
    list_roles,
)
from salary_pipeline.config.hub_performance_loader import load_hub_performance_config
from salary_pipeline.data_ingestion.data_loader import build_workbook_loader
from salary_pipeline.paths import resolve_project_path
from salary_pipeline.modules.base import (
    SUMMARY_KEY_COLUMNS,
    BaseCommissionModule,
    ModuleResult,
)

logger = logging.getLogger(__name__)

FAMILY_ID = "销售顾问"
_ROLE_BY_NAME = {r["name"]: r for r in list_roles()}


class SalesAdvisorPerformanceModule(BaseCommissionModule):
    """
    形态 C：Phase B computed 绩效整理表 → Hub W–AI 显式算薪。

    - 读 ``computed_perf_frame``（PerformanceSheetModule 输出）
    - 公式自 Hub topology 解析（SUMIF/SUMIFS × 完成率）
    - 仅 hub_linked 顾问写 overlay；子表全员见 销售提成标准
    """

    name = "sales_advisor_performance"
    roles = ["销售顾问"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        hub_cfg = load_hub_performance_config()
        family = hub_cfg.get("role_families", {}).get(FAMILY_ID, {})

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

        loader = build_workbook_loader(context)
        gate_cols = hub_columns_for_gate()
        month_config = context.get("month_config", {})
        perf_cfg = month_config.get("performance_sheet", {})
        hub_cfg = month_config.get("hub", {})
        topology_path = resolve_project_path(month_config["topology"]["sales"])
        use_golden_perf = perf_cfg.get("use_golden_perf_sheet", True)
        bootstrap_golden = hub_cfg.get("bootstrap_from_golden", False)

        rows: list[dict[str, Any]] = []
        for _, person in skeleton.iterrows():
            if not match_advisor_row(person):
                continue
            name = str(person["姓名"])
            role = _ROLE_BY_NAME.get(name)
            if role is not None and not is_hub_linked(role):
                continue

            result = compute_for_advisor(
                person,
                perf_frame,
                loader,
                topology_path=topology_path,
                use_golden_perf_sheet=use_golden_perf,
                bootstrap_from_golden=bootstrap_golden,
            )
            row_data: dict[str, Any] = {
                "店别": person["店别"],
                "职务": person["职务"],
                "姓名": name,
            }
            for col in gate_cols:
                if col in result.hub_metrics:
                    row_data[col] = result.hub_metrics[col]
            for col, val in result.hub_metrics.items():
                if col not in row_data:
                    row_data[col] = val
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
            "%s: matched=%s rules_sheet=%s perf_rows=%s",
            self.name,
            len(metrics),
            family.get("rules_sheet", "销售提成标准"),
            len(perf_frame),
        )
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=metrics,
            metadata={
                "family_id": FAMILY_ID,
                "rules_sheet": family.get("rules_sheet", "销售提成标准"),
                "algorithm": "perf_sheet_sumif_with_completion_rate",
                "source": "computed_perf_frame",
                "hub_linked_only": True,
                "rows": len(metrics),
                "hub_columns": list(gate_cols),
            },
        )
