from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.ops.basic import ratio_with_cap, sumif_by_key

logger = logging.getLogger(__name__)

TASK_SHEET = "销售任务及完成率"

F_SUMIF = re.compile(
    r"^=SUMIF\(\s*销售任务及完成率!C:C\s*,\s*D(\d+)\s*,\s*销售任务及完成率!Y:Y\s*\)$",
    re.IGNORECASE,
)
G_SUMIF = re.compile(
    r"^=SUMIF\(\s*销售任务及完成率!C:C\s*,\s*D(\d+)\s*,\s*销售任务及完成率!Z:Z\s*\)$",
    re.IGNORECASE,
)
F_CELL = re.compile(r"^=销售任务及完成率!([YZ]\d+)$", re.IGNORECASE)
H_RATIO_120 = re.compile(
    r"^=IF\(F(\d+)<>0,IF\(G\1/F\1>120%,120%,G\1/F\1\),0\)$",
    re.IGNORECASE,
)
H_RATIO_110 = re.compile(
    r"^=IF\(F(\d+)<>0,IF\(G\1/F\1>110%,110%,G\1/F\1\),0\)$",
    re.IGNORECASE,
)


class HubTaskMetricsCalculator:
    """Fill 提成汇总 columns 考核量 / 实际销量 / 销量完成率 from 销售任务及完成率."""

    def __init__(self, topology_path: Path, workbook_loader: WorkbookLoader) -> None:
        self.topology_path = topology_path
        self.loader = workbook_loader
        self.cells = json.loads(topology_path.read_text(encoding="utf-8"))["cells"]
        self.task_frame = workbook_loader.read_sales_task_sheet()

    def apply(self, summary: pd.DataFrame) -> pd.DataFrame:
        if summary.empty:
            return summary

        out = summary.copy()
        if "_excel_row" not in out.columns:
            raise ValueError("summary missing _excel_row for formula row mapping")

        f_values: dict[int, float] = {}
        g_values: dict[int, float] = {}

        for idx, row in out.iterrows():
            excel_row = int(row["_excel_row"])
            name = row.get("姓名")
            f_values[excel_row] = self._eval_f(excel_row, name)
            g_values[excel_row] = self._eval_g(excel_row, name)

        out["考核量"] = [
            f_values.get(int(r), pd.NA) for r in out["_excel_row"]
        ]
        out["实际销量"] = [
            g_values.get(int(r), pd.NA) for r in out["_excel_row"]
        ]
        out["销量完成率"] = [
            self._eval_h(int(r), f_values, g_values) for r in out["_excel_row"]
        ]

        filled = out["考核量"].notna().sum()
        logger.info(
            "Hub task metrics applied: 考核量 filled=%s / %s rows",
            filled,
            len(out),
        )
        return out.drop(columns=["_excel_row"], errors="ignore")

    def _formula(self, sheet_row: int, col: str) -> str | None:
        key = f"提成汇总!{col}{sheet_row}"
        info = self.cells.get(key)
        return info.get("formula") if info else None

    def _eval_f(self, excel_row: int, name: Any) -> float | None:
        formula = self._formula(excel_row, "F")
        if not formula:
            return None
        match = F_SUMIF.match(formula)
        if match:
            return float(sumif_by_key(self.task_frame, "姓名", "考核量", str(name)))
        match = F_CELL.match(formula)
        if match:
            value = self.loader.read_cell_value(TASK_SHEET, match.group(1))
            return float(value) if value is not None and not pd.isna(value) else 0.0
        return None

    def _eval_g(self, excel_row: int, name: Any) -> float | None:
        formula = self._formula(excel_row, "G")
        if not formula:
            return None
        if G_SUMIF.match(formula):
            return float(sumif_by_key(self.task_frame, "姓名", "实际销量", str(name)))
        return None

    def _eval_h(
        self,
        excel_row: int,
        f_values: dict[int, float],
        g_values: dict[int, float],
    ) -> float | None:
        formula = self._formula(excel_row, "H")
        if not formula:
            return None
        cap = None
        if H_RATIO_120.match(formula):
            cap = 1.2
        elif H_RATIO_110.match(formula):
            cap = 1.1
        else:
            return None
        f_val = f_values.get(excel_row, 0.0)
        g_val = g_values.get(excel_row, 0.0)
        return float(ratio_with_cap(g_val, f_val, cap=cap))
