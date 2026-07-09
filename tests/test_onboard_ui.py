"""Streamlit 新月接入页 helper 单元测试。"""

from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from openpyxl import Workbook

from salary_pipeline.app.onboard_helpers import (
    RULE_CANONICAL,
    UPLOAD_MODE_FULL,
    UPLOAD_MODE_SHEETS,
    auto_conflict_resolutions,
    consolidated_workbook_path,
    default_label_for_month,
    default_rule_mode_label,
    list_inherit_source_months,
    prepare_onboard_from_sheet_uploads,
    sales_relative_path,
    sales_save_path,
    save_sales_workbook,
    validate_month_id,
)
from salary_pipeline.ingestion_upload.file_intake import (
    IntakeResult,
    SheetMatch,
    SheetMatchStatus,
    UploadedFile,
    normalize_streamlit_upload_files,
    pairs_from_streamlit_files,
)
from salary_pipeline.ingestion_upload.manifest import RequiredSheet
from salary_pipeline.observability.models import MonthInfo
from salary_pipeline.paths import PROJECT_ROOT


def _workbook_bytes(sheet_name: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = sheet_name
    ws["A1"] = "test"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _zip_bytes(*inner: tuple[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in inner:
            zf.writestr(name, data)
    return buf.getvalue()


class OnboardUiHelpersTest(unittest.TestCase):
    def test_validate_month_id_ok(self) -> None:
        self.assertIsNone(validate_month_id("2026-07"))
        self.assertIsNone(validate_month_id(" 2026-12 "))

    def test_validate_month_id_errors(self) -> None:
        self.assertEqual(validate_month_id(""), "账期不能为空")
        self.assertEqual(validate_month_id("2026-7"), "账期格式须为 YYYY-MM（如 2026-07）")
        self.assertEqual(validate_month_id("26-07"), "账期格式须为 YYYY-MM（如 2026-07）")

    def test_default_label_for_month(self) -> None:
        self.assertEqual(default_label_for_month("2026-07"), "2026年07月")

    def test_sales_save_path_uses_original_xlsx_name(self) -> None:
        path = sales_save_path("2026-08", "我的销售账套.xlsx")
        self.assertEqual(path.name, "我的销售账套.xlsx")
        self.assertIn("2026-08", str(path))

    def test_sales_save_path_fallback_name(self) -> None:
        path = sales_save_path("2026-08", "upload.bin")
        self.assertEqual(path.name, "销售账套-合并-2026-08.xlsx")

    def test_save_sales_workbook_writes_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch(
                "salary_pipeline.app.onboard_helpers.raw_month_dir",
                return_value=tmp_path / "data" / "raw" / "2099-01",
            ):
                saved = save_sales_workbook("2099-01", b"PK\x03\x04", "test.xlsx")
            self.assertTrue(saved.exists())
            self.assertEqual(saved.read_bytes(), b"PK\x03\x04")

    def test_sales_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file_path = root / "data" / "raw" / "2026-09" / "sales.xlsx"
            file_path.parent.mkdir(parents=True)
            file_path.write_bytes(b"x")
            with mock.patch(
                "salary_pipeline.app.onboard_helpers.PROJECT_ROOT", root
            ):
                rel = sales_relative_path(file_path)
            self.assertEqual(rel, "data/raw/2026-09/sales.xlsx")

    def test_list_inherit_source_months_excludes_target(self) -> None:
        fake_months = [
            MonthInfo("2026-02", "2026年02月", "imported", True, True, "month-2026-02.yaml"),
            MonthInfo("2026-05", "2026年05月", "imported", True, True, "month-2026-05.yaml"),
        ]
        with mock.patch(
            "salary_pipeline.app.onboard_helpers.discover_months",
            return_value=fake_months,
        ):
            sources = list_inherit_source_months("2026-05")
        self.assertEqual(sources, ["2026-02"])

    def test_default_rule_mode_label(self) -> None:
        label = default_rule_mode_label()
        self.assertIn("2026-05", label)

    def test_rule_canonical_constant(self) -> None:
        self.assertEqual(RULE_CANONICAL, "canonical")

    def test_upload_mode_constants(self) -> None:
        self.assertEqual(UPLOAD_MODE_FULL, "full")
        self.assertEqual(UPLOAD_MODE_SHEETS, "sheets")

    def test_consolidated_workbook_path(self) -> None:
        with mock.patch(
            "salary_pipeline.app.onboard_helpers.raw_month_dir",
            return_value=Path("data/raw/2099-03"),
        ):
            path = consolidated_workbook_path("2099-03")
        self.assertEqual(path.name, "销售账套-合并-2099-03.xlsx")

    def test_auto_conflict_resolutions_prefers_sales_workbook(self) -> None:
        sales = Path("/tmp/西物销售提成.xlsx")
        intake = IntakeResult(
            month_id="2099-04",
            staging_dir=Path("/tmp/staging"),
            uploads=[
                UploadedFile("西物销售提成.xlsx", sales, 1, ["终端明细表"]),
                UploadedFile("补充.xlsx", Path("/tmp/补充.xlsx"), 1, ["终端明细表"]),
            ],
            matches=[
                SheetMatch(
                    required=RequiredSheet(name="终端明细表"),
                    status=SheetMatchStatus.CONFLICT,
                    sources=["西物销售提成.xlsx", "补充.xlsx"],
                    resolved_name="终端明细表",
                )
            ],
            sales_workbook=sales,
        )
        resolutions = auto_conflict_resolutions(intake)
        self.assertEqual(resolutions["终端明细表"], "西物销售提成.xlsx")

    def test_prepare_onboard_from_sheet_uploads_empty(self) -> None:
        result = prepare_onboard_from_sheet_uploads("2099-05", [])
        self.assertEqual(result.errors, ["请至少上传一个 Excel 或 ZIP 文件"])

    def test_prepare_onboard_from_sheet_uploads_zip_extracts_xlsx(self) -> None:
        inner_name = "直营店经理提成 (财务).xlsx"
        inner_data = _workbook_bytes("直营店经理提成 (财务)")
        bundle = _zip_bytes((inner_name, inner_data))
        uploads = [("燃油车-2026年05月管理部(财务).zip", bundle)]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            month_dir = tmp_path / "data" / "raw" / "2099-07"
            with mock.patch(
                "salary_pipeline.app.onboard_helpers.raw_month_dir",
                return_value=month_dir,
            ):
                result = prepare_onboard_from_sheet_uploads("2099-07", uploads)
            extracted = month_dir / ".onboard_staging" / "uploads" / inner_name
            self.assertTrue(extracted.exists(), "ZIP 内 xlsx 应解压至 staging/uploads/")
            self.assertFalse(
                any("仅支持" in err or "未找到有效的" in err or "ZIP 文件无效" in err for err in result.errors),
                msg=f"unexpected intake errors: {result.errors}",
            )
            self.assertTrue(
                any("缺失" in err for err in result.errors),
                "单表 ZIP 应继续走工作表匹配并提示缺失必需表",
            )

    def test_prepare_onboard_from_sheet_uploads_missing_required(self) -> None:
        uploads = [("only.xlsx", _workbook_bytes("无关表"))]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch(
                "salary_pipeline.app.onboard_helpers.raw_month_dir",
                return_value=tmp_path / "data" / "raw" / "2099-06",
            ):
                result = prepare_onboard_from_sheet_uploads("2099-06", uploads)
        self.assertTrue(result.errors)
        self.assertIsNone(result.sales_path)
        self.assertTrue(any("缺失" in err for err in result.errors))


class OnboardPageUploadConfigTest(unittest.TestCase):
    """新月接入页 file_uploader 须与发薪上传一致（表单外 + 多选 + ZIP）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.page_path = (
            PROJECT_ROOT / "salary_pipeline" / "app" / "pages" / "0_新月接入.py"
        )
        cls.payroll_path = (
            PROJECT_ROOT / "salary_pipeline" / "app" / "pages" / "0_发薪上传.py"
        )
        cls.page_source = cls.page_path.read_text(encoding="utf-8")
        cls.payroll_source = cls.payroll_path.read_text(encoding="utf-8")

    def test_sheet_uploader_outside_form_with_multi_and_zip(self) -> None:
        self.assertNotIn(
            "st.form(",
            self.page_source,
            "file_uploader 放在 st.form 内会导致 macOS 无法多选",
        )
        self.assertIn("accept_multiple_files=True", self.page_source)
        self.assertIn("STREAMLIT_UPLOAD_ACCEPT", self.page_source)
        self.assertIn('type=["xlsx"]', self.page_source)

    def test_page_defaults_to_canonical_rules(self) -> None:
        self.assertIn("RULE_CANONICAL", self.page_source)
        self.assertIn("使用系统固化规则", self.page_source)
        self.assertIn("data/topology/2026-05/", self.page_source)

    def test_payroll_page_same_upload_pattern(self) -> None:
        for needle in ("STREAMLIT_UPLOAD_ACCEPT", "accept_multiple_files=True"):
            self.assertIn(needle, self.payroll_source)
            self.assertIn(needle, self.page_source)


class StreamlitUploadNormalizeTest(unittest.TestCase):
    def test_normalize_empty(self) -> None:
        self.assertEqual(normalize_streamlit_upload_files(None), [])

    def test_normalize_single_object(self) -> None:
        fake = mock.Mock(name="uploaded.xlsx")
        self.assertEqual(normalize_streamlit_upload_files(fake), [fake])

    def test_pairs_from_single_upload(self) -> None:
        fake = mock.Mock()
        fake.name = "a.xlsx"
        fake.getvalue.return_value = b"PK"
        self.assertEqual(pairs_from_streamlit_files(fake), [("a.xlsx", b"PK")])


if __name__ == "__main__":
    unittest.main()
