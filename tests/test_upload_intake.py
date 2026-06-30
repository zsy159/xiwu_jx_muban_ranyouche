"""Tests for upload intake and worksheet-level matching."""

from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from openpyxl import Workbook

from salary_pipeline.ingestion_upload.file_intake import (
    SheetMatchStatus,
    display_match_status,
    intake_uploads,
    preferred_conflict_source_index,
    scan_workbook_sheets,
)
from salary_pipeline.ingestion_upload.manifest import (
    FAMILY_SALES,
    build_required_sheet_manifest,
    group_manifest_by_family,
    required_input_sheets,
    resolve_sheet_alias,
)
from salary_pipeline.ingestion_upload.month_config import write_month_config
from salary_pipeline.ingestion_upload.overrides import (
    apply_overrides,
    load_overrides,
    store_sheet_override,
)
from salary_pipeline.ingestion_upload.sheet_merge import (
    build_consolidated_workbook,
    needs_openpyxl_merge,
    plan_sheet_sources,
)


def _make_workbook(path: Path, sheets: dict[str, list[list]]) -> None:
    wb = Workbook()
    default = wb.active
    wb.remove(default)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r_idx, row in enumerate(rows, start=1):
            for c_idx, val in enumerate(row, start=1):
                ws.cell(row=r_idx, column=c_idx, value=val)
    wb.save(path)


class UploadIntakeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_manifest_includes_registry_and_closure_sheets(self) -> None:
        manifest = build_required_sheet_manifest()
        names = {s.name for s in manifest if not s.optional_note}
        self.assertIn("终端明细表", names)
        self.assertIn("系统销售毛利", names)
        self.assertIn("翼真考核", names)
        self.assertIn("按揭原表", names)
        self.assertIn("指标汇总", names)
        self.assertIn("保客考核明细", names)
        self.assertIn("直营店交车", names)
        self.assertIn("综合表", names)
        self.assertIn("比对表", names)
        self.assertIn("延保提成", names)
        self.assertNotIn("绩效整理表", names)

    def test_manifest_formula_notes_exclude_generated_perf_sheet(self) -> None:
        manifest = build_required_sheet_manifest()
        all_names = {s.name for s in manifest}
        self.assertNotIn("绩效整理表", all_names)
        optional = {s.name for s in manifest if s.optional_note}
        self.assertIn("销售任务及完成率", optional)

    def test_manifest_includes_role_family_sheets(self) -> None:
        manifest = build_required_sheet_manifest()
        by_name = {s.name: s for s in manifest if not s.optional_note}
        role_sheets = {
            "新媒体": ("新媒体",),
            "邀约专员提成": ("邀约专员",),
            "客户部提成": ("客户专员",),
            "直营店经理提成 (财务)": ("直营店经理",),
            "招聘": ("招聘",),
        }
        for sheet_name, families in role_sheets.items():
            self.assertIn(sheet_name, by_name, msg=f"missing {sheet_name}")
            self.assertEqual(by_name[sheet_name].families, families)
            self.assertEqual(by_name[sheet_name].source, "role")

    def test_manifest_groups_by_family(self) -> None:
        groups = dict(group_manifest_by_family())
        self.assertIn(FAMILY_SALES, groups)
        self.assertIn("新媒体", groups)
        self.assertIn("招聘", groups)
        sales_names = {s.name for s in groups[FAMILY_SALES] if not s.optional_note}
        self.assertIn("终端明细表", sales_names)
        self.assertNotIn("新媒体", sales_names)
        new_media_names = {s.name for s in groups["新媒体"]}
        self.assertEqual(new_media_names, {"新媒体"})

    def test_scan_workbook_sheets(self) -> None:
        path = self.tmp / "a.xlsx"
        _make_workbook(path, {"终端明细表": [["h"]], "整车成本": [["h"]]})
        sheets = scan_workbook_sheets(path)
        self.assertEqual(set(sheets), {"终端明细表", "整车成本"})

    def test_sheet_level_matching_ready(self) -> None:
        sales = self.tmp / "销售.xlsx"
        required = required_input_sheets()
        sheet_data = {s.name: [["x"]] for s in required[:5]}
        _make_workbook(sales, sheet_data)

        data = sales.read_bytes()
        intake = intake_uploads(
            "2099-01",
            [("销售.xlsx", data)],
            staging_root=self.tmp / "staging",
        )
        self.assertFalse(intake.errors)
        matched = {
            m.required.name: m.status
            for m in intake.matches
            if not m.required.optional_note
        }
        for name in sheet_data:
            self.assertEqual(matched[name], SheetMatchStatus.READY)
        self.assertIsNotNone(intake.sales_workbook)

    def test_missing_and_conflict_detection(self) -> None:
        f1 = self.tmp / "a.xlsx"
        f2 = self.tmp / "b.xlsx"
        _make_workbook(f1, {"终端明细表": [["1"]]})
        _make_workbook(f2, {"终端明细表": [["2"]]})

        intake = intake_uploads(
            "2099-02",
            [
                ("a.xlsx", f1.read_bytes()),
                ("b.xlsx", f2.read_bytes()),
            ],
            staging_root=self.tmp / "staging2",
        )
        terminal = next(m for m in intake.matches if m.required.name == "终端明细表")
        self.assertEqual(terminal.status, SheetMatchStatus.CONFLICT)
        self.assertIn("终端明细表", intake.conflict_sheets)
        self.assertFalse(intake.all_required_ready)
        self.assertFalse(intake.can_proceed())
        self.assertFalse(intake.can_proceed({"终端明细表": "a.xlsx"}))
        blockers = intake.proceed_blockers()
        self.assertTrue(any("冲突" in b for b in blockers))
        resolved_blockers = intake.proceed_blockers({"终端明细表": "a.xlsx"})
        self.assertFalse(any("冲突" in b for b in resolved_blockers))
        self.assertTrue(any("缺失" in b for b in resolved_blockers))

    def test_can_proceed_missing_sheets(self) -> None:
        sales = self.tmp / "partial.xlsx"
        _make_workbook(sales, {"终端明细表": [["x"]]})
        intake = intake_uploads(
            "2099-06",
            [("partial.xlsx", sales.read_bytes())],
            staging_root=self.tmp / "staging6",
        )
        self.assertFalse(intake.can_proceed())
        blockers = intake.proceed_blockers()
        self.assertTrue(any("缺失" in b for b in blockers))

    def test_zip_upload_extraction(self) -> None:
        inner = self.tmp / "inner.xlsx"
        _make_workbook(inner, {"整车成本": [["v"]]})
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("inner.xlsx", inner.read_bytes())
        intake = intake_uploads(
            "2099-03",
            [("bundle.zip", buf.getvalue())],
            staging_root=self.tmp / "staging3",
        )
        self.assertFalse(intake.errors)
        cost = next(m for m in intake.matches if m.required.name == "整车成本")
        self.assertEqual(cost.status, SheetMatchStatus.READY)

    def test_resolve_sheet_alias_trailing_space(self) -> None:
        available = {"二手置换 ", "比对表"}
        self.assertEqual(resolve_sheet_alias("二手置换", available), "二手置换 ")
        self.assertEqual(resolve_sheet_alias("二手置换 ", available), "二手置换 ")

    def test_display_match_status_reflects_conflict_resolution(self) -> None:
        from salary_pipeline.ingestion_upload.file_intake import SheetMatch
        from salary_pipeline.ingestion_upload.manifest import RequiredSheet

        match = SheetMatch(
            required=RequiredSheet(name="新媒体", families=("新媒体",)),
            status=SheetMatchStatus.CONFLICT,
            sources=["销售.xlsx", "提成依据.xlsx"],
        )
        status, sources = display_match_status(match, {})
        self.assertEqual(status, SheetMatchStatus.CONFLICT)
        self.assertEqual(sources, ["销售.xlsx", "提成依据.xlsx"])

        status, sources = display_match_status(
            match, {"新媒体": "销售.xlsx"}
        )
        self.assertEqual(status, SheetMatchStatus.READY)
        self.assertEqual(sources, ["销售.xlsx"])

    def test_preferred_conflict_source_index_prefers_sales_workbook(self) -> None:
        sources = ["提成依据.xlsx", "西物销售提成.xlsx"]
        idx = preferred_conflict_source_index(
            sources,
            sales_workbook=Path("西物销售提成.xlsx"),
        )
        self.assertEqual(idx, 1)
        idx2 = preferred_conflict_source_index(sources)
        self.assertEqual(idx2, 1)

    def test_build_consolidated_workbook(self) -> None:
        import json

        base = self.tmp / "base.xlsx"
        extra = self.tmp / "extra.xlsx"
        _make_workbook(base, {"终端明细表": [["a"]]})
        _make_workbook(extra, {"比对表": [["b"]]})

        intake = intake_uploads(
            "2099-04",
            [
                ("base.xlsx", base.read_bytes()),
                ("extra.xlsx", extra.read_bytes()),
            ],
            staging_root=self.tmp / "staging4",
        )
        out = self.tmp / "merged.xlsx"
        build_consolidated_workbook(intake, out)
        sheets = set(scan_workbook_sheets(out))
        self.assertIn("终端明细表", sheets)
        self.assertNotIn("比对表", sheets)
        self.assertIsNotNone(intake.sheet_sources_path)
        sources = json.loads(intake.sheet_sources_path.read_text(encoding="utf-8"))
        self.assertIn("比对表", sources)

    def test_write_month_config_staging_paths(self) -> None:
        cfg_dir = self.tmp / "cfg"
        path = write_month_config(
            "2099-05",
            sales_workbook="data/raw/2099-05/sales.xlsx",
            sales_topology="data/topology/2099-05/sales.topology.json",
            sheet_sources_file="data/raw/2099-05/.staging/sheet_sources.json",
            staging=True,
            config_dir=cfg_dir,
        )
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")
        self.assertIn(".staging", text)
        self.assertIn("sheet_sources.json", text)
        self.assertIn("2099-05", text)

    def test_single_file_merge_uses_copy_not_openpyxl(self) -> None:
        sales = self.tmp / "销售.xlsx"
        required = required_input_sheets()
        sheet_data = {s.name: [["x"]] for s in required[:5]}
        _make_workbook(sales, sheet_data)
        intake = intake_uploads(
            "2099-04b",
            [("销售.xlsx", sales.read_bytes())],
            staging_root=self.tmp / "staging4b",
        )
        self.assertFalse(needs_openpyxl_merge(intake))
        self.assertEqual(plan_sheet_sources(intake), {})
        out = self.tmp / "merged-copy.xlsx"
        build_consolidated_workbook(intake, out)
        self.assertEqual(out.read_bytes(), sales.read_bytes())

    def test_trial_preview_uses_staging_commission_path(self) -> None:
        import yaml

        cfg_dir = self.tmp / "cfg-trial"
        config_path = write_month_config(
            "2099-07",
            sales_workbook="data/raw/2099-07/.staging/销售账套-合并.xlsx",
            sales_topology="data/topology/2099-07/销售.topology.json",
            staging=True,
            config_dir=cfg_dir,
        )
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.assertEqual(
            cfg["outputs"]["commission_summary_file"],
            "output/2099-07/.staging/提成汇总.xlsx",
        )
        self.assertNotEqual(
            cfg["outputs"]["commission_summary_file"],
            "output/2099-07/提成汇总.xlsx",
        )
        self.assertTrue(config_path.exists())

    def test_overrides_roundtrip(self) -> None:
        import pandas as pd

        df = pd.DataFrame(
            [{"店别": "A", "职务": "顾问", "姓名": "张三", "整车绩效": 100.0}]
        )
        ov_path = self.tmp / "overrides.json"
        store_sheet_override(ov_path, "提成汇总", df)
        loaded = apply_overrides(df, "提成汇总", load_overrides(ov_path))
        self.assertEqual(float(loaded.iloc[0]["整车绩效"]), 100.0)


if __name__ == "__main__":
    unittest.main()
