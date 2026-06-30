"""Tests for customer specialist field alignment (必做 / 机动 / 增值)."""

from __future__ import annotations

import unittest

from salary_pipeline.calculators.customer_specialist.line_item_catalog import (
    LINE_ITEM_SECTIONS,
)
from salary_pipeline.calculators.field_alignment.customer_specialist import (
    inputs_from_values,
    load_customer_alignment,
    values_from_inputs,
)
from salary_pipeline.calculators.field_alignment.schema import load_alignment_family
from salary_pipeline.calculators.customer_specialist.types import (
    CustomerSpecialistInput,
    LeftLineItemsInput,
    LineItem,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"


class CustomerFieldAlignmentTest(unittest.TestCase):
    def test_three_left_sections_injected(self) -> None:
        family = load_alignment_family("customer_specialist")
        labels = [s.label for s in family.sections[:3]]
        self.assertEqual(labels, ["必做", "机动", "增值"])

    def test_bizuo_field_count(self) -> None:
        family = load_customer_alignment()
        bizuo = family.sections[0]
        self.assertEqual(bizuo.label, "必做")
        # 10 行项 + 整车固定额
        self.assertEqual(len(bizuo.fields), 11)

    def test_catalog_matches_excel_row_count(self) -> None:
        total = sum(len(sec.items) for sec in LINE_ITEM_SECTIONS)
        self.assertEqual(total, 38)

    def test_roundtrip_line_item_qty(self) -> None:
        base = CustomerSpecialistInput(
            template="left_and_baoke",
            left=LeftLineItemsInput(
                person="dengfang",
                line_items=[
                    LineItem(
                        category="必做",
                        item_name="3DC一网",
                        coefficient=1.5,
                        qty_dengfang=10,
                        qty_zhangbaozhen=5,
                    ),
                ],
            ),
        )
        vals = values_from_inputs(base)
        self.assertEqual(vals["line_3dc_yiwang_coefficient"], 1.5)
        self.assertEqual(vals["line_3dc_yiwang_qty_dengfang"], 10.0)
        self.assertEqual(vals["line_3dc_yiwang_qty_zhangbaozhen"], 5.0)
        restored = inputs_from_values(base, vals, "left_and_baoke")
        assert restored.left is not None
        item = next(i for i in restored.left.line_items if i.item_name == "3DC一网")
        self.assertEqual(item.qty_dengfang, 10.0)
        self.assertEqual(item.qty_zhangbaozhen, 5.0)
        self.assertEqual(item.coefficient, 1.5)

    def test_baoke_section_has_sixteen_fields(self) -> None:
        family = load_customer_alignment()
        baoke = next(s for s in family.sections if s.id == "baoke_block")
        # 4 metrics × 4 fields + phone flat = 17
        self.assertEqual(len(baoke.fields), 17)


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class CustomerFieldAlignmentExtractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))

    def test_dengfang_values_cover_all_line_items(self) -> None:
        from salary_pipeline.calculators.customer_specialist import extract_role_inputs

        inputs = extract_role_inputs(self.loader, "邓芳")
        vals = values_from_inputs(inputs)
        assert inputs.left is not None
        self.assertEqual(len(inputs.left.line_items), 38)
        for spec in LINE_ITEM_SECTIONS[0].items:
            self.assertIn(f"line_{spec.id}_qty_dengfang", vals)
            self.assertIn(f"line_{spec.id}_achievement_rate", vals)


if __name__ == "__main__":
    unittest.main()
