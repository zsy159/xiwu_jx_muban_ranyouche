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
from salary_pipeline.pipelines.aftersales_formula_engine import (
    _col_to_index,
    _index_to_col,
)
from salary_pipeline.pipelines.hub_formula_engine import (
    SUMIF_SIMPLE,
    SUM_RE,
    HubFormulaEngine,
    _column_letters,
)

logger = logging.getLogger(__name__)

HUB_SHEET = "提成汇总"
BASIC_SHEET = "西物基本"
GALAXY_B_SHEET = "银河B直营店提成"
GALAXY_A_SHEET = "银河A提成- 渠道+直营店"

XW_COLUMN_MAP: dict[str, str] = {
    "F": "考核量",
    "G": "销售数量",
    "H": "整车绩效",
    "I": "权限结余绩效",
    "J": "附加1绩效",
    "K": "附加2绩效",
    "L": "附加3绩效",
    "M": "附加4绩效",
    "N": "上户绩效",
    "O": "专项提成",
    "P": "其他",
    "Q": "超期绩效",
    "R": "大客户",
    "S": "附加",
    "T": "特殊车型已发扣除",
    "U": "提成合计",
    "V": "整车完成考核",
    "W": "附加1考核",
    "X": "综合",
    "Y": "活动",
    "Z": "其它1",
    "AA": "已经发放并税",
    "AB": "其它",
    "AC": "集客考核",
    "AD": "考核小计",
    "AE": "应发放合计",
    "AF": "已经发放并税_AF",
    "AG": "代发放绩效",
    "AH": "实际发放",
    "AI": "基本工资（含补助）",
    "AJ": "其它_AJ",
    "AK": "个人社保",
    "AL": "个人公积金",
    "AM": "应纳税所得额",
    "AN": "个人所得税",
    "AO": "已扣税",
    "AP": "本次扣税",
    "AQ": "基本代扣款",
    "AR": "其他扣款",
    "AS": "实际发放_AS",
    "AT": "AT列",
    "AU": "年终绩效",
}

LOCAL_INDEX = re.compile(
    r"^=INDEX\((?P<vcol>[A-Z]{1,3}):(?P=vcol),MATCH\((?P<kref>[A-Z]{1,3}\d+),(?P<kcol>[A-Z]{1,3}):(?P=kcol),0\)\)$",
    re.IGNORECASE,
)
SUB_CELLS = re.compile(r"^=([A-Z]{1,3})(\d+)-([A-Z]{1,3})(\d+)$", re.IGNORECASE)
ADD2_CELLS = re.compile(
    r"^=([A-Z]{1,3})(\d+)\+([A-Z]{1,3})(\d+)$",
    re.IGNORECASE,
)
ADD4_CELLS = re.compile(
    r"^=([A-Z]{1,3})(\d+)\+([A-Z]{1,3})(\d+)\+([A-Z]{1,3})(\d+)\+([A-Z]{1,3})(\d+)$",
    re.IGNORECASE,
)
SUB_ADD_CELLS = re.compile(
    r"^=([A-Z]{1,3})(\d+)-([A-Z]{1,3})(\d+)\+([A-Z]{1,3})(\d+)$",
    re.IGNORECASE,
)
SUB3_CELLS = re.compile(
    r"^=([A-Z]{1,3})(\d+)-([A-Z]{1,3})(\d+)-([A-Z]{1,3})(\d+)$",
    re.IGNORECASE,
)

HUB_VALUE_LETTERS = [
    "D",
    "F",
    "G",
    "W",
    "X",
    "Y",
    "Z",
    "AA",
    "AB",
    "AC",
    "AD",
    "AE",
    "AF",
    "AG",
    "AH",
    "AI",
    "AK",
    "AL",
    "AM",
    "AN",
    "AO",
    "AP",
    "AQ",
    "AR",
    "AT",
    "AX",
    "AY",
]

DIRECT_STORE_BASIC_SHEET = "直营店基本"
CS_BASIC_SHEET = "超市基本"

DIRECT_STORE_COLUMN_MAP: dict[str, str] = {
    "F": "考核量",
    "G": "销售数量",
    "H": "整车绩效",
    "I": "权限结余绩效",
    "J": "附加1绩效",
    "K": "附加2绩效",
    "L": "附加3绩效",
    "M": "附加4绩效",
    "N": "附加5绩效",
    "O": "其它",
    "P": "重功车型追加",
    "Q": "超期绩效",
    "R": "其它_R",
    "S": "附加",
    "T": "附加_T",
    "U": "提成合计",
    "V": "整车完成考核",
    "W": "附加1完成考核",
    "X": "综合",
    "Y": "延保提成",
    "Z": "其它及超期",
    "AA": "已经发放",
    "AB": "交车支出",
    "AC": "集客考核",
    "AD": "考核小计",
    "AE": "应发放合计",
    "AF": "已经发放_AF",
    "AG": "代发放绩效(银河A+B)",
    "AH": "实际发放",
    "AI": "基本工资（含补助）",
    "AJ": "其它_AJ",
    "AK": "个人社保",
    "AL": "个人公积金",
    "AM": "应纳税所得额",
    "AN": "个人所得税",
    "AO": "已交个税",
    "AP": "本次扣税",
    "AQ": "基本代扣项",
    "AR": "其它_AR",
    "AS": "实际发放_AS",
    "AT": "Hub_AX",
    "AU": "年终绩效",
    "AV": "新能源B网销量",
    "AW": "银河B年终绩效",
    "AX": "新能源A网销量",
    "AY": "新能源A年终绩效",
    "AZ": "验证",
    "BA": "应发验证差",
}

CS_COLUMN_MAP: dict[str, str] = {
    **{
        letter: name
        for letter, name in XW_COLUMN_MAP.items()
        if letter not in {"N", "P", "T", "AA", "AF", "AT"}
    },
    "N": "附加5绩效",
    "P": "其它_P",
    "T": "交强险提成",
    "AA": "已经发放并税",
    "AF": "已经发放并税_AF",
    "AT": "标准",
}


@dataclass
class XwPayoutEngineConfig:
    anchor_sheet: str = "XW提成-发"
    column_map: dict[str, str] = field(default_factory=lambda: dict(XW_COLUMN_MAP))
    name_key_letter: str = "D"
    sheet_frames: dict[str, list[str]] = field(default_factory=dict)
    static_bootstrap_cols: list[str] = field(
        default_factory=lambda: ["AJ", "AO", "AR"]
    )
    criteria_aux_letters: list[str] = field(default_factory=list)
    tax_lookup_key_col: str = "AZ"
    tax_lookup_value_col: str = "BA"


XW_CONFIG = XwPayoutEngineConfig(
    sheet_frames={
        HUB_SHEET: HUB_VALUE_LETTERS,
        BASIC_SHEET: ["C", "P", "AB", "AC", "AG", "AA", "AE"],
        GALAXY_B_SHEET: ["F", "AI"],
        GALAXY_A_SHEET: ["F", "AH"],
        "车展奖励（并税）": ["L", "V"],
    },
)

DIRECT_STORE_CONFIG = XwPayoutEngineConfig(
    anchor_sheet="直营店提成-发",
    column_map=DIRECT_STORE_COLUMN_MAP,
    criteria_aux_letters=["E"],
    tax_lookup_key_col="BE",
    tax_lookup_value_col="BF",
    sheet_frames={
        HUB_SHEET: HUB_VALUE_LETTERS,
        DIRECT_STORE_BASIC_SHEET: ["C", "P", "AB", "AC", "AG", "AA", "AE"],
        GALAXY_B_SHEET: ["F", "I", "AG", "AI", "AV"],
        GALAXY_A_SHEET: ["F", "AH", "AU", "I"],
        "综合表": ["D", "M"],
        "超市公积金": ["B", "D"],
        "服装扣款明细": ["C", "D", "N", "O", "Q", "R"],
    },
)

CS_CONFIG = XwPayoutEngineConfig(
    anchor_sheet="CS提成-发",
    column_map=CS_COLUMN_MAP,
    tax_lookup_key_col="BA",
    tax_lookup_value_col="BB",
    sheet_frames={
        HUB_SHEET: HUB_VALUE_LETTERS,
        CS_BASIC_SHEET: ["C", "P", "AB", "AC", "AG", "AA", "AE"],
        GALAXY_B_SHEET: ["F", "AI"],
        GALAXY_A_SHEET: ["F", "AH"],
        "车展奖励（并税）": ["L", "V"],
    },
)

PAYOUT_CHANNEL_CONFIGS: dict[str, XwPayoutEngineConfig] = {
    "xw": XW_CONFIG,
    "direct_store": DIRECT_STORE_CONFIG,
    "cs": CS_CONFIG,
}

PAYOUT_CHANNEL_COLUMN_MAPS: dict[str, dict[str, str]] = {
    "xw": XW_COLUMN_MAP,
    "direct_store": DIRECT_STORE_COLUMN_MAP,
    "cs": CS_COLUMN_MAP,
}


class XwPayoutFormulaEngine(HubFormulaEngine):
    """Evaluate XW提成-发 formulas: hub SUMIF + payroll merge + row arithmetic."""

    def __init__(
        self,
        topology_path: Path,
        loader: WorkbookLoader,
        config: XwPayoutEngineConfig | None = None,
        *,
        hub_frame: pd.DataFrame | None = None,
    ) -> None:
        self.config = config or XW_CONFIG
        self.anchor_sheet = self.config.anchor_sheet
        self.column_map = self.config.column_map
        self.name_key_letter = self.config.name_key_letter

        topo = json.loads(topology_path.read_text(encoding="utf-8"))
        self.cells = topo["cells"]
        allowed = set(self.column_map) | {"AT", "AU"}
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
        if hub_frame is not None:
            self._sheet_cache[HUB_SHEET] = hub_frame
        self._row_names: dict[int, str] = {}
        self._criteria_aux: dict[tuple[int, str], Any] = {}
        self._name_tax_lookup: pd.Series = pd.Series(dtype=float)

    def apply(self, skeleton: pd.DataFrame) -> pd.DataFrame:
        if skeleton.empty or "_excel_row" not in skeleton.columns:
            raise ValueError("skeleton requires _excel_row column")

        self._row_names = {
            int(row["_excel_row"]): normalize_name(row.get("姓名"))
            for _, row in skeleton.iterrows()
        }
        self.values.clear()
        self.warnings.clear()
        self._bootstrap_static_columns()

        for _pass in range(12):
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
                    value = self._eval_payout(formula, row_num, name)
                except Exception as exc:
                    if _pass == 0:
                        self.warnings.append(f"eval fail {full_key}: {exc}")
                    continue
                if value is not None:
                    self.values[coord] = 0.0 if pd.isna(value) else float(value)
            if len(self.values) == before:
                break

        out = skeleton.copy()
        for idx, row in out.iterrows():
            excel_row = int(row["_excel_row"])
            for letter, col_name in self.column_map.items():
                key = f"{letter}{excel_row}"
                if key in self.values:
                    out.at[idx, col_name] = self.values[key]
        logger.info(
            "XW payout engine: computed=%s warnings=%s",
            len(self.values),
            len(self.warnings),
        )
        return out.drop(columns=["_excel_row"], errors="ignore")

    def _eval_payout(self, formula: str, row: int, name: Any) -> float | None:
        formula = formula.strip()
        if not formula.startswith("="):
            return None
        body = formula[1:]

        if "+" in body.upper() and "SUMIF(" in body.upper():
            parts = re.split(r"\+(?=SUMIF\()", body, flags=re.IGNORECASE)
            if len(parts) > 1:
                return sum(
                    self._eval_sumif_part(part, row, name) for part in parts if part.strip()
                )

        m = LOCAL_INDEX.match(formula)
        if m:
            return self._eval_local_index(m, row, name)

        m = SUB3_CELLS.match(formula)
        if m:
            return (
                self._cell(f"{m.group(1).upper()}{m.group(2)}")
                - self._cell(f"{m.group(3).upper()}{m.group(4)}")
                - self._cell(f"{m.group(5).upper()}{m.group(6)}")
            )

        m = SUB_ADD_CELLS.match(formula)
        if m:
            return (
                self._cell(f"{m.group(1).upper()}{m.group(2)}")
                - self._cell(f"{m.group(3).upper()}{m.group(4)}")
                + self._cell(f"{m.group(5).upper()}{m.group(6)}")
            )

        m = ADD4_CELLS.match(formula)
        if m:
            return sum(self._cell(f"{m.group(i).upper()}{m.group(i+1)}") for i in (1, 3, 5, 7))

        m = ADD2_CELLS.match(formula)
        if m:
            return self._cell(f"{m.group(1).upper()}{m.group(2)}") + self._cell(
                f"{m.group(3).upper()}{m.group(4)}"
            )

        m = SUB_CELLS.match(formula)
        if m:
            return self._cell(f"{m.group(1).upper()}{m.group(2)}") - self._cell(
                f"{m.group(3).upper()}{m.group(4)}"
            )

        if self._looks_like_cell_arithmetic(body):
            return self._eval_cell_arithmetic(body)

        return self._eval(formula, row, name)

    def _looks_like_cell_arithmetic(self, body: str) -> bool:
        if "(" in body or "SUMIF" in body.upper() or "INDEX" in body.upper():
            return False
        return bool(re.fullmatch(r"[\d.+\-A-Z]+", body, re.I))

    def _eval_cell_arithmetic(self, body: str) -> float:
        parts = re.split(r"([+-])", body)
        total = self._resolve_arith_term(parts[0].strip())
        idx = 1
        while idx + 1 < len(parts):
            op = parts[idx]
            total = (
                total + self._resolve_arith_term(parts[idx + 1].strip())
                if op == "+"
                else total - self._resolve_arith_term(parts[idx + 1].strip())
            )
            idx += 2
        return total

    def _resolve_arith_term(self, token: str) -> float:
        if re.fullmatch(r"[A-Z]+\d+", token, re.I):
            return self._cell(token.upper())
        return float(token)

    def _eval_sumif_part(self, part: str, row: int, name: Any) -> float:
        part = part.strip()
        if part.upper().startswith("SUMIF("):
            inner = part[6:].rstrip(")")
            return self._eval_sumif(inner, row, name)
        raise ValueError(f"expected SUMIF fragment, got {part!r}")

    def _eval_local_index(self, m: re.Match[str], row: int, name: Any) -> float:
        vcol = m.group("vcol").upper()
        kref = m.group("kref").upper()
        lookup_name = self._resolve_key_ref(kref, row, name)
        tax_val = self.config.tax_lookup_value_col.upper()
        tax_key = self.config.tax_lookup_key_col.upper()
        if vcol == tax_val and m.group("kcol").upper() == tax_key:
            key = normalize_name(lookup_name)
            if key in self._name_tax_lookup.index:
                return float(self._name_tax_lookup.loc[key])
            return 0.0
        return 0.0

    def _bootstrap_static_columns(self) -> None:
        static_letters = list(self.config.static_bootstrap_cols)
        aux_letters = list(self.config.criteria_aux_letters)
        tax_key = self.config.tax_lookup_key_col
        tax_val = self.config.tax_lookup_value_col
        read_letters = sorted(
            set(static_letters + aux_letters + [tax_key, tax_val]),
            key=lambda letter: (len(letter), letter),
        )
        raw = self.loader.read_sheet_columns(
            self.anchor_sheet,
            {letter: letter for letter in read_letters},
            label=f"{self.anchor_sheet}!static",
        )
        for letter in static_letters:
            series = pd.to_numeric(raw[letter], errors="coerce")
            for excel_row in self._row_names:
                idx = excel_row - 1
                if 0 <= idx < len(series) and not pd.isna(series.iloc[idx]):
                    self.values[f"{letter}{excel_row}"] = float(series.iloc[idx])

        for letter in aux_letters:
            series = raw[letter]
            for excel_row in self._row_names:
                idx = excel_row - 1
                if 0 <= idx < len(series):
                    value = series.iloc[idx]
                    if value is not None and not (isinstance(value, float) and pd.isna(value)):
                        self._criteria_aux[(excel_row, letter.upper())] = value

        names = raw[tax_key].map(normalize_name)
        amounts = pd.to_numeric(raw[tax_val], errors="coerce")
        lookup = pd.Series(amounts.values, index=names)
        self._name_tax_lookup = lookup[~lookup.index.isna()].groupby(level=0).last()

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
        frame = self._payout_frame(sheet)
        if key_col in frame.columns:
            frame = frame.copy()
            if key_col in ("D", "C", "F", "A", "L"):
                frame[key_col] = frame[key_col].map(normalize_name)
        return float(sumif_by_key(frame, key_col, val_col, str(criteria)))

    def _resolve_sumif_criteria(self, crit: str, row: int, name: Any) -> Any:
        crit = crit.strip()
        m = re.match(
            rf"(?:'{re.escape(self.anchor_sheet)}'|{re.escape(self.anchor_sheet)})!"
            rf"([A-Z]{{1,3}})(\d+)",
            crit,
            re.I,
        )
        if m:
            ref_col, ref_row = m.group(1).upper(), int(m.group(2))
            return self._resolve_anchor_criteria(ref_col, ref_row, row, name)
        m = re.match(rf"({self.name_key_letter})(\d+)", crit, re.I)
        if m:
            ref_row = int(m.group(2))
            return name if ref_row == row else self._row_names.get(ref_row, name)
        return crit.strip('"')

    def _resolve_anchor_criteria(
        self, ref_col: str, ref_row: int, row: int, name: Any
    ) -> Any:
        if ref_col == self.name_key_letter:
            return name if ref_row == row else self._row_names.get(ref_row, name)
        aux = self._criteria_aux.get((ref_row, ref_col))
        if aux is not None:
            return aux
        cell_key = f"{ref_col}{ref_row}"
        if cell_key in self.values:
            return self.values[cell_key]
        return self._cell(cell_key)

    def _parse_range_ref(self, token: str) -> tuple[str, str]:
        token = token.strip()
        if token.startswith("'"):
            bang = token.index("!")
            sheet = token[1:bang].strip("'")
            return sheet, token[bang + 1 :]
        if "!" in token:
            sheet, range_ref = token.split("!", 1)
            return sheet.strip(), range_ref
        if ":" in token and "!" not in token:
            return self.anchor_sheet, token
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
        for excel_row in range(r_lo, r_hi + 1):
            for col_idx in range(c_lo, c_hi + 1):
                total += self._cell(f"{_index_to_col(col_idx)}{excel_row}") or 0.0
        return total

    def _cell(self, ref: str) -> float:
        ref = ref.upper()
        if ref in self.values:
            return self.values[ref]
        return 0.0

    def _payout_frame(self, sheet: str) -> pd.DataFrame:
        sheet = sheet.strip()
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
                if letter in ("D", "C", "F", "A"):
                    frame[letter] = frame[letter].map(normalize_name)
                else:
                    frame[letter] = pd.to_numeric(frame[letter], errors="coerce")
            self._sheet_cache[sheet] = frame
        return self._sheet_cache[sheet]

    def _sheet_frame(self, sheet: str) -> pd.DataFrame:
        return self._payout_frame(sheet)

    def _resolve_criteria(self, crit: str, row: int, name: Any) -> Any:
        return self._resolve_sumif_criteria(crit, row, name)
