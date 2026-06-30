#!/usr/bin/env python3
"""CLI entry inside package. Prefer project root: python main.py ..."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config
from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
from salary_pipeline.pipelines.performance_sheet_export import export_computed_performance_sheet
from salary_pipeline.pipelines.run_cache import (
    cache_is_valid,
    compute_input_fingerprint,
    read_manifest,
    resolve_cache_dir,
)
from salary_pipeline.pipelines.commission_summary_formatting import (
    apply_commission_summary_highlighting,
)
from salary_pipeline.pipelines.sales import SalesPipeline
from salary_pipeline.pipelines.aftersales import AftersalesPipeline
from salary_pipeline.pipelines.aftersales_formula_engine import (
    AIRPORT_CONFIG,
    WUHOU_CONFIG,
)
from salary_pipeline.pipelines.xw_payout import ChannelPayoutPipeline
from salary_pipeline.pipelines.xw_payout_formula_engine import (
    PAYOUT_CHANNEL_COLUMN_MAPS,
    XW_COLUMN_MAP,
)
from salary_pipeline.validation.parity import (
    CommissionSummaryParity,
    compare_hub_parity_bundle,
    write_diff_report,
    write_hub_diff_report,
)
from salary_pipeline.calculators.sales_advisor.registry import (
    build_reconcile_deferred_cells,
)


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _report_dir(config: dict, args: argparse.Namespace) -> Path:
    if args.report_dir:
        return resolve_project_path(args.report_dir)
    return resolve_project_path(
        config.get("outputs", {}).get("report_dir", "output/reports")
    )


def cmd_export_performance_sheet(args: argparse.Namespace) -> int:
    config = load_month_config(CONFIG_DIR)
    ctx: dict = {"month_config": config}
    result = PerformanceSheetModule().run(ctx)
    frame = ctx.get("computed_perf_frame")
    if frame is None or frame.empty:
        print("[export-performance-sheet] 未生成绩效整理表（检查 performance_sheet.use_computed）")
        return 1

    if args.output:
        output_path = resolve_project_path(args.output)
    else:
        output_path = resolve_project_path(
            config.get("outputs", {}).get(
                "performance_sheet_file",
                "output/绩效整理表-系统生成.xlsx",
            )
        )

    month = config.get("month") or config.get("performance_sheet", {}).get(
        "billing_month", ""
    )
    title = f"{month} 销售绩效整理表（系统生成）" if month else "系统生成-绩效整理表"
    export_computed_performance_sheet(frame, output_path, title=title)

    meta = result.metadata
    print(f"[export-performance-sheet] 已导出: {output_path}")
    print(
        f"[export-performance-sheet] rows={meta.get('rows', len(frame))} "
        f"cols={len(meta.get('implemented_columns', []))} 已实现列"
    )
    if meta.get("implemented_columns"):
        print(f"[export-performance-sheet] 列: {', '.join(meta['implemented_columns'])}")
    return 0


def cmd_compute(args: argparse.Namespace) -> int:
    config = load_month_config(CONFIG_DIR)
    from_stage = args.from_stage

    if from_stage == "hub":
        cache_dir = resolve_cache_dir(config)
        manifest = read_manifest(cache_dir)
        current_fp = compute_input_fingerprint(config)
        valid, reason = cache_is_valid(
            manifest, current_fp, scope="hub", cache_dir=cache_dir
        )
        if not valid:
            print(f"[compute] Hub 缓存不可用: {reason}")
            print(
                "[compute] 请先运行完整计算: python main.py compute"
                "（源 Excel / 拓扑 / 绩效配置变更后须全量重算）"
            )
            return 1

    pipeline = SalesPipeline(CONFIG_DIR)
    result = pipeline.run(from_stage=from_stage, only=args.only)
    print(f"[compute] 提成汇总已生成: {result['output_path']}")
    print(f"[compute] shape={result['summary'].shape}")
    if from_stage == "hub":
        only_msg = f", only={args.only}" if args.only else ""
        print(f"[compute] 增量模式: from=hub{only_msg}")
    if args.reconcile:
        return cmd_reconcile(
            argparse.Namespace(
                computed=result["output_path"],
                golden=args.golden,
                sheet=args.sheet,
                report_dir=args.report_dir,
                verbose=args.verbose,
            )
        )
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    config = load_month_config(CONFIG_DIR)
    parity_cfg = config.get("parity", {})

    golden_path = resolve_project_path(
        args.golden or parity_cfg["golden_workbook"]
    )
    computed_path = resolve_project_path(
        args.computed or config["outputs"]["commission_summary_file"]
    )
    sheet = args.sheet or parity_cfg.get("golden_sheet", "提成汇总")
    report_dir = _report_dir(config, args)
    header_row = int(parity_cfg.get("header_row", 2))
    data_start_row = int(parity_cfg.get("data_start_row", 3))
    perf_path = resolve_project_path(
        config["outputs"].get("performance_sheet_file")
        or computed_path.parent / "绩效整理表-系统生成.xlsx"
    )
    deferred_for_highlight = build_reconcile_deferred_cells(
        golden_path,
        perf_path=perf_path,
        header_row=header_row,
        data_start_row=data_start_row,
    )

    bundle = compare_hub_parity_bundle(
        computed_path,
        golden_path,
        sheet,
        parity_cfg,
        deferred_cells=deferred_for_highlight,
    )
    if bundle.performance is not None:
        json_path, md_path = write_hub_diff_report(bundle, report_dir)
    else:
        json_path, md_path = write_diff_report(bundle.metrics, report_dir)

    report = bundle.metrics
    print(f"[reconcile] F–P 验收: {'通过' if report.overall_passed else '未通过'}")
    if bundle.performance is not None:
        perf = bundle.performance
        passed_roles = sum(1 for r in perf.roles if r.passed)
        print(
            f"[reconcile] W–AI 绩效: {'通过' if perf.overall_passed else '未通过'} "
            f"({passed_roles}/{len(perf.roles)} 岗位通过, "
            f"{sum(r.mismatch_cells for r in perf.roles)} 处不一致)"
        )
    if bundle.gated_performance is not None:
        gated = bundle.gated_performance
        g_passed = sum(1 for r in gated.roles if r.passed)
        print(
            f"[reconcile] 算薪族 parity_gate: {'通过' if gated.overall_passed else '未通过'} "
            f"({g_passed}/{len(gated.roles)} 岗位通过, "
            f"{sum(r.mismatch_cells for r in gated.roles)} 处不一致)"
        )
    print(f"[reconcile] 整体(F–P): {'通过' if report.overall_passed else '未通过'}")
    print(f"[reconcile] 差异报告: {md_path}")
    print(f"[reconcile] JSON: {json_path}")
    for role in report.roles:
        mark = "OK" if role.passed else "FAIL"
        print(
            f"  [{mark}] {role.role}: missing={role.missing_rows} "
            f"mismatch_cells={role.mismatch_cells}"
        )

    compare_columns = list(parity_cfg.get("columns") or []) + list(
        parity_cfg.get("performance_columns") or []
    )
    if compare_columns:
        stats = apply_commission_summary_highlighting(
            config,
            computed_path,
            golden_path=golden_path,
        )
        print(
            f"[reconcile] 高亮 {stats.mismatches} 个不一致单元格 -> {computed_path}"
        )
        if stats.deferred:
            print(
                f"[reconcile] 高亮 {stats.deferred} 个单元格"
                f"（灰=金标准直填，蓝=公式含手工） -> {computed_path}"
            )
        if stats.annotated:
            print(
                f"[reconcile] 批注 {stats.annotated} 个公式异常单元格 -> {computed_path}"
            )

    return 0 if report.overall_passed else 2


def cmd_compute_aftersales(args: argparse.Namespace) -> int:
    pipeline = AftersalesPipeline(CONFIG_DIR, store=args.store)
    result = pipeline.run()
    print(
        f"[compute-aftersales] {result['store']} 已生成: {result['output_path']}"
    )
    print(f"[compute-aftersales] shape={result['summary'].shape} warnings={len(result['warnings'])}")
    if args.reconcile:
        return cmd_reconcile_aftersales(
            argparse.Namespace(
                store=args.store,
                computed=result["output_path"],
                golden=args.golden,
                sheet=args.sheet,
                report_dir=args.report_dir,
                verbose=args.verbose,
            )
        )
    return 0


def cmd_reconcile_aftersales(args: argparse.Namespace) -> int:
    config = load_month_config(CONFIG_DIR)
    parity_cfg = config.get("aftersales_parity", {})
    store_cfg = config.get("aftersales", {}).get("stores", {}).get(args.store, {})
    engine_cfg = WUHOU_CONFIG if args.store == "wuhou" else AIRPORT_CONFIG

    golden_path = resolve_project_path(
        args.golden or store_cfg.get("golden_workbook") or config["workbooks"]["aftersales"]
    )
    sheet = args.sheet or store_cfg.get("anchor_sheet") or engine_cfg.anchor_sheet
    output_key = f"aftersales_{args.store}"
    computed_path = resolve_project_path(
        args.computed or config["outputs"].get(output_key)
    )
    report_dir = _report_dir(config, args)

    checker = CommissionSummaryParity(
        join_keys=parity_cfg.get("join_keys", ["店别", "姓名"]),
        numeric_tolerance=float(parity_cfg.get("numeric_tolerance", 1e-6)),
        columns=parity_cfg.get("columns"),
        role_column=parity_cfg.get("role_column", "店别"),
    )
    report = checker.compare_aftersales_files(
        computed_path,
        golden_path,
        sheet,
        engine_cfg.column_map,
        data_start_row=int(parity_cfg.get("data_start_row", 5)),
    )
    json_path, md_path = write_diff_report(report, report_dir)

    print(f"[reconcile-aftersales] {args.store} 整体: {'通过' if report.overall_passed else '未通过'}")
    print(f"[reconcile-aftersales] 差异报告: {md_path}")
    for role in report.roles:
        mark = "OK" if role.passed else "FAIL"
        print(
            f"  [{mark}] {role.role}: missing={role.missing_rows} "
            f"mismatch_cells={role.mismatch_cells}"
        )
    return 0 if report.overall_passed else 2


PAYOUT_CHANNELS = ("xw", "direct_store", "cs")

PAYOUT_PARITY_KEYS = {
    "xw": "payout_parity",
    "direct_store": "direct_store_parity",
    "cs": "cs_parity",
}

PAYOUT_OUTPUT_KEYS = {
    "xw": "xw_payout",
    "direct_store": "direct_store_payout",
    "cs": "cs_payout",
}


def _payout_channel_label(channel: str) -> str:
    return {
        "xw": "XW提成-发",
        "direct_store": "直营店提成-发",
        "cs": "CS提成-发",
    }.get(channel, channel)


def cmd_compute_payout(args: argparse.Namespace) -> int:
    channel = args.channel
    pipeline = ChannelPayoutPipeline(channel, CONFIG_DIR)
    result = pipeline.run()
    label = _payout_channel_label(channel)
    print(f"[compute-payout] {label} 已生成: {result['output_path']}")
    print(
        f"[compute-payout] shape={result['summary'].shape} "
        f"warnings={len(result['warnings'])}"
    )
    if args.reconcile:
        return cmd_reconcile_payout(
            argparse.Namespace(
                channel=channel,
                computed=result["output_path"],
                golden=args.golden,
                sheet=args.sheet,
                report_dir=args.report_dir,
                verbose=args.verbose,
            )
        )
    return 0


def cmd_reconcile_payout(args: argparse.Namespace) -> int:
    channel = getattr(args, "channel", "xw")
    config = load_month_config(CONFIG_DIR)
    parity_key = PAYOUT_PARITY_KEYS.get(channel, "payout_parity")
    parity_cfg = config.get(parity_key, config.get("payout_parity", {}))
    payout_cfg = config.get("payout", {}).get(channel, config.get("payout", {}).get("xw", {}))

    golden_path = resolve_project_path(
        args.golden or payout_cfg.get("golden_workbook") or config["workbooks"]["sales"]
    )
    sheet = args.sheet or payout_cfg.get("anchor_sheet") or _payout_channel_label(channel)
    output_key = PAYOUT_OUTPUT_KEYS.get(channel, "xw_payout")
    computed_path = resolve_project_path(
        args.computed or config["outputs"].get(output_key)
    )
    report_dir = _report_dir(config, args)
    column_map = PAYOUT_CHANNEL_COLUMN_MAPS.get(channel, XW_COLUMN_MAP)

    checker = CommissionSummaryParity(
        join_keys=parity_cfg.get("join_keys", ["店别", "职务", "姓名"]),
        numeric_tolerance=float(parity_cfg.get("numeric_tolerance", 1e-4)),
        columns=parity_cfg.get("columns"),
        role_column=parity_cfg.get("role_column", "店别"),
    )
    report = checker.compare_payout_files(
        computed_path,
        golden_path,
        sheet,
        column_map,
        data_start_row=int(parity_cfg.get("data_start_row", 3)),
    )
    json_path, md_path = write_diff_report(report, report_dir)

    label = _payout_channel_label(channel)
    print(f"[reconcile-payout] {label} 整体: {'通过' if report.overall_passed else '未通过'}")
    print(f"[reconcile-payout] 差异报告: {md_path}")
    for role in report.roles:
        mark = "OK" if role.passed else "FAIL"
        print(
            f"  [{mark}] {role.role}: missing={role.missing_rows} "
            f"mismatch_cells={role.mismatch_cells}"
        )
    return 0 if report.overall_passed else 2


def cmd_compute_all(args: argparse.Namespace) -> int:
    """Hub → all payout channels end-to-end; optional reconcile at each stage."""
    hub_pipeline = SalesPipeline(CONFIG_DIR)
    hub_result = hub_pipeline.run()
    print(f"[compute-all] 提成汇总: {hub_result['output_path']}")
    print(f"[compute-all] hub shape={hub_result['summary'].shape}")

    hub_context = {
        "hub_path": hub_result["output_path"],
        "use_computed_hub": True,
    }
    payout_results: dict[str, dict] = {}
    for channel in PAYOUT_CHANNELS:
        pipeline = ChannelPayoutPipeline(channel, CONFIG_DIR)
        result = pipeline.run(context=hub_context)
        payout_results[channel] = result
        label = _payout_channel_label(channel)
        print(f"[compute-all] {label}: {result['output_path']}")
        print(
            f"[compute-all] {channel} shape={result['summary'].shape} "
            f"warnings={len(result['warnings'])}"
        )

    if not args.reconcile:
        return 0

    exit_codes = [
        cmd_reconcile(
            argparse.Namespace(
                computed=hub_result["output_path"],
                golden=args.golden,
                sheet=args.sheet,
                report_dir=args.report_dir,
                verbose=args.verbose,
            )
        )
    ]
    for channel in PAYOUT_CHANNELS:
        exit_codes.append(
            cmd_reconcile_payout(
                argparse.Namespace(
                    channel=channel,
                    computed=payout_results[channel]["output_path"],
                    golden=args.golden,
                    sheet=None,
                    report_dir=args.report_dir,
                    verbose=args.verbose,
                )
            )
        )
    return 0 if all(rc == 0 for rc in exit_codes) else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="薪酬提成流水线 — 模块计算聚合生成提成汇总，支持对账比对",
        epilog=(
            "快速工作流：\n"
            "  仅改对账/批注 → `reconcile`（~3–4 分钟）\n"
            "  改单个岗位计算器 → `compute --from hub --only <role>`（~2–5 分钟）\n"
            "  改源 Excel / 拓扑 / 绩效配置 → `compute` 全量（~10–17 分钟）\n"
            "  `--only` 可重复：sales-advisor, new-media, invite, customer, "
            "direct-store, recruit"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    compute = sub.add_parser(
        "compute",
        help="运行各模块并聚合生成提成汇总（默认全量重算）",
    )
    compute.add_argument(
        "--from",
        dest="from_stage",
        choices=("full", "hub"),
        default="full",
        help="full=全量（默认）；hub=从 Hub 快照增量重跑 overlay",
    )
    compute.add_argument(
        "--only",
        action="append",
        dest="only",
        metavar="ROLE",
        default=None,
        help="仅重跑指定岗位 overlay（可多次）；须配合 --from hub",
    )
    compute.add_argument(
        "--reconcile",
        action="store_true",
        help="计算后自动对账；若 output 已存在且只需对账，请用 reconcile 子命令",
    )
    compute.add_argument("--golden", help="金标准工作簿路径")
    compute.add_argument("--sheet", default=None)
    compute.add_argument("--report-dir", default=None)
    compute.set_defaults(func=cmd_compute)

    reconcile = sub.add_parser(
        "reconcile",
        help="仅对账（跳过 compute，读取已有 output/提成汇总.xlsx）",
    )
    reconcile.add_argument("--computed", help="计算生成的 提成汇总.xlsx")
    reconcile.add_argument("--golden", help="金标准工作簿路径")
    reconcile.add_argument("--sheet", default=None)
    reconcile.add_argument("--report-dir", default=None)
    reconcile.set_defaults(func=cmd_reconcile)

    compute_as = sub.add_parser(
        "compute-aftersales",
        help="运行售后账套（武侯/机场）提成表计算",
    )
    compute_as.add_argument(
        "--store",
        choices=["wuhou", "airport"],
        default="wuhou",
        help="门店标识",
    )
    compute_as.add_argument("--reconcile", action="store_true")
    compute_as.add_argument("--golden", help="金标准工作簿路径")
    compute_as.add_argument("--sheet", default=None)
    compute_as.add_argument("--report-dir", default=None)
    compute_as.set_defaults(func=cmd_compute_aftersales)

    reconcile_as = sub.add_parser(
        "reconcile-aftersales",
        help="对账：计算版售后提成表 vs 金标准",
    )
    reconcile_as.add_argument(
        "--store",
        choices=["wuhou", "airport"],
        default="wuhou",
    )
    reconcile_as.add_argument("--computed", help="计算生成的售后提成 xlsx")
    reconcile_as.add_argument("--golden", help="金标准工作簿路径")
    reconcile_as.add_argument("--sheet", default=None)
    reconcile_as.add_argument("--report-dir", default=None)
    reconcile_as.set_defaults(func=cmd_reconcile_aftersales)

    compute_po = sub.add_parser("compute-payout", help="运行渠道发薪表（XW / 直营店 / CS）")
    compute_po.add_argument(
        "--channel",
        choices=PAYOUT_CHANNELS,
        default="xw",
        help="发薪渠道（默认 xw）",
    )
    compute_po.add_argument("--reconcile", action="store_true")
    compute_po.add_argument("--golden", help="金标准工作簿路径")
    compute_po.add_argument("--sheet", default=None)
    compute_po.add_argument("--report-dir", default=None)
    compute_po.set_defaults(func=cmd_compute_payout)

    reconcile_po = sub.add_parser(
        "reconcile-payout",
        help="对账：计算版发薪表 vs 金标准",
    )
    reconcile_po.add_argument(
        "--channel",
        choices=PAYOUT_CHANNELS,
        default="xw",
        help="发薪渠道（默认 xw）",
    )
    reconcile_po.add_argument("--computed", help="计算生成的发薪 xlsx")
    reconcile_po.add_argument("--golden", help="金标准工作簿路径")
    reconcile_po.add_argument("--sheet", default=None)
    reconcile_po.add_argument("--report-dir", default=None)
    reconcile_po.set_defaults(func=cmd_reconcile_payout)

    compute_all = sub.add_parser(
        "compute-all",
        help="端到端：提成汇总 → XW/直营店/CS 发薪（合并计算版 hub + 金标准 W–AR）",
    )
    compute_all.add_argument("--reconcile", action="store_true")
    compute_all.add_argument("--golden", help="金标准工作簿路径")
    compute_all.add_argument("--sheet", default=None)
    compute_all.add_argument("--report-dir", default=None)
    compute_all.set_defaults(func=cmd_compute_all)

    export_perf = sub.add_parser(
        "export-performance-sheet",
        help="导出系统重算的绩效整理表（computed_perf_frame）为 Excel",
    )
    export_perf.add_argument(
        "--output",
        help="输出 xlsx 路径（默认 output/YYYY-MM/绩效整理表-系统生成.xlsx）",
    )
    export_perf.set_defaults(func=cmd_export_performance_sheet)

    return parser


def main() -> int:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
