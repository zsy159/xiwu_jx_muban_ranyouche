#!/usr/bin/env python3
"""Extract commission rules from 提成依据.xlsx into config/commission_rules/."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from salary_pipeline.data_ingestion.data_loader import normalize_header
from salary_pipeline.paths import CONFIG_DIR, resolve_project_path

logger = logging.getLogger(__name__)


def _sheet_to_records(workbook_path: Path, sheet_name: str) -> list[dict[str, Any]]:
    frame = pd.read_excel(workbook_path, sheet_name=sheet_name, engine="openpyxl")
    frame.columns = [normalize_header(c) or f"col_{i}" for i, c in enumerate(frame.columns)]
    frame = frame.dropna(how="all")
    records: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        item = {
            str(k): (None if pd.isna(v) else v)
            for k, v in row.items()
            if not (isinstance(v, float) and pd.isna(v)) and str(k).startswith("col_") is False
        }
        if item:
            records.append(item)
    return records


def extract_rules(workbook_path: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    xls = pd.ExcelFile(workbook_path, engine="openpyxl")
    manifest: dict[str, Any] = {
        "source_workbook": str(workbook_path),
        "sheets": {},
    }

    for sheet_name in xls.sheet_names:
        safe_name = sheet_name.strip().replace("/", "_")
        records = _sheet_to_records(workbook_path, sheet_name)
        payload = {"sheet": sheet_name, "records": records}
        json_path = output_dir / f"{safe_name}.json"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        manifest["sheets"][sheet_name] = {
            "file": json_path.name,
            "record_count": len(records),
        }
        logger.info("Wrote %s (%d records)", json_path.name, len(records))

    manifest_path = output_dir / "manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract 提成依据.xlsx to JSON rules")
    parser.add_argument(
        "--workbook",
        default=None,
        help="Path to 提成依据.xlsx (default: month.yaml workbooks.rules)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(CONFIG_DIR / "commission_rules"),
        help="Output directory for JSON rule files",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.workbook:
        workbook_path = resolve_project_path(args.workbook)
    else:
        month_cfg = yaml.safe_load((CONFIG_DIR / "month.yaml").read_text(encoding="utf-8"))
        workbook_path = resolve_project_path(month_cfg["workbooks"]["rules"])

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = resolve_project_path(output_dir)

    manifest = extract_rules(workbook_path, output_dir)
    print(f"Extracted {len(manifest['sheets'])} sheets -> {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
