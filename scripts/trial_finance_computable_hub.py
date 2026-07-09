#!/usr/bin/env python3
"""Trial Hub preview from 财务可计算 template (sales-advisor W–AI only).

Reads person-sheet aggregates filled by finance; does NOT auto-rollup VIN detail,
does NOT touch month.yaml / uploads ingestion, does NOT bootstrap golden values.

Reuse: HubRuleEngine.compute_row + hub_column_rules.yaml (read-only).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, PROJECT.as_posix())

from salary_pipeline.pipelines.hub_rule_engine import (  # noqa: E402
    HubRuleEngine,
    load_hub_column_rules,
    resolve_sales_advisor_template,
)

CONFIG_DIR = PROJECT / "salary_pipeline" / "config"
TEMPLATE_CFG = CONFIG_DIR / "finance_computable_template.yaml"
DEFAULT_INPUT = PROJECT / "docs/templates/销售账套-财务可计算-2026-05.xlsx"
DEFAULT_OUT = PROJECT / "output" / "finance_computable_trial" / "hub_preview_sales_advisor.xlsx"

FAMILY_ID = "销售顾问"
logger = logging.getLogger(__name__)

# label (Excel 中文表头) → AdvisorAlignedInput / perf frame column letter
PERSON_LABEL_TO_PERF_LETTER: dict[str, str] = {
    "整车绩效合计": "AG",
    "权限结余合计": "AH",
    "加装绩效合计": "AI",
    "保险绩效合计": "AJ",
    "金融绩效合计": "AK",
    "爱车宝绩效合计": "AM",
    "上户绩效分项一": "AN",
    "上户绩效分项二": "AS",
    "盈利产品合计": "AL",
    "延保提成合计": "AT",
    "特殊车型合计": "AQ",
    "座位险合计": "AO",
    "二手车合计": "AR",
    "玻碎险合计": "AP",
}

def _load_cfg(path: Path = TEMPLATE_CFG) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _read_person_sheet(workbook: Path, sheet_name: str) -> pd.DataFrame:
    """Row2 = headers, row3 = comments, row4+ = data (1-indexed Excel)."""
    raw = pd.read_excel(workbook, sheet_name=sheet_name, header=None)
    if raw.empty or len(raw) < 2:
        return pd.DataFrame()
    headers = [str(v).strip() if pd.notna(v) else f"col_{i}" for i, v in enumerate(raw.iloc[1])]
    data = raw.iloc[3:].copy()
    data.columns = headers
    data = data.dropna(how="all")
    if "姓名" in data.columns:
        data = data[data["姓名"].notna()]
        data = data[data["姓名"].astype(str).str.strip() != ""]
    return data.reset_index(drop=True)


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_perf_frame_from_person_row(row: pd.Series) -> pd.DataFrame:
    """One synthetic VIN-less row per advisor so HubRuleEngine can SUMIF by P."""
    record: dict[str, Any] = {"P": str(row.get("姓名", "")).strip()}
    for label, letter in PERSON_LABEL_TO_PERF_LETTER.items():
        record[letter] = _to_float(row.get(label), 0.0)
    return pd.DataFrame([record])


def compute_hub_preview(person_df: pd.DataFrame) -> pd.DataFrame:
    engine = HubRuleEngine(load_hub_column_rules())
    family = engine.role_families.get(FAMILY_ID, {})
    if not family:
        raise RuntimeError(f"hub_column_rules.yaml missing family {FAMILY_ID}")

    from salary_pipeline.data_ingestion.data_loader import normalize_name

    ba_rates: dict[str, float] = {}
    for _, row in person_df.iterrows():
        name = str(row.get("姓名", "")).strip()
        if not name:
            continue
        ba_rates[name] = _to_float(row.get("合并完成率"), 0.0)

    class _NormLoader:
        """BA from person sheet; 姓名 keys normalized like production task sheet."""

        def read_sales_task_sheet(self) -> pd.DataFrame:
            rows = [
                {"姓名": normalize_name(name), "合并完成率": rate}
                for name, rate in ba_rates.items()
            ]
            return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["姓名", "合并完成率"])

    loader = _NormLoader()

    hub_cols = list(
        _load_cfg().get(
            "trial_hub_columns",
            [s["hub_column"] for s in family.get("columns", [])],
        )
    )

    out_rows: list[dict[str, Any]] = []
    for _, row in person_df.iterrows():
        name = str(row.get("姓名", "")).strip()
        if not name:
            continue
        store = row.get("店别")
        role = str(row.get("职务", "销售顾问") or "销售顾问").strip()
        h_rate = _to_float(row.get("销量完成率"), 0.0)
        insurance_const = _to_float(row.get("保险绩效追加常数"), 0.0)

        # Apply insurance_add override via temporary family copy when constant filled
        family_cfg = dict(family)
        selector = dict(family_cfg.get("template_selector") or {})
        overrides = dict(selector.get("name_overrides") or {})
        template, _ = resolve_sales_advisor_template(
            name=name, store=str(store) if store is not None else None, family_cfg=family
        )
        if insurance_const and template != "insurance_add":
            # Finance-filled constant forces insurance_add style for Z only path
            overrides[name] = {
                "template": "insurance_add",
                "insurance_add_const": insurance_const,
            }
            selector["name_overrides"] = overrides
            family_cfg["template_selector"] = selector
        elif name in overrides and insurance_const:
            overrides[name] = {
                **overrides[name],
                "insurance_add_const": insurance_const,
            }
            selector["name_overrides"] = overrides
            family_cfg["template_selector"] = selector

        perf_frame = _build_perf_frame_from_person_row(row)
        metrics = engine.compute_row(
            name=name,
            store=str(store) if store is not None else None,
            h_rate=h_rate,
            perf_frame=perf_frame,
            family_cfg=family_cfg,
            loader=loader,
        )
        template_used, add_const = resolve_sales_advisor_template(
            name=name,
            store=str(store) if store is not None else None,
            family_cfg=family_cfg,
        )
        out = {
            "店别": store,
            "职务": role,
            "姓名": name,
            "销量完成率": h_rate,
            "合并完成率": _to_float(row.get("合并完成率"), 0.0),
            "模板": template_used,
            "保险追加常数": add_const,
        }
        for col in hub_cols:
            out[col] = metrics.get(col)
        out_rows.append(out)

    return pd.DataFrame(out_rows)


def run_trial(
    *,
    input_path: Path,
    out_path: Path,
    person_sheet: str | None = None,
) -> dict[str, Any]:
    cfg = _load_cfg()
    sheet = person_sheet or cfg.get("person_sheet", {}).get("name", "销售人员")
    person_df = _read_person_sheet(input_path, sheet)
    if person_df.empty:
        raise SystemExit(
            f"No person rows in '{sheet}' of {input_path}. "
            "Fill 销售人员 starting row 4."
        )

    preview = compute_hub_preview(person_df)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        preview.to_excel(writer, sheet_name="Hub预览-销售顾问", index=False)
        gaps = pd.DataFrame(
            {
                "延期项": cfg.get("deferred", []),
            }
        )
        gaps.to_excel(writer, sheet_name="延期缺口", index=False)
        notes = pd.DataFrame(
            [
                {"说明": "本预览仅销售顾问 W–AI；数据来自销售人员手填合计"},
                {"说明": "销售明细 VIN 列本阶段不参与计算（不自动 rollup）"},
                {"说明": "未读金标准、未改 month.yaml / uploads"},
                {"说明": f"输入: {input_path}"},
            ]
        )
        notes.to_excel(writer, sheet_name="说明", index=False)

    return {
        "input": str(input_path),
        "out_path": str(out_path),
        "rows": len(preview),
        "columns": list(preview.columns),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trial Hub W–AI preview from 财务可计算 person sheet"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--person-sheet", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    if not args.input.is_file():
        raise SystemExit(f"Input not found: {args.input}")

    result = run_trial(
        input_path=args.input,
        out_path=args.out,
        person_sheet=args.person_sheet,
    )
    print(f"Read: {result['input']}")
    print(f"Wrote: {result['out_path']}")
    print(f"Advisor rows: {result['rows']}")
    print(f"Columns: {', '.join(result['columns'])}")


if __name__ == "__main__":
    main()
