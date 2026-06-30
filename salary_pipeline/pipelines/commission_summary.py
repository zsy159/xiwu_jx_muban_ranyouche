from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from salary_pipeline.modules.base import SUMMARY_KEY_COLUMNS, ModuleResult
from salary_pipeline.utils.excel_format import format_writer_sheet

logger = logging.getLogger(__name__)

# Excel 提成汇总表头（与样板月一致，聚合时按列名对齐）
SUMMARY_TEMPLATE_COLUMNS = [
    "序号", "店别", "职务", "姓名", "人数", "考核量", "实际销量", "销量完成率",
    "集客达成率", "加装额", "加装销量完成率", "保险渗透率", "整车毛利", "加装毛利",
    "保险毛利", "按揭毛利", "爱车宝毛利", "上户毛利", "整车+加装（毛利）", "综合毛利",
    "主营单台毛利", "综合单台毛利", "整车绩效", "权限结余绩效", "加装绩效", "保险绩效",
    "金融绩效", "爱车宝绩效", "上户绩效", "盈利产品绩效", "延保提成", "特殊车型+指定车型",
    "座位险提成", "二手车提成", "玻碎险提成", "提成合计", "整车完成考核", "加装完成考核",
    "综合项", "04月活动", "超期", "（已发放奖励）", "交车支出", "保客考核", "考核小计",
    "单台提成", "提成毛利占比", "预算单台", "计提单台", "计提金额",
]


class CommissionSummaryBuilder:
    """
    Aggregate module outputs into the final 提成汇总 table.

    Design rule: 提成汇总 is NEVER imported as input — only produced here.
    """

    def __init__(self, template_columns: list[str] | None = None) -> None:
        self.template_columns = template_columns or SUMMARY_TEMPLATE_COLUMNS

    def build(self, module_results: list[ModuleResult]) -> pd.DataFrame:
        frames = [
            self._normalize_result(result)
            for result in module_results
            if not result.metrics.empty
        ]
        if not frames:
            logger.warning("No module results; returning empty summary skeleton.")
            return pd.DataFrame(columns=self.template_columns)
        combined = frames[0]
        for frame in frames[1:]:
            combined = combined.merge(
                frame,
                on=SUMMARY_KEY_COLUMNS,
                how="outer",
                suffixes=("", "_dup"),
            )
            dup_cols = [c for c in combined.columns if c.endswith("_dup")]
            combined = combined.drop(columns=dup_cols)

        summary = self._align_to_template(combined)
        summary = self._fill_sequence(summary)
        logger.info("Built commission summary shape=%s", summary.shape)
        return summary

    def _normalize_result(self, result: ModuleResult) -> pd.DataFrame:
        metric_cols = [
            c for c in result.metrics.columns if c not in SUMMARY_KEY_COLUMNS
        ]
        frame = result.metrics[SUMMARY_KEY_COLUMNS + metric_cols].copy()
        logger.info(
            "Module %s roles=%s shape=%s metrics=%s",
            result.module_name,
            result.roles,
            frame.shape,
            metric_cols,
        )
        return frame

    def _align_to_template(self, combined: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame()
        for col in self.template_columns:
            if col in combined.columns:
                out[col] = combined[col]
            elif col == "人数":
                out[col] = 1
            else:
                out[col] = pd.NA
        for col in combined.columns:
            if col.startswith("_") and col not in out.columns:
                out[col] = combined[col]
        return out

    def _fill_sequence(self, summary: pd.DataFrame) -> pd.DataFrame:
        if "序号" in summary.columns:
            summary["序号"] = range(1, len(summary) + 1)
        return summary

    def export_excel(
        self,
        summary: pd.DataFrame,
        output_path: Path,
        sheet_name: str = "提成汇总",
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            title = pd.DataFrame([[sheet_name]], columns=[sheet_name])
            title.to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=0)
            summary.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)
            format_writer_sheet(
                writer, sheet_name, summary.columns, header_row=2
            )
        logger.info("Exported commission summary -> %s", output_path)
        return output_path


def load_month_config(config_dir: Path) -> dict[str, Any]:
    path = config_dir / "month.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)
