"""Tests for 新媒体底层计算器（对齐金标准 AB / Q）。"""

from __future__ import annotations

import unittest

from salary_pipeline.calculators.new_media import (
    compute_for_role,
    extract_role_inputs,
    lookup_golden_ab,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"

EXPECTED = {
    "肖廷忠": 9684.0522875817,
    "黄凤": 7240.0,
    "曾子乂": 7393.86111111111,
    "王芝婕": 8672.25,
    "蓝仁楷": 7768.65152963671,
    "何玉": 9506.0,
    "赵金秀": 3000.0,
}


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class NewMediaCalculatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))

    def test_extract_and_compute_all_seven(self) -> None:
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                inputs = extract_role_inputs(self.loader, name)
                result = compute_for_role(name, inputs)
                self.assertAlmostEqual(
                    result.hub_vehicle_performance, expected, places=2
                )

    def test_lookup_golden_ab(self) -> None:
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                golden = lookup_golden_ab(self.loader, name)
                self.assertIsNotNone(golden)
                self.assertAlmostEqual(float(golden), expected, places=4)


if __name__ == "__main__":
    unittest.main()
