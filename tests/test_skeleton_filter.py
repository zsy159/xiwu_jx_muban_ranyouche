from __future__ import annotations

import unittest
from pathlib import Path

from salary_pipeline.data_ingestion.data_loader import (
    filter_comparable_rows,
    filter_skeleton_rows,
    read_summary_skeleton_keys,
)
from salary_pipeline.paths import PROJECT_ROOT


class TestSkeletonFilter(unittest.TestCase):
    def test_regional_advisor_without_serial_in_skeleton(self) -> None:
        golden = (
            PROJECT_ROOT
            / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"
        )
        if not golden.exists():
            self.skipTest("golden workbook not available")

        skeleton = read_summary_skeleton_keys(golden, "提成汇总", header_row=2, data_start_row=3)
        for name in ("余才万2", "余才万5"):
            self.assertFalse(
                skeleton[skeleton["姓名"] == name].empty,
                f"{name} must stay in skeleton for store-block SUM(G*:G*)",
            )

    def test_comparable_still_excludes_blank_serial(self) -> None:
        frame = __import__("pandas").DataFrame(
            [
                {"序号": 1, "姓名": "张三", "职务": "销售顾问"},
                {"序号": None, "姓名": "余才万2", "职务": "区域顾问"},
            ]
        )
        comparable = filter_comparable_rows(frame)
        skeleton = filter_skeleton_rows(frame)
        self.assertEqual(len(comparable), 1)
        self.assertEqual(len(skeleton), 2)


if __name__ == "__main__":
    unittest.main()
