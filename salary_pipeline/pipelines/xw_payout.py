from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, load_month_config
from salary_pipeline.data_ingestion.hub_frame_loader import build_hub_sumif_frame
from salary_pipeline.modules.payout_skeleton import read_payout_skeleton
from salary_pipeline.paths import CONFIG_DIR, resolve_project_path
from salary_pipeline.utils.excel_format import format_writer_sheet
from salary_pipeline.pipelines.xw_payout_formula_engine import (
    PAYOUT_CHANNEL_COLUMN_MAPS,
    PAYOUT_CHANNEL_CONFIGS,
    XwPayoutEngineConfig,
    XwPayoutFormulaEngine,
)

logger = logging.getLogger(__name__)

CHANNEL_OUTPUT_KEYS = {
    "xw": "xw_payout",
    "direct_store": "direct_store_payout",
    "cs": "cs_payout",
}

CHANNEL_WARN_FILES = {
    "xw": "formula_warnings_xw_payout.txt",
    "direct_store": "formula_warnings_direct_store_payout.txt",
    "cs": "formula_warnings_cs_payout.txt",
}

CHANNEL_DEFAULT_OUTPUTS = {
    "xw": "XW提成-发.xlsx",
    "direct_store": "直营店提成-发.xlsx",
    "cs": "CS提成-发.xlsx",
}


def payout_export_columns(column_map: dict[str, str]) -> list[str]:
    return ["店别", "职务", "姓名", *column_map.values()]


class ChannelPayoutPipeline:
    """Multi-channel final payout sheets (XW / 直营店 / CS)."""

    def __init__(
        self,
        channel: str = "xw",
        config_dir: Path | None = None,
    ) -> None:
        if channel not in PAYOUT_CHANNEL_CONFIGS:
            raise ValueError(
                f"Unknown payout channel {channel!r}; "
                f"expected one of {sorted(PAYOUT_CHANNEL_CONFIGS)}"
            )
        self.channel = channel
        self.config_dir = config_dir or CONFIG_DIR
        self.month_config = load_month_config(self.config_dir)
        self.engine_config: XwPayoutEngineConfig = PAYOUT_CHANNEL_CONFIGS[channel]
        self.column_map = PAYOUT_CHANNEL_COLUMN_MAPS[channel]

    def run(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        payout_cfg = self.month_config.get("payout", {})
        channel_cfg = payout_cfg.get(self.channel, {})
        data_start_row = int(payout_cfg.get("data_start_row", 3))
        sheet = channel_cfg.get("anchor_sheet", self.engine_config.anchor_sheet)
        golden_path = resolve_project_path(
            channel_cfg.get("golden_workbook") or self.month_config["workbooks"]["sales"]
        )

        hub_computed = None
        if context.get("use_computed_hub"):
            hub_computed = context.get("hub_path")
            if hub_computed is None:
                hub_rel = self.month_config["outputs"].get("commission_summary_file")
                hub_computed = resolve_project_path(hub_rel) if hub_rel else None

        hub_frame = build_hub_sumif_frame(
            golden_path,
            computed_workbook=hub_computed,
            data_start_row=int(self.month_config.get("parity", {}).get("data_start_row", 3)),
        )

        skeleton = read_payout_skeleton(golden_path, sheet, data_start_row=data_start_row)
        loader = WorkbookLoader(golden_path)
        topology_path = resolve_project_path(self.month_config["topology"]["sales"])
        engine = XwPayoutFormulaEngine(
            topology_path,
            loader,
            self.engine_config,
            hub_frame=hub_frame,
        )
        result = engine.apply(skeleton)

        output_key = CHANNEL_OUTPUT_KEYS[self.channel]
        default_name = CHANNEL_DEFAULT_OUTPUTS[self.channel]
        rel_path = self.month_config["outputs"].get(
            output_key,
            f"output/{self.month_config['month']}/{default_name}",
        )
        output_path = resolve_project_path(rel_path)
        self._export(result, output_path, sheet)

        if engine.warnings:
            report_dir = resolve_project_path(
                self.month_config["outputs"]["report_dir"]
            )
            report_dir.mkdir(parents=True, exist_ok=True)
            warn_path = report_dir / CHANNEL_WARN_FILES[self.channel]
            warn_path.write_text("\n".join(engine.warnings), encoding="utf-8")

        return {
            "channel": self.channel,
            "summary": result,
            "output_path": output_path,
            "warnings": engine.warnings,
        }

    def _export(self, frame: pd.DataFrame, path: Path, sheet_name: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = payout_export_columns(self.column_map)
        export = pd.DataFrame(columns=columns)
        for col in columns:
            export[col] = frame[col] if col in frame.columns else pd.NA
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            title = pd.DataFrame([[sheet_name]], columns=[sheet_name])
            title.to_excel(
                writer, sheet_name=sheet_name, index=False, header=False, startrow=0
            )
            export.to_excel(writer, sheet_name=sheet_name, index=False, startrow=2)
            format_writer_sheet(
                writer, sheet_name, export.columns, header_row=3
            )
        logger.info(
            "Exported %s payout -> %s shape=%s", self.channel, path, export.shape
        )


class XwPayoutPipeline(ChannelPayoutPipeline):
    """西物渠道最终发薪表 XW提成-发。"""

    def __init__(self, config_dir: Path | None = None) -> None:
        super().__init__(channel="xw", config_dir=config_dir)
