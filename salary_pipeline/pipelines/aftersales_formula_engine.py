from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name
from salary_pipeline.ops.basic import sumif_by_key
from salary_pipeline.ops.lookup import lookup_match_index
from salary_pipeline.pipelines.hub_formula_engine import (
    CELL_REF,
    SHEET_CELL,
    SUMIF_SIMPLE,
    SUM_RE,
    HubFormulaEngine,
    _column_letters,
)

logger = logging.getLogger(__name__)

BASIC_SHEET = "05基本"
BIZ_SHEET = "05月业务提成"
OTHER_DEPT_SHEET = "05月其他部门提成"
WORKSHOP_SHEET = "05月车间提成"
BAR_SHEET = "吧台提成"
INSURANCE_EXT_SHEET = "保险专员5月外拓"
ASSESS_SHEET = "综合考核"
CLOTHING_SHEET = "服装扣款"
FUND_SHEET = "超市公积金"
PAINT_SHEET = "钣喷中心"
XW_FUND_SHEET = "西物公积金"

WUHOU_COLUMN_MAP: dict[str, str] = {
    "D": "其他补贴",
    "E": "单位社保",
    "F": "个人社保",
    "G": "个人公积金",
    "H": "其它",
    "I": "基本工资",
    "J": "其中：加班工资",
    "K": "当月应计提绩效",
    "L": "综合考核/其他",
    "M": "应付提成工资",
    "N": "代扣社保",
    "O": "实付提成",
    "P": "其它_P",
    "Q": "已发并税",
    "R": "计税工资",
    "S": "代扣个税",
    "T": "已扣税",
    "U": "实际扣税",
    "V": "其他(代扣项)",
    "W": "实发提成",
}

AIRPORT_COLUMN_MAP = dict(WUHOU_COLUMN_MAP)

INDEX_TERM = re.compile(
    r"INDEX\("
    r"(?:'(?P<qsheet>[^']+)'|(?P<usheet>[^'!]+))!"
    r"(?P<vcol>[A-Z]{1,3}):(?P=vcol),"
    r"MATCH\("
    r"(?P<kref>[A-Z]{1,3}\d+),"
    r"(?:'(?P<qsheet3>[^']+)'|(?P<usheet3>[^'!]+))!"
    r"(?P<kcol>[A-Z]{1,3}):(?P=kcol),0\)\)",
    re.IGNORECASE,
)
LOCAL_INDEX = re.compile(
    r"^=INDEX\((?P<vcol>[A-Z]{1,3}):(?P=vcol),MATCH\((?P<kref>[A-Z]{1,3}\d+),(?P<kcol>[A-Z]{1,3}):(?P=kcol),0\)\)$",
    re.IGNORECASE,
)
SUB_CELLS = re.compile(r"^=([A-Z]{1,3})(\d+)-([A-Z]{1,3})(\d+)$", re.IGNORECASE)
ADD3_CELLS = re.compile(
    r"^=([A-Z]{1,3})(\d+)\+([A-Z]{1,3})(\d+)\+([A-Z]{1,3})(\d+)$",
    re.IGNORECASE,
)
SUB3_CELLS = re.compile(
    r"^=([A-Z]{1,3})(\d+)-([A-Z]{1,3})(\d+)-([A-Z]{1,3})(\d+)$",
    re.IGNORECASE,
)


@dataclass
class AftersalesEngineConfig:
    anchor_sheet: str
    column_map: dict[str, str]
    name_key_letter: str = "C"
    sheet_frames: dict[str, list[str]] = field(default_factory=dict)


WUHOU_CONFIG = AftersalesEngineConfig(
    anchor_sheet="05月提成-武侯售后",
    column_map=WUHOU_COLUMN_MAP,
    sheet_frames={
        BASIC_SHEET: ["C", "I", "J", "K", "L", "M", "P", "AA", "AB", "AC", "AF"],
        BIZ_SHEET: ["B", "BO"],
        OTHER_DEPT_SHEET: ["C", "Q"],
        WORKSHOP_SHEET: ["B", "C", "W", "M"],
        BAR_SHEET: ["B", "M"],
        INSURANCE_EXT_SHEET: ["A", "I"],
        ASSESS_SHEET: ["A", "M", "N"],
        CLOTHING_SHEET: ["C", "N"],
        FUND_SHEET: ["C", "I"],
    },
)

AIRPORT_CONFIG = AftersalesEngineConfig(
    anchor_sheet="05月提成-机场售后",
    column_map=AIRPORT_COLUMN_MAP,
    sheet_frames={
        **WUHOU_CONFIG.sheet_frames,
        PAINT_SHEET: ["C", "N"],
        XW_FUND_SHEET: ["C", "I"],
    },
)


def _col_to_index(letter: str) -> int:
    value = 0
    for char in letter.upper():
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value


def _index_to_col(index: int) -> str:
    chars: list[str] = []
    while index:
        index, rem = divmod(index - 1, 26)
        chars.append(chr(ord("A") + rem))
    return "".join(reversed(chars))


class AftersalesFormulaEngine(HubFormulaEngine):
    """Evaluate aftersales anchor sheet formulas (武侯 / 机场)."""

    def __init__(
        self,
        topology_path: Path,
        loader: WorkbookLoader,
        config: AftersalesEngineConfig,
    ) -> None:
        self.config = config
        self.anchor_sheet = config.anchor_sheet
        self.column_map = config.column_map
        self.name_key_letter = config.name_key_letter

        topo = json.loads(topology_path.read_text(encoding="utf-8"))
        self.cells = topo["cells"]
        allowed = set(config.column_map)
        self.execution_order = [
            key
            for key in topo["execution_order"]
            if key.startswith(f"{self.anchor_sheet}!")
            and _column_letters(key.split("!", 1)[1]) in allowed
        ]
        self.loader = loader
        self.values: dict[str, float] = {}
        self.warnings: list[str] = []
        self._sheet_cache: dict[str, pd.DataFrame] = {}
        self._row_names: dict[int, str] = {}
        self._name_tax_lookup: pd.Series = pd.Series(dtype=float)

    def apply(self, summary: pd.DataFrame) -> pd.DataFrame:
        if summary.empty or "_excel_row" not in summary.columns:
            raise ValueError("summary requires _excel_row column")

        self._row_names = {
            int(row["_excel_row"]): normalize_name(row.get("姓名"))
            for _, row in summary.iterrows()
        }
        self.values.clear()
        self.warnings.clear()
        self._bootstrap_static_columns()

        for _pass in range(10):
            before = len(self.values)
            for full_key in self.execution_order:
                formula = self.cells[full_key].get("formula", "")
                if "#REF!" in formula.upper():
                    if _pass == 0:
                        self.warnings.append(f"skip #REF!: {full_key} {formula}")
                    continue
                coord = full_key.split("!", 1)[1].upper()
                row_num = int(re.search(r"\d+", coord).group())
                name = self._row_names.get(row_num)
                try:
                    value = self._eval_aftersales(formula, row_num, name)
                except Exception as exc:
                    if _pass == 0:
                        self.warnings.append(f"eval fail {full_key}: {exc}")
                    continue
                if value is not None:
                    self.values[coord] = 0.0 if pd.isna(value) else float(value)
            if len(self.values) == before:
                break

        out = summary.copy()
        for idx, row in out.iterrows():
            excel_row = int(row["_excel_row"])
            for letter, col_name in self.column_map.items():
                key = f"{letter}{excel_row}"
                if key in self.values:
                    out.at[idx, col_name] = self.values[key]
            if "店别" in row:
                out.at[idx, "店别"] = row["店别"]
            if "姓名" in row:
                out.at[idx, "姓名"] = row["姓名"]

        logger.info(
            "Aftersales engine [%s]: computed=%s warnings=%s",
            self.anchor_sheet,
            len(self.values),
            len(self.warnings),
        )
        return out.drop(columns=["_excel_row"], errors="ignore")

    def _eval_aftersales(self, formula: str, row: int, name: Any) -> float | None:
        formula = formula.strip()
        if not formula.startswith("="):
            return None

        body = formula[1:]
        if "INDEX(" in body.upper():
            if "+" in body:
                return self._eval_index_sum(body, row, name)
            m = LOCAL_INDEX.match(formula)
            if m:
                return self._eval_local_index(m, row, name)
            m = INDEX_TERM.search(body)
            if m:
                return self._lookup_index_term(m, row, name)

        m = SUB3_CELLS.match(formula)
        if m:
            a = self._cell(f"{m.group(1).upper()}{m.group(2)}")
            b = self._cell(f"{m.group(3).upper()}{m.group(4)}")
            c = self._cell(f"{m.group(5).upper()}{m.group(6)}")
            return a - b - c

        m = ADD3_CELLS.match(formula)
        if m:
            return sum(
                self._cell(f"{m.group(i).upper()}{m.group(i+1)}")
                for i in (1, 3, 5)
            )

        m = SUB_CELLS.match(formula)
        if m:
            return self._cell(f"{m.group(1).upper()}{m.group(2)}") - self._cell(
                f"{m.group(3).upper()}{m.group(4)}"
            )

        return self._eval(formula, row, name)

    def _eval_index_sum(self, body: str, row: int, name: Any) -> float:
        total = 0.0
        for term in body.split("+"):
            term = term.strip()
            m = INDEX_TERM.search(term)
            if not m:
                continue
            total += self._lookup_index_term(m, row, name)
        return total

    def _lookup_index_term(self, m: re.Match[str], row: int, name: Any) -> float:
        value_sheet = (m.group("qsheet") or m.group("usheet") or "").strip()
        vcol = m.group("vcol").upper()
        key_sheet = (m.group("qsheet3") or m.group("usheet3") or value_sheet).strip()
        kcol = m.group("kcol").upper()
        kref = m.group("kref").upper()
        lookup_name = self._resolve_key_ref(kref, row, name)
        if key_sheet:
            frame = self._aftersales_frame(key_sheet)
            key_series = frame[kcol].map(normalize_name)
            return float(
                lookup_match_index(
                    pd.Series([lookup_name]),
                    key_series,
                    frame[vcol],
                ).iloc[0]
            )
        keys = self._same_sheet_keys()
        values = self._same_sheet_column(vcol)
        indexed = pd.Series(values, index=keys)
        key = normalize_name(lookup_name)
        return float(indexed.get(key, 0.0)) if key in indexed.index else 0.0

    def _eval_local_index(self, m: re.Match[str], row: int, name: Any) -> float:
        vcol = m.group("vcol").upper()
        kcol = m.group("kcol").upper()
        kref = m.group("kref").upper()
        lookup_name = self._resolve_key_ref(kref, row, name)
        if kcol == "AB" and vcol == "AC":
            key = normalize_name(lookup_name)
            if key in self._name_tax_lookup.index:
                return float(self._name_tax_lookup.loc[key])
            return 0.0
        keys = self._same_sheet_keys()
        values = self._same_sheet_column(vcol)
        series = pd.Series(values, index=keys)
        key = normalize_name(lookup_name)
        return float(series.get(key, 0.0)) if key in series.index else 0.0

    def _bootstrap_static_columns(self) -> None:
        """Preload AB/AC tax lookup table and per-row T (已扣税) from golden sheet."""
        raw = self.loader.read_sheet_columns(
            self.anchor_sheet,
            {"AB": "AB", "AC": "AC", "T": "T"},
            label=f"{self.anchor_sheet}!AB:AC",
        )
        names = raw["AB"].map(normalize_name)
        amounts = pd.to_numeric(raw["AC"], errors="coerce")
        lookup = pd.Series(amounts.values, index=names)
        self._name_tax_lookup = lookup[~lookup.index.isna()].groupby(level=0).last()

        t_series = pd.to_numeric(raw["T"], errors="coerce")
        for excel_row in self._row_names:
            idx = excel_row - 1
            if 0 <= idx < len(t_series) and not pd.isna(t_series.iloc[idx]):
                self.values[f"T{excel_row}"] = float(t_series.iloc[idx])

    def _same_sheet_keys(self) -> list[str | None]:
        rows = sorted(self._row_names)
        return [self._row_names[r] for r in rows]

    def _same_sheet_column(self, col: str) -> list[float]:
        col = col.upper()
        rows = sorted(self._row_names)
        return [float(self.values.get(f"{col}{r}", 0.0)) for r in rows]

    def _resolve_key_ref(self, kref: str, row: int, name: Any) -> Any:
        col, r = re.match(r"([A-Z]+)(\d+)", kref).groups()
        if col == self.name_key_letter and int(r) == row:
            return name
        if col == self.name_key_letter:
            return self._row_names.get(int(r))
        return self._cell(kref)

    def _eval_sumif(self, body: str, row: int, name: Any) -> float:
        parts = self._split_args(body)
        if len(parts) != 3:
            raise ValueError(f"SUMIF arity {len(parts)}")
        sheet1, key_range = self._parse_range_ref(parts[0])
        crit = parts[1].strip()
        sheet2, val_range = self._parse_range_ref(parts[2])
        sheet = sheet1 or sheet2
        key_col = key_range.split(":")[0].replace("$", "")
        val_col = val_range.split(":")[0].replace("$", "")

        if crit.upper().startswith("#REF"):
            return 0.0
        criteria = self._resolve_sumif_criteria(crit, row, name)
        frame = self._aftersales_frame(sheet)
        if key_col in frame.columns:
            frame = frame.copy()
            frame[key_col] = frame[key_col].map(normalize_name)
        return float(sumif_by_key(frame, key_col, val_col, str(criteria)))

    def _resolve_sumif_criteria(self, crit: str, row: int, name: Any) -> Any:
        crit = crit.strip()
        m = re.match(
            rf"(?:'{re.escape(self.anchor_sheet)}'|{re.escape(self.anchor_sheet)})!"
            rf"({self.name_key_letter})(\d+)",
            crit,
            re.I,
        )
        if m:
            return self._row_names.get(int(m.group(2)), name)
        m = re.match(rf"({self.name_key_letter})(\d+)", crit, re.I)
        if m:
            ref_row = int(m.group(2))
            if ref_row == row:
                return name
            return self._row_names.get(ref_row)
        if crit.startswith(f"{self.name_key_letter}"):
            return name
        return crit.strip('"')

    def _parse_range_ref(self, token: str) -> tuple[str, str]:
        token = token.strip()
        if token.startswith("'"):
            bang = token.index("!")
            sheet = token[1:bang].strip("'")
            return sheet, token[bang + 1 :]
        if "!" in token:
            sheet, range_ref = token.split("!", 1)
            return sheet.strip(), range_ref
        return self.anchor_sheet, token

    def _eval_sum(self, body: str) -> float:
        total = 0.0
        for part in self._split_args(body):
            part = part.strip()
            if ":" in part:
                total += self._sum_range(part)
            else:
                ref = part.replace("$", "").replace(f"{self.anchor_sheet}!", "").upper()
                total += self._cell(ref) or 0.0
        return total

    def _sum_range(self, range_ref: str) -> float:
        range_ref = range_ref.replace("$", "").replace(f"{self.anchor_sheet}!", "")
        if ":" not in range_ref:
            return self._cell(range_ref.upper()) or 0.0
        start, end = range_ref.split(":")
        m1 = re.match(r"([A-Z]+)(\d+)", start, re.I)
        m2 = re.match(r"([A-Z]+)(\d+)", end, re.I)
        if not m1 or not m2:
            return 0.0
        c1, r1 = m1.group(1).upper(), int(m1.group(2))
        c2, r2 = m2.group(1).upper(), int(m2.group(2))
        c_lo, c_hi = sorted((_col_to_index(c1), _col_to_index(c2)))
        r_lo, r_hi = sorted((r1, r2))
        total = 0.0
        for row in range(r_lo, r_hi + 1):
            for col_idx in range(c_lo, c_hi + 1):
                total += self._cell(f"{_index_to_col(col_idx)}{row}") or 0.0
        return total

    def _aftersales_frame(self, sheet: str) -> pd.DataFrame:
        if sheet not in self._sheet_cache:
            letters = self.config.sheet_frames.get(sheet)
            if not letters:
                raise KeyError(f"Sheet not registered: {sheet}")
            frame = self.loader.read_sheet_columns(
                sheet,
                {letter: letter for letter in letters},
                label=sheet,
            )
            for letter in letters:
                if letter in ("B", "C", "P", "A"):
                    frame[letter] = frame[letter].map(normalize_name)
                else:
                    frame[letter] = pd.to_numeric(frame[letter], errors="coerce")
            self._sheet_cache[sheet] = frame
        return self._sheet_cache[sheet]

    def _sheet_frame(self, sheet: str) -> pd.DataFrame:
        return self._aftersales_frame(sheet)

    def _resolve_criteria(self, crit: str, row: int, name: Any) -> Any:
        return self._resolve_sumif_criteria(crit, row, name)
