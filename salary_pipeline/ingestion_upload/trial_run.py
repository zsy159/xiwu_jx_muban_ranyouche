"""Trial compute: SalesPipeline to staging output with preview payload."""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from salary_pipeline.ingestion_upload.progress import TrialProgressReporter
from salary_pipeline.ingestion_upload.month_config import (
    load_written_month_config,
    write_month_config,
)
from salary_pipeline.ingestion_upload.sheet_merge import load_sheet_sources
from salary_pipeline.paths import PROJECT_ROOT, output_month_dir, resolve_project_path
from salary_pipeline.pipelines.performance_sheet_export import (
    export_computed_performance_sheet,
    prepare_export_frame,
)
from salary_pipeline.pipelines.run_cache import (
    cache_is_valid,
    compute_input_fingerprint,
    read_manifest,
    resolve_cache_dir,
)
from salary_pipeline.pipelines.sales import SalesPipeline

logger = logging.getLogger(__name__)

StageCallback = Callable[[str], None]
ProgressCallback = Callable[[str, str], None]
CacheSource = Literal["staging", "formal"] | None

# Honest UX hints (minutes); incremental assumes hub cache hit.
ESTIMATED_FULL_MINUTES = "8–12"
ESTIMATED_INCREMENTAL_MINUTES = "2–5"


@dataclass
class TrialCacheStatus:
    """Pre-run cache availability for upload UI."""

    staging_valid: bool = False
    formal_valid: bool = False
    staging_reason: str = ""
    formal_reason: str = ""
    recommended_from_stage: str = "full"
    cache_source: CacheSource = None
    message: str = "首次全量试算"

    @property
    def incremental_available(self) -> bool:
        return self.staging_valid or self.formal_valid

    def timing_hint(self) -> str:
        if self.incremental_available:
            return (
                f"首次全量约 {ESTIMATED_FULL_MINUTES} 分钟；"
                f"输入未变时增量约 {ESTIMATED_INCREMENTAL_MINUTES} 分钟"
            )
        return f"首次全量约 {ESTIMATED_FULL_MINUTES} 分钟（完成后再次试算可增量）"


@dataclass
class TrialRunResult:
    month_id: str
    staging_dir: Path
    config_path: Path
    commission_summary_path: Path | None = None
    performance_sheet_path: Path | None = None
    summary_preview: pd.DataFrame = field(default_factory=pd.DataFrame)
    performance_preview: pd.DataFrame = field(default_factory=pd.DataFrame)
    pipeline_result: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    from_stage: str = "full"
    cache_source: CacheSource = None
    cache_message: str = ""
    elapsed_seconds: float = 0.0


def inspect_trial_cache(month_config: dict[str, Any]) -> TrialCacheStatus:
    """Check staging / formal hub caches without mutating disk."""
    fp = compute_input_fingerprint(month_config)
    staging_cache = resolve_cache_dir(month_config)
    staging_manifest = read_manifest(staging_cache)
    staging_valid, staging_reason = cache_is_valid(
        staging_manifest, fp, scope="hub", cache_dir=staging_cache
    )

    month_id = month_config.get("month", "")
    formal_valid = False
    formal_reason = ""
    if month_id:
        formal_cache = output_month_dir(month_id) / "cache"
        formal_manifest = read_manifest(formal_cache)
        formal_valid, formal_reason = cache_is_valid(
            formal_manifest, fp, scope="hub", cache_dir=formal_cache
        )

    if staging_valid:
        return TrialCacheStatus(
            staging_valid=True,
            formal_valid=formal_valid,
            staging_reason=staging_reason,
            formal_reason=formal_reason,
            recommended_from_stage="hub",
            cache_source="staging",
            message="staging 缓存可用，将增量试算",
        )
    if formal_valid:
        return TrialCacheStatus(
            staging_valid=False,
            formal_valid=True,
            staging_reason=staging_reason,
            formal_reason=formal_reason,
            recommended_from_stage="hub",
            cache_source="formal",
            message="可复用正式目录 Hub 缓存，将增量试算",
        )
    return TrialCacheStatus(
        staging_valid=False,
        formal_valid=formal_valid,
        staging_reason=staging_reason,
        formal_reason=formal_reason,
        recommended_from_stage="full",
        cache_source=None,
        message="全量试算（首次或输入已变更）",
    )


def bootstrap_staging_cache_from_formal(
    month_id: str,
    staging_cache_dir: Path,
    current_fingerprint: dict[str, str],
) -> tuple[bool, str]:
    """Copy formal output/<月>/cache into staging when fingerprints match."""
    formal_cache = output_month_dir(month_id) / "cache"
    manifest = read_manifest(formal_cache)
    valid, reason = cache_is_valid(
        manifest, current_fingerprint, scope="hub", cache_dir=formal_cache
    )
    if not valid:
        return False, reason

    staging_cache_dir.parent.mkdir(parents=True, exist_ok=True)
    if staging_cache_dir.exists():
        shutil.rmtree(staging_cache_dir)
    shutil.copytree(formal_cache, staging_cache_dir)
    logger.info("Bootstrapped staging cache from formal %s", formal_cache)
    return True, "reused formal hub cache"


def resolve_trial_from_stage(
    month_config: dict[str, Any],
) -> tuple[str, CacheSource, str]:
    """
    Pick pipeline from_stage for trial run.

    Returns (from_stage, cache_source, human message).
    """
    status = inspect_trial_cache(month_config)
    if status.recommended_from_stage == "hub":
        if status.cache_source == "staging":
            return "hub", "staging", status.message
        if status.cache_source == "formal":
            staging_cache = resolve_cache_dir(month_config)
            fp = compute_input_fingerprint(month_config)
            month_id = month_config.get("month", "")
            ok, _ = bootstrap_staging_cache_from_formal(month_id, staging_cache, fp)
            if ok:
                return "hub", "formal", status.message
    return "full", None, status.message


def run_trial_compute(
    month_id: str,
    consolidated_workbook: Path,
    *,
    rules_workbook: Path | None = None,
    topology_rel: str | Path,
    config_dir: Path | None = None,
    sheet_sources_path: Path | None = None,
    on_stage: StageCallback | None = None,
    progress_callback: ProgressCallback | None = None,
    progress_reporter: TrialProgressReporter | None = None,
    export_performance_sheet: bool = True,
) -> TrialRunResult:
    """
    Clean + trial SalesPipeline run writing to output/<month>/.staging/.

  When hub snapshot cache is valid (staging or formal), uses from_stage="hub"
  for ~2–5 min incremental preview instead of full ~8–12 min run.
    """
    def _progress(stage_key: str, label: str) -> None:
        if progress_reporter is not None:
            progress_reporter.report(stage_key, label)
        if progress_callback is not None:
            progress_callback(stage_key, label)
        if on_stage is not None:
            on_stage(label)

    consolidated_rel = _relative(consolidated_workbook)
    rules_rel = _relative(rules_workbook) if rules_workbook else None
    topo_rel = str(topology_rel)
    sources_rel = _relative(sheet_sources_path) if sheet_sources_path else None

    _progress("check_cache", "准备账期配置…")
    config_path = write_month_config(
        month_id,
        sales_workbook=consolidated_rel,
        rules_workbook=rules_rel,
        sales_topology=topo_rel,
        rules_topology=topo_rel if rules_rel else None,
        sheet_sources_file=sources_rel,
        staging=True,
        config_dir=config_dir,
    )
    month_config = load_written_month_config(month_id)

    staging_dir = resolve_project_path(
        month_config["outputs"]["commission_summary_file"]
    ).parent

    result = TrialRunResult(
        month_id=month_id,
        staging_dir=staging_dir,
        config_path=config_path,
    )

    t0 = time.perf_counter()
    try:
        _progress("check_cache", "检查 Hub 缓存…")
        from_stage, cache_source, cache_message = resolve_trial_from_stage(month_config)
        result.from_stage = from_stage
        result.cache_source = cache_source
        result.cache_message = cache_message
        if progress_reporter is not None:
            progress_reporter.set_mode(
                "incremental" if from_stage == "hub" else "full"
            )

        pipeline = SalesPipeline(config_dir=config_path.parent, month_config=month_config)
        sheet_sources = load_sheet_sources(sheet_sources_path)
        if not sheet_sources and month_config.get("workbooks", {}).get(
            "sheet_sources_file"
        ):
            sheet_sources = load_sheet_sources(
                resolve_project_path(
                    month_config["workbooks"]["sheet_sources_file"]
                )
            )
        ctx: dict[str, Any] = {
            "month_config": month_config,
            "sheet_sources": sheet_sources,
            "progress_callback": _progress,
        }

        pipeline_result = pipeline.run(context=ctx, from_stage=from_stage)
        result.pipeline_result = pipeline_result

        summary_path = resolve_project_path(
            month_config["outputs"]["commission_summary_file"]
        )
        result.commission_summary_path = summary_path
        result.summary_preview = pipeline_result["summary"].copy()

        computed_perf = pipeline_result.get("computed_perf_frame")
        if computed_perf is not None and not computed_perf.empty:
            result.performance_preview = prepare_export_frame(computed_perf)
            if export_performance_sheet:
                _progress("export_preview", "导出绩效整理表预览…")
                perf_path = resolve_project_path(
                    month_config["outputs"]["performance_sheet_file"]
                )
                title = f"{month_id} 销售绩效整理表（系统生成）"
                export_computed_performance_sheet(computed_perf, perf_path, title=title)
                result.performance_sheet_path = perf_path
        else:
            result.errors.append("绩效整理表未生成（检查明细输入是否齐全）")

        if progress_reporter is not None:
            progress_reporter.complete("试算完成")

    except Exception as exc:
        logger.exception("Trial compute failed")
        result.errors.append(str(exc))

    result.elapsed_seconds = time.perf_counter() - t0
    return result


def _relative(path: Path) -> str:
    path = Path(path)
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)
