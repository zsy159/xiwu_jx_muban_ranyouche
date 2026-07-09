#!/usr/bin/env python3
"""CLI entry inside package. Prefer project root: python main.py ..."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from salary_pipeline.observability.loaders import (
    load_month_config_for,
    load_months_registry,
    register_month,
)
from salary_pipeline.paths import (
    CONFIG_DIR,
    PROJECT_ROOT,
    output_month_dir,
    raw_month_dir,
    resolve_project_path,
)
from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
from salary_pipeline.pipelines.performance_sheet_export import (
    export_computed_performance_sheet,
    prepare_export_frame,
    resolve_export_column_spec,
)
from salary_pipeline.pipelines.performance_sheet_formatting import (
    apply_performance_sheet_highlighting,
    resolve_perf_golden_path,
)
from salary_pipeline.pipelines.run_cache import (
    cache_is_valid,
    compute_input_fingerprint,
    read_manifest,
    resolve_cache_dir,
)
from salary_pipeline.pipelines.commission_summary_formatting import (
    apply_commission_summary_highlighting,
)
from salary_pipeline.pipelines.payout_formatting import (
    apply_payout_highlighting,
    resolve_payout_compare_columns,
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


def _default_month() -> str:
    registry = load_months_registry()
    return str(registry.get("default_month", "2026-05"))


def _month_from_args(args: argparse.Namespace) -> str:
    return getattr(args, "month", None) or _default_month()


def _resolve_month_config(month_id: str) -> dict[str, Any]:
    registry = load_months_registry()
    known = set(registry.get("months", {}))
    if month_id not in known:
        registered = ", ".join(sorted(known)) or "(none)"
        raise SystemExit(
            f"Unknown month '{month_id}'. Registered: {registered}. "
            f"Onboard with: python main.py onboard-month --month {month_id} ..."
        )
    return load_month_config_for(month_id)


def _config_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return _resolve_month_config(_month_from_args(args))


def _has_golden_workbook(config: dict[str, Any], *, channel: str | None = None) -> bool:
    if channel:
        payout_cfg = config.get("payout", {}).get(channel, {})
        golden = payout_cfg.get("golden_workbook")
    else:
        golden = config.get("parity", {}).get("golden_workbook")
    if golden is None:
        return False
    if isinstance(golden, str) and not golden.strip():
        return False
    return True


def _add_month_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--month",
        metavar="YYYY-MM",
        default=None,
        help=f"账期（默认 months_registry default_month={_default_month()}）",
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


def _relative_project_path(path: Path) -> str:
    resolved = path.resolve()
    root = PROJECT_ROOT.resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def cmd_onboard_month(args: argparse.Namespace) -> int:
    month_id = args.month
    if args.extract_topology and args.inherit_topology:
        print("[onboard-month] 不能同时使用 --extract-topology 与 --inherit-topology")
        return 1

    sales_path = resolve_project_path(args.sales)
    if not sales_path.exists():
        print(f"[onboard-month] 销售账套不存在: {sales_path}")
        return 1
    sales_rel = _relative_project_path(sales_path)

    rules_rel: str | None = None
    if args.rules:
        rules_path = resolve_project_path(args.rules)
        if not rules_path.exists():
            print(f"[onboard-month] 提成依据不存在: {rules_path}")
            return 1
        rules_rel = _relative_project_path(rules_path)

    sheet_sources_rel: str | None = None
    if args.sheet_sources:
        sheet_sources_path = resolve_project_path(args.sheet_sources)
        if not sheet_sources_path.exists():
            print(f"[onboard-month] sheet_sources 不存在: {sheet_sources_path}")
            return 1
        sheet_sources_rel = _relative_project_path(sheet_sources_path)

    from salary_pipeline.ingestion_upload.month_config import write_month_config

    if args.inherit_topology:
        inherit_month = args.inherit_topology
        try:
            inherit_cfg = load_month_config_for(inherit_month)
        except (FileNotFoundError, OSError) as exc:
            print(f"[onboard-month] 无法加载继承月份配置 {inherit_month}: {exc}")
            return 1

        topo = inherit_cfg.get("topology", {})
        sales_topo = topo.get("sales")
        rules_topo = topo.get("rules")
        aftersales_topo = topo.get("aftersales")
        for name, rel in (
            ("sales", sales_topo),
            ("rules", rules_topo),
            ("aftersales", aftersales_topo),
        ):
            if not rel:
                print(f"[onboard-month] 继承配置缺少 topology.{name}")
                return 1
            if not resolve_project_path(rel).exists():
                print(f"[onboard-month] 拓扑文件不存在: {rel}")
                return 1

        config_path = write_month_config(
            month_id,
            sales_workbook=sales_rel,
            rules_workbook=rules_rel,
            sales_topology=sales_topo,
            rules_topology=rules_topo,
            aftersales_topology=aftersales_topo,
            sheet_sources_file=sheet_sources_rel,
            no_golden=True,
        )
        print(f"[onboard-month] 继承 {inherit_month} 拓扑（无金标准）")
    elif args.extract_topology:
        from salary_pipeline.ingestion_upload.topology import extract_sales_topology

        topo_rel = str(extract_sales_topology(sales_path, month_id))
        config_path = write_month_config(
            month_id,
            sales_workbook=sales_rel,
            rules_workbook=rules_rel,
            sales_topology=topo_rel,
            rules_topology=topo_rel,
            sheet_sources_file=sheet_sources_rel,
        )
        print(f"[onboard-month] 已提取销售拓扑: {topo_rel}")
    else:
        from salary_pipeline.ingestion_upload.default_rules import (
            canonical_month_label,
            resolve_existing_canonical_topology,
        )

        topo, topo_errors = resolve_existing_canonical_topology()
        if topo_errors:
            for err in topo_errors:
                print(f"[onboard-month] {err}")
            return 1

        canonical_month, canonical_label = canonical_month_label()
        config_path = write_month_config(
            month_id,
            sales_workbook=sales_rel,
            rules_workbook=rules_rel,
            sales_topology=topo["sales"],
            rules_topology=topo["rules"],
            aftersales_topology=topo["aftersales"],
            sheet_sources_file=sheet_sources_rel,
            no_golden=True,
        )
        print(
            f"[onboard-month] 使用系统固化规则（{canonical_label}，无金标准）"
        )

    label = args.label or month_id
    raw_dir = f"data/raw/{month_id}"
    register_month(month_id, label, raw_dir, config=config_path.name)

    output_month_dir(month_id).mkdir(parents=True, exist_ok=True)
    (raw_month_dir(month_id) / "uploads").mkdir(parents=True, exist_ok=True)

    print(f"[onboard-month] 已注册 {month_id} ({label})")
    print(f"[onboard-month] 配置: {config_path}")
    return 0


def cmd_export_performance_sheet(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
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
    golden_path = resolve_perf_golden_path(config)
    export_computed_performance_sheet(
        frame, output_path, title=title, golden_path=golden_path
    )

    meta = result.metadata
    print(f"[export-performance-sheet] 已导出: {output_path}")
    print(
        f"[export-performance-sheet] rows={meta.get('rows', len(frame))} "
        f"cols={len(prepare_export_frame(frame, column_spec=resolve_export_column_spec(golden_path)).columns)} "
        f"(金标准表头对齐)"
    )
    if meta.get("implemented_columns"):
        print(
            f"[export-performance-sheet] 已实现 {len(meta['implemented_columns'])} 列: "
            f"{', '.join(meta['implemented_columns'])}"
        )

    if getattr(args, "reconcile", False):
        if golden_path is None:
            print("[export-performance-sheet] 无金标准，跳过对账高亮")
        else:
            stats = apply_performance_sheet_highlighting(
                config, output_path, golden_path=golden_path, computed_frame=frame
            )
            print(
                f"[export-performance-sheet] 对账高亮: "
                f"差异={stats.mismatches} 手填标记={stats.manual_marked} "
                f"待填列格={stats.unimplemented_marked}"
            )
    return 0


def cmd_compute(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
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

    pipeline = SalesPipeline(CONFIG_DIR, month_config=config)
    result = pipeline.run(from_stage=from_stage, only=args.only)
    print(f"[compute] 提成汇总已生成: {result['output_path']}")
    print(f"[compute] shape={result['summary'].shape}")
    if from_stage == "hub":
        only_msg = f", only={args.only}" if args.only else ""
        print(f"[compute] 增量模式: from=hub{only_msg}")
    if args.reconcile:
        if not _has_golden_workbook(config):
            print("[compute] 本月无金标准，跳过对账")
            return 0
        return cmd_reconcile(
            argparse.Namespace(
                month=args.month,
                computed=result["output_path"],
                golden=args.golden,
                sheet=args.sheet,
                report_dir=args.report_dir,
                verbose=args.verbose,
            )
        )
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    if not _has_golden_workbook(config):
        print("[reconcile] 本月无金标准，跳过")
        return 0
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
    config = _config_from_args(args)
    pipeline = AftersalesPipeline(CONFIG_DIR, store=args.store, month_config=config)
    result = pipeline.run()
    print(
        f"[compute-aftersales] {result['store']} 已生成: {result['output_path']}"
    )
    print(f"[compute-aftersales] shape={result['summary'].shape} warnings={len(result['warnings'])}")
    if args.reconcile:
        return cmd_reconcile_aftersales(
            argparse.Namespace(
                month=args.month,
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
    config = _config_from_args(args)
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
    config = _config_from_args(args)
    channel = args.channel
    pipeline = ChannelPayoutPipeline(channel, CONFIG_DIR, month_config=config)
    context: dict = {}
    if getattr(args, "golden_hub", False):
        logging.warning(
            "--golden-hub is deprecated and ignored; "
            "payout SUMIF always uses computed 提成汇总.xlsx"
        )
    result = pipeline.run(context=context or None)
    label = _payout_channel_label(channel)
    print(f"[compute-payout] {label} 已生成: {result['output_path']}")
    hub_note = (
        f"hub=computed ({result['hub_path'].name})"
        if result.get("use_computed_hub") and result.get("hub_path")
        else "hub=computed (missing — SUMIF columns empty)"
    )
    print(
        f"[compute-payout] shape={result['summary'].shape} "
        f"warnings={len(result['warnings'])} {hub_note}"
    )
    if args.reconcile:
        return cmd_reconcile_payout(
            argparse.Namespace(
                month=args.month,
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
    config = _config_from_args(args)
    if not _has_golden_workbook(config, channel=channel):
        label = _payout_channel_label(channel)
        print(f"[reconcile-payout] {label} 本月无金标准，跳过")
        return 0
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
    compare_columns = resolve_payout_compare_columns(parity_cfg, column_map)

    checker = CommissionSummaryParity(
        join_keys=parity_cfg.get("join_keys", ["店别", "职务", "姓名"]),
        numeric_tolerance=float(parity_cfg.get("numeric_tolerance", 1e-4)),
        columns=compare_columns,
        role_column=parity_cfg.get("role_column", "店别"),
        literal_columns=True,
    )
    report = checker.compare_payout_files(
        computed_path,
        golden_path,
        sheet,
        column_map,
        data_start_row=int(parity_cfg.get("data_start_row", 3)),
    )
    json_path, md_path = write_diff_report(report, report_dir)

    apply_payout_highlighting(config, computed_path, channel)

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
    config = _config_from_args(args)
    hub_pipeline = SalesPipeline(CONFIG_DIR, month_config=config)
    hub_result = hub_pipeline.run()
    print(f"[compute-all] 提成汇总: {hub_result['output_path']}")
    print(f"[compute-all] hub shape={hub_result['summary'].shape}")

    hub_context = {
        "hub_path": hub_result["output_path"],
        "use_computed_hub": True,
    }
    payout_results: dict[str, dict] = {}
    for channel in PAYOUT_CHANNELS:
        pipeline = ChannelPayoutPipeline(channel, CONFIG_DIR, month_config=config)
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

    exit_codes: list[int] = []
    if _has_golden_workbook(config):
        exit_codes.append(
            cmd_reconcile(
                argparse.Namespace(
                    month=args.month,
                    computed=hub_result["output_path"],
                    golden=args.golden,
                    sheet=args.sheet,
                    report_dir=args.report_dir,
                    verbose=args.verbose,
                )
            )
        )
    else:
        print("[compute-all] 本月无金标准，跳过 Hub 对账")
    for channel in PAYOUT_CHANNELS:
        if _has_golden_workbook(config, channel=channel):
            exit_codes.append(
                cmd_reconcile_payout(
                    argparse.Namespace(
                        month=args.month,
                        channel=channel,
                        computed=payout_results[channel]["output_path"],
                        golden=args.golden,
                        sheet=None,
                        report_dir=args.report_dir,
                        verbose=args.verbose,
                    )
                )
            )
        else:
            label = _payout_channel_label(channel)
            print(f"[compute-all] {label} 无金标准，跳过对账")
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
    _add_month_arg(compute)
    compute.set_defaults(func=cmd_compute)

    reconcile = sub.add_parser(
        "reconcile",
        help="仅对账（跳过 compute，读取已有 output/提成汇总.xlsx）",
    )
    reconcile.add_argument("--computed", help="计算生成的 提成汇总.xlsx")
    reconcile.add_argument("--golden", help="金标准工作簿路径")
    reconcile.add_argument("--sheet", default=None)
    reconcile.add_argument("--report-dir", default=None)
    _add_month_arg(reconcile)
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
    _add_month_arg(compute_as)
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
    _add_month_arg(reconcile_as)
    reconcile_as.set_defaults(func=cmd_reconcile_aftersales)

    compute_po = sub.add_parser("compute-payout", help="运行渠道发薪表（XW / 直营店 / CS）")
    compute_po.add_argument(
        "--channel",
        choices=PAYOUT_CHANNELS,
        default="xw",
        help="发薪渠道（默认 xw）",
    )
    compute_po.add_argument("--reconcile", action="store_true")
    compute_po.add_argument(
        "--golden-hub",
        action="store_true",
        help="已废弃：发薪 SUMIF 固定使用 computed 提成汇总",
    )
    compute_po.add_argument("--golden", help="金标准工作簿路径")
    compute_po.add_argument("--sheet", default=None)
    compute_po.add_argument("--report-dir", default=None)
    _add_month_arg(compute_po)
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
    _add_month_arg(reconcile_po)
    reconcile_po.set_defaults(func=cmd_reconcile_payout)

    compute_all = sub.add_parser(
        "compute-all",
        help="端到端：提成汇总 → XW/直营店/CS 发薪（合并计算版 hub + 金标准 W–AR）",
    )
    compute_all.add_argument("--reconcile", action="store_true")
    compute_all.add_argument("--golden", help="金标准工作簿路径")
    compute_all.add_argument("--sheet", default=None)
    compute_all.add_argument("--report-dir", default=None)
    _add_month_arg(compute_all)
    compute_all.set_defaults(func=cmd_compute_all)

    export_perf = sub.add_parser(
        "export-performance-sheet",
        help="导出系统重算的绩效整理表（computed_perf_frame）为 Excel",
    )
    export_perf.add_argument(
        "--output",
        help="输出 xlsx 路径（默认 output/YYYY-MM/绩效整理表-系统生成.xlsx）",
    )
    export_perf.add_argument(
        "--reconcile",
        action="store_true",
        help="导出后与金标准对账并高亮差异/手填格",
    )
    _add_month_arg(export_perf)
    export_perf.set_defaults(func=cmd_export_performance_sheet)

    onboard = sub.add_parser(
        "onboard-month",
        help="注册新账期：生成 month-YYYY-MM.yaml 并写入 months_registry",
    )
    onboard.add_argument("--month", metavar="YYYY-MM", required=True, help="新账期")
    onboard.add_argument("--sales", required=True, help="销售账套 xlsx 路径")
    onboard.add_argument("--rules", help="提成依据 xlsx 路径")
    onboard.add_argument("--sheet-sources", help="sheet_sources.json 路径")
    onboard.add_argument("--label", help="注册表显示名称（默认与 month 相同）")
    topo_group = onboard.add_mutually_exclusive_group(required=False)
    topo_group.add_argument(
        "--extract-topology",
        action="store_true",
        help="从 --sales 提取公式拓扑到 data/topology/<month>/（高级：重建样板）",
    )
    topo_group.add_argument(
        "--inherit-topology",
        metavar="YYYY-MM",
        help="继承指定已注册月份的拓扑 JSON（高级；默认改用 repo 内 2026-05 固化规则）",
    )
    onboard.set_defaults(func=cmd_onboard_month)

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
