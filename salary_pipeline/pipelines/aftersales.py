from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, load_month_config
from salary_pipeline.modules.aftersales_skeleton import read_aftersales_skeleton
from salary_pipeline.paths import CONFIG_DIR, resolve_project_path
from salary_pipeline.utils.excel_format import format_writer_sheet
from salary_pipeline.pipelines.aftersales_formula_engine import (
    AIRPORT_CONFIG,
    WUHOU_CONFIG,
    AftersalesFormulaEngine,
)

logger = logging.getLogger(__name__)

AFTER_SALES_TEMPLATE_COLUMNS = list(WUHOU_CONFIG.column_map.values())
AFTER_SALES_EXPORT_COLUMNS = ["店别", "姓名", *AFTER_SALES_TEMPLATE_COLUMNS]


class AftersalesPipeline:
    """售后账套：武侯 / 机场门店提成表。"""

    STORE_CONFIGS = {
        "wuhou": WUHOU_CONFIG,
        "airport": AIRPORT_CONFIG,
    }

    def __init__(self, config_dir: Path | None = None, store: str = "wuhou") -> None:
        self.config_dir = config_dir or CONFIG_DIR
        self.month_config = load_month_config(self.config_dir)
        self.store = store
        self.engine_config = self.STORE_CONFIGS[store]

    def run(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        ctx["month_config"] = self.month_config

        after_cfg = self.month_config.get("aftersales", {})
        golden_path = resolve_project_path(self.month_config["workbooks"]["aftersales"])
        skeleton = read_aftersales_skeleton(
            golden_path,
            self.engine_config.anchor_sheet,
            data_start_row=int(after_cfg.get("data_start_row", 5)),
        )

        loader = WorkbookLoader(golden_path)
        topology_path = resolve_project_path(self.month_config["topology"]["aftersales"])
        engine = AftersalesFormulaEngine(topology_path, loader, self.engine_config)
        result = engine.apply(skeleton)

        output_key = f"aftersales_{self.store}"
        rel_path = self.month_config["outputs"].get(
            output_key,
            f"output/{self.month_config['month']}/{self.engine_config.anchor_sheet}.xlsx",
        )
        output_path = resolve_project_path(rel_path)
        self._export(result, output_path, self.engine_config.anchor_sheet)

        if engine.warnings:
            report_dir = resolve_project_path(
                self.month_config["outputs"]["report_dir"]
            )
            report_dir.mkdir(parents=True, exist_ok=True)
            warn_path = report_dir / f"formula_warnings_{self.store}.txt"
            warn_path.write_text("\n".join(engine.warnings), encoding="utf-8")
            logger.info("Wrote formula warnings -> %s", warn_path)

        return {
            "summary": result,
            "output_path": output_path,
            "warnings": engine.warnings,
            "store": self.store,
        }

    def _export(self, frame: pd.DataFrame, path: Path, sheet_name: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        export = pd.DataFrame(columns=AFTER_SALES_EXPORT_COLUMNS)
        for col in AFTER_SALES_EXPORT_COLUMNS:
            export[col] = frame[col] if col in frame.columns else pd.NA
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            title = pd.DataFrame([[sheet_name]], columns=[sheet_name])
            title.to_excel(
                writer, sheet_name=sheet_name, index=False, header=False, startrow=0
            )
            export.to_excel(writer, sheet_name=sheet_name, index=False, startrow=3)
            format_writer_sheet(
                writer, sheet_name, export.columns, header_row=4
            )
        logger.info("Exported aftersales -> %s shape=%s", path, export.shape)
