"""Promote staging outputs to formal paths and register month."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from salary_pipeline.ingestion_upload.archive import archive_month_uploads
from salary_pipeline.ingestion_upload.month_config import write_month_config
from salary_pipeline.ingestion_upload.sheet_merge import prepend_generated_sheets
from salary_pipeline.observability.loaders import register_month
from salary_pipeline.paths import PROJECT_ROOT, output_month_dir, raw_month_dir

logger = logging.getLogger(__name__)


def promote_staging(
    month_id: str,
    *,
    staging_dir: Path,
    consolidated_workbook: Path,
    original_uploads: list[Path],
    rules_workbook: Path | None = None,
    topology_rel: str,
) -> dict[str, Path]:
    """
    Archive originals, copy consolidated + outputs to formal locations,
    prepend generated sheets to archived workbook, register month.
    """
    archive_month_uploads(month_id, original_uploads)

    raw_dir = raw_month_dir(month_id)
    raw_dir.mkdir(parents=True, exist_ok=True)

    formal_sales = raw_dir / consolidated_workbook.name
    shutil.copy2(consolidated_workbook, formal_sales)

    if rules_workbook and rules_workbook.exists():
        formal_rules = raw_dir / rules_workbook.name
        shutil.copy2(rules_workbook, formal_rules)
        rules_rel = str(formal_rules.relative_to(PROJECT_ROOT))
    else:
        rules_rel = None

    sales_rel = str(formal_sales.relative_to(PROJECT_ROOT))

    write_month_config(
        month_id,
        sales_workbook=sales_rel,
        rules_workbook=rules_rel,
        sales_topology=topology_rel,
        rules_topology=topology_rel,
        staging=False,
    )

    out_dir = output_month_dir(month_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    promoted: dict[str, Path] = {}
    staging_commission = staging_dir / "提成汇总.xlsx"
    staging_perf = staging_dir / "绩效整理表-系统生成.xlsx"

    if staging_commission.exists():
        dest = out_dir / staging_commission.name
        shutil.copy2(staging_commission, dest)
        promoted["commission_summary"] = dest

    if staging_perf.exists():
        dest = out_dir / staging_perf.name
        shutil.copy2(staging_perf, dest)
        promoted["performance_sheet"] = dest

    staging_cache = staging_dir / "cache"
    if staging_cache.exists():
        formal_cache = out_dir / "cache"
        if formal_cache.exists():
            shutil.rmtree(formal_cache)
        shutil.copytree(staging_cache, formal_cache)
        promoted["cache"] = formal_cache

    staging_reports = staging_dir / "reports"
    if staging_reports.exists():
        formal_reports = out_dir / "reports"
        formal_reports.mkdir(parents=True, exist_ok=True)
        for item in staging_reports.iterdir():
            dest = formal_reports / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        promoted["reports"] = formal_reports

    overrides_src = staging_dir / "overrides.json"
    if overrides_src.exists():
        shutil.copy2(overrides_src, out_dir / "overrides.json")

    generated: dict[str, Path] = {}
    if staging_commission.exists():
        generated["提成汇总"] = staging_commission
    if staging_perf.exists():
        generated["绩效整理表"] = staging_perf

    if generated:
        merged_path = raw_dir / f"{formal_sales.stem}-含系统生成.xlsx"
        prepend_generated_sheets(formal_sales, generated, output_path=merged_path)
        promoted["merged_workbook"] = merged_path

    register_month(month_id, label=month_id, raw_dir=f"data/raw/{month_id}")
    logger.info("Promoted staging for %s -> %s", month_id, out_dir)
    return promoted
