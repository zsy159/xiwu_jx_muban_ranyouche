from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from salary_pipeline.data_ingestion.data_loader import (
    build_workbook_loader,
    read_personnel_skeleton_keys,
    read_summary_skeleton_keys,
    resolve_summary_skeleton_source,
)
from salary_pipeline.modules.base import PERSONNEL_FILENAME, PERSONNEL_SHEET
from salary_pipeline.modules.base import SUMMARY_KEY_COLUMNS
from salary_pipeline.modules.customer_specialist_performance import (
    CustomerSpecialistPerformanceModule,
)
from salary_pipeline.modules.direct_store_manager_performance import (
    DirectStoreManagerPerformanceModule,
)
from salary_pipeline.modules.invite_specialist_performance import (
    InviteSpecialistPerformanceModule,
)
from salary_pipeline.modules.new_media_performance import NewMediaPerformanceModule
from salary_pipeline.modules.registry import ModuleRegistry
from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
from salary_pipeline.modules.mortgage_clerk_performance import (
    MortgageClerkPerformanceModule,
)
from salary_pipeline.modules.network_advisor_performance import (
    NetworkAdvisorPerformanceModule,
)
from salary_pipeline.modules.recruit_performance import RecruitPerformanceModule
from salary_pipeline.modules.sales_advisor_performance import (
    SalesAdvisorPerformanceModule,
)
from salary_pipeline.modules.store_clerk_performance import StoreClerkPerformanceModule
from salary_pipeline.modules.yizhen_new_media_performance import (
    YizhenNewMediaPerformanceModule,
)
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.paths import PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import (
    CommissionSummaryBuilder,
    load_month_config,
)
from salary_pipeline.pipelines.hub_adjustment_rule_engine import HubAdjustmentRuleEngine
from salary_pipeline.pipelines.hub_metrics_rule_engine import HubMetricsRuleEngine
from salary_pipeline.pipelines.commission_summary_formatting import (
    apply_commission_summary_highlighting,
)
from salary_pipeline.pipelines.performance_sheet_formatting import (
    apply_performance_sheet_highlighting,
    resolve_perf_golden_path,
)
from salary_pipeline.pipelines.non_frontline_columns import (
    apply_non_frontline_columns,
    bootstrap_non_frontline_physical_columns,
)
from salary_pipeline.pipelines.performance_overlay import (
    clear_bootstrap_for_overlay,
    overlay_module_metrics,
)
from salary_pipeline.pipelines.performance_sheet_export import (
    export_computed_performance_sheet,
)
from salary_pipeline.pipelines.performance_sheet_paths import (
    load_resolved_performance_frame,
    resolve_system_performance_sheet_path,
)
from salary_pipeline.pipelines.run_cache import (
    compute_input_fingerprint,
    normalize_overlay_keys,
    resolve_cache_dir,
    save_hub_snapshot,
    write_manifest,
    load_hub_snapshot,
)

logger = logging.getLogger(__name__)

OverlayRunner = Callable[[dict[str, Any]], Any]


def _report_progress(ctx: dict[str, Any], stage_key: str, label: str) -> None:
    cb = ctx.get("progress_callback")
    if cb is not None:
        cb(stage_key, label)

# Ordered overlay registry: key → module factory (instantiated per run)
PERFORMANCE_OVERLAY_REGISTRY: list[tuple[str, OverlayRunner]] = [
    ("new-media", lambda ctx: NewMediaPerformanceModule().run(ctx)),
    ("yizhen-media", lambda ctx: YizhenNewMediaPerformanceModule().run(ctx)),
    ("invite", lambda ctx: InviteSpecialistPerformanceModule().run(ctx)),
    ("customer", lambda ctx: CustomerSpecialistPerformanceModule().run(ctx)),
    ("direct-store", lambda ctx: DirectStoreManagerPerformanceModule().run(ctx)),
    ("recruit", lambda ctx: RecruitPerformanceModule().run(ctx)),
    ("store-clerk", lambda ctx: StoreClerkPerformanceModule().run(ctx)),
    ("network-advisor", lambda ctx: NetworkAdvisorPerformanceModule().run(ctx)),
    ("mortgage-clerk", lambda ctx: MortgageClerkPerformanceModule().run(ctx)),
    # sales-advisor now also covers 销售主管/销售助理 (match_advisor_row);
    # 独立的 sales-supervisor overlay 已删除，避免重复计算同一批列。
    ("sales-advisor", lambda ctx: SalesAdvisorPerformanceModule().run(ctx)),
]


class SalesPipeline:
    """
    销售账套流水线：
    1. 各业务模块独立计算 → ModuleResult
    2. CommissionSummaryBuilder 聚合 → 提成汇总（系统生成，非导入）
    """

    def __init__(
        self,
        config_dir: Path | None = None,
        month_config: dict[str, Any] | None = None,
    ) -> None:
        from salary_pipeline.paths import CONFIG_DIR

        self.config_dir = config_dir or CONFIG_DIR
        if month_config is not None:
            self.month_config = month_config
        else:
            self.month_config = load_month_config(self.config_dir)
        self.registry = ModuleRegistry()
        self.registry.register(SummarySkeletonModule())
        self.summary_builder = CommissionSummaryBuilder()

    def _attach_excel_rows(self, summary: Any) -> Any:
        if summary is None or summary.empty or "_excel_row" in summary.columns:
            return summary
        parity = self.month_config.get("parity", {})
        start = int(parity.get("data_start_row", 3))
        sheet = self.month_config["outputs"]["commission_summary_sheet"]
        skeleton_wb, _, read_sheet = resolve_summary_skeleton_source(
            self.month_config, sheet_name=sheet
        )
        if skeleton_wb is not None:
            try:
                if read_sheet == PERSONNEL_SHEET:
                    keys = read_personnel_skeleton_keys(
                        skeleton_wb,
                        data_start_row=start,
                    )
                else:
                    keys = read_summary_skeleton_keys(
                        skeleton_wb,
                        read_sheet,
                        header_row=int(parity.get("header_row", 2)),
                        data_start_row=start,
                    )
                merged = summary.merge(
                    keys[[*SUMMARY_KEY_COLUMNS, "_excel_row"]],
                    on=SUMMARY_KEY_COLUMNS,
                    how="left",
                )
                if merged["_excel_row"].notna().all():
                    return merged
            except Exception as exc:
                logger.warning("Golden _excel_row merge failed, using sequential: %s", exc)
        out = summary.copy()
        out["_excel_row"] = [start + i for i in range(len(out))]
        return out

    def _run_overlays(
        self,
        summary: Any,
        ctx: dict[str, Any],
        module_results: list[Any],
        only: list[str] | None,
    ) -> Any:
        selected = set(only) if only else None
        for key, runner in PERFORMANCE_OVERLAY_REGISTRY:
            if selected is not None and key not in selected:
                logger.info("Skipping overlay %s (--only filter)", key)
                continue
            perf = runner(ctx)
            summary = clear_bootstrap_for_overlay(summary, perf)
            summary = overlay_module_metrics(summary, perf)
            module_results.append(perf)
        return summary

    def run(
        self,
        context: dict[str, Any] | None = None,
        *,
        from_stage: str = "full",
        only: list[str] | None = None,
    ) -> Any:
        if from_stage not in ("full", "hub"):
            raise ValueError(f"from_stage must be 'full' or 'hub', got {from_stage!r}")

        only_keys = normalize_overlay_keys(only)
        ctx = context or {}
        ctx["month_config"] = self.month_config
        ctx["project_root"] = PROJECT_ROOT
        module_results: list[Any] = []

        if from_stage == "full":
            logger.info("Running %d commission modules", len(self.registry.modules))
            _report_progress(ctx, "performance_sheet", "业务模块计算…")
            module_results = self.registry.run_all(ctx)
            summary = self.summary_builder.build(module_results)
            ctx["summary_skeleton"] = summary

            loader = build_workbook_loader(ctx)
            _report_progress(ctx, "performance_sheet", "绩效整理表生成…")
            perf_result = PerformanceSheetModule().run(ctx)
            computed_perf = ctx.get("computed_perf_frame")
            # Hub F–P 指标列改为 HubMetricsRuleEngine 声明式规则（同一套固定规则，
            # 按姓名匹配底层表；同列的店别差异以显式分组表达，如 H 列完成率封顶），
            # 不再回放 Excel 拓扑公式。销售顾问 W–AI 由 HubRuleEngine 在下方 overlay
            # （SalesAdvisorPerformanceModule）中声明式计算并覆盖。
            _report_progress(ctx, "hub_metrics", "Hub 列规则计算…")
            summary = HubMetricsRuleEngine().apply(
                summary, computed_perf_frame=computed_perf, loader=loader
            )
            _report_progress(ctx, "hub_adjustment", "Hub 调整列计算…")
            summary = HubAdjustmentRuleEngine(month_config=self.month_config).apply(
                summary, computed_perf_frame=computed_perf, loader=loader
            )
            ctx["summary_skeleton"] = self._attach_excel_rows(summary)
            if perf_result.metadata.get("rows"):
                logger.info(
                    "Performance sheet wired: %s rows, %s cols",
                    perf_result.metadata["rows"],
                    len(perf_result.metadata.get("implemented_columns", [])),
                )

            cache_dir = resolve_cache_dir(self.month_config)
            artifacts = save_hub_snapshot(cache_dir, summary, computed_perf)
            fingerprint = compute_input_fingerprint(self.month_config)
            write_manifest(cache_dir, fingerprint, stage="hub", artifacts=artifacts)
        else:
            cache_dir = resolve_cache_dir(self.month_config)
            _report_progress(ctx, "load_hub", "加载 Hub 快照…")
            summary, computed_perf = load_hub_snapshot(cache_dir)
            computed_perf = load_resolved_performance_frame(
                self.month_config, computed_perf
            )
            ctx["computed_perf_frame"] = computed_perf
            summary = self._attach_excel_rows(summary)
            ctx["summary_skeleton"] = summary
            logger.info(
                "Loaded hub snapshot from %s (summary %s rows, perf %s rows)",
                cache_dir,
                len(summary),
                len(computed_perf),
            )

        _report_progress(ctx, "overlay", "岗位绩效 overlay…")
        summary = self._run_overlays(summary, ctx, module_results, only_keys)
        parity_cfg = self.month_config.get("parity", {})
        golden_raw = parity_cfg.get("golden_workbook") or self.month_config.get(
            "workbooks", {}
        ).get("sales")
        golden_path = (
            resolve_project_path(golden_raw) if golden_raw else None
        )
        summary = bootstrap_non_frontline_physical_columns(
            summary,
            golden_path,
            sheet_name=self.month_config["outputs"].get(
                "commission_summary_sheet", "提成汇总"
            ),
            header_row=int(parity_cfg.get("header_row", 2)),
            data_start_row=int(parity_cfg.get("data_start_row", 3)),
        )
        summary = apply_non_frontline_columns(summary)
        summary = self.summary_builder._align_to_template(summary)
        summary = summary.drop(columns=["_excel_row"], errors="ignore")
        summary = summary.reset_index(drop=True)

        performance_sheet_path: Path | None = None
        computed_perf = ctx.get("computed_perf_frame")
        perf_cfg = self.month_config.get("performance_sheet", {})
        if (
            computed_perf is not None
            and not computed_perf.empty
            and perf_cfg.get("use_computed", True)
        ):
            performance_sheet_path = resolve_system_performance_sheet_path(
                self.month_config
            )
            month = self.month_config.get("month") or perf_cfg.get(
                "billing_month", ""
            )
            title = (
                f"{month} 销售绩效整理表（系统生成）"
                if month
                else "系统生成-绩效整理表"
            )
            export_computed_performance_sheet(
                computed_perf,
                performance_sheet_path,
                title=title,
                golden_path=resolve_perf_golden_path(self.month_config),
            )
            apply_performance_sheet_highlighting(
                self.month_config,
                performance_sheet_path,
                computed_frame=computed_perf,
            )

        _report_progress(ctx, "export_preview", "写出提成汇总…")
        output_path = resolve_project_path(
            self.month_config["outputs"]["commission_summary_file"]
        )
        sheet_name = self.month_config["outputs"]["commission_summary_sheet"]
        self.summary_builder.export_excel(summary, output_path, sheet_name=sheet_name)
        apply_commission_summary_highlighting(self.month_config, output_path)

        return {
            "module_results": module_results,
            "summary": summary,
            "output_path": output_path,
            "computed_perf_frame": computed_perf,
            "performance_sheet_path": performance_sheet_path,
        }
