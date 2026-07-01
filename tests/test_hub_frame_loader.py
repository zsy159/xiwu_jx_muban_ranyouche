"""Tests for hub frame loader (computed-only SUMIF source)."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from salary_pipeline.data_ingestion.hub_frame_loader import (
    PAYOUT_HUB_LETTERS,
    build_hub_sumif_frame,
    detect_hub_data_start_row,
    read_hub_columns_by_letter,
    read_hub_columns_mapped,
)
from salary_pipeline.data_ingestion.data_loader import normalize_name
from salary_pipeline.paths import PROJECT_ROOT


GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"
COMPUTED = PROJECT_ROOT / "output/2026-05/提成汇总.xlsx"


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class HubFrameLoaderTest(unittest.TestCase):
    def test_read_hub_columns_has_d_and_w(self) -> None:
        frame = read_hub_columns_by_letter(GOLDEN, letters=["D", "W", "F"])
        self.assertIn("D", frame.columns)
        self.assertIn("W", frame.columns)
        self.assertGreater(len(frame), 0)

    def test_detect_data_start_row_golden(self) -> None:
        self.assertEqual(detect_hub_data_start_row(GOLDEN), 3)

    @unittest.skipUnless(COMPUTED.exists(), "computed hub missing")
    def test_detect_data_start_row_computed_with_legend(self) -> None:
        self.assertEqual(detect_hub_data_start_row(COMPUTED), 4)

    @unittest.skipUnless(COMPUTED.exists(), "computed hub missing")
    def test_computed_only_frame_uses_computed_w_x(self) -> None:
        merged = build_hub_sumif_frame(GOLDEN, computed_workbook=COMPUTED)
        computed = read_hub_columns_mapped(COMPUTED, letters=["W", "X", "D"])
        name = "唐操"
        lookup = computed.set_index(computed["D"].map(normalize_name))
        self.assertIn(name, lookup.index)
        m = merged[merged["D"].map(normalize_name) == name].iloc[0]
        self.assertAlmostEqual(float(m["W"]), float(lookup.loc[name, "W"]), places=4)
        self.assertAlmostEqual(float(m["X"]), float(lookup.loc[name, "X"]), places=4)

    @unittest.skipUnless(COMPUTED.exists(), "computed hub missing")
    def test_computed_only_does_not_use_golden_w(self) -> None:
        merged = build_hub_sumif_frame(GOLDEN, computed_workbook=COMPUTED)
        golden = read_hub_columns_by_letter(GOLDEN, letters=["D", "W"])
        name = "唐操"
        g = golden[golden["D"].map(normalize_name) == name].iloc[0]
        m = merged[merged["D"].map(normalize_name) == name].iloc[0]
        self.assertNotAlmostEqual(
            float(m["W"]),
            float(g["W"]),
            places=2,
            msg="W must come from computed hub, not golden",
        )

    @unittest.skipUnless(COMPUTED.exists(), "computed hub missing")
    def test_all_payout_letters_from_computed(self) -> None:
        merged = build_hub_sumif_frame(GOLDEN, computed_workbook=COMPUTED)
        for letter in PAYOUT_HUB_LETTERS:
            self.assertIn(letter, merged.columns)

    def test_missing_computed_returns_empty_numeric_columns(self) -> None:
        merged = build_hub_sumif_frame(
            GOLDEN,
            computed_workbook=Path("/nonexistent/hub.xlsx"),
            letters=["D", "W"],
        )
        self.assertIn("D", merged.columns)
        self.assertTrue(merged["W"].isna().all())


if __name__ == "__main__":
    unittest.main()
