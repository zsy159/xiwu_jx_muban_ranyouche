"""Tests for hub frame merge loader."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from salary_pipeline.data_ingestion.hub_frame_loader import (
    COMPUTED_HUB_OVERRIDE_LETTERS,
    PAYOUT_HUB_LETTERS,
    build_hub_sumif_frame,
    read_hub_columns_by_letter,
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

    def test_merge_overrides_f_from_computed(self) -> None:
        if not COMPUTED.exists():
            self.skipTest("computed hub missing")
        merged = build_hub_sumif_frame(GOLDEN, computed_workbook=COMPUTED, letters=["D", "F"])
        computed = read_hub_columns_by_letter(COMPUTED, letters=["F", "D"])
        golden = read_hub_columns_by_letter(GOLDEN, letters=["F", "D"])
        lookup = computed.set_index(computed["D"].map(normalize_name))["F"]
        for name, f_val in lookup.items():
            if pd.isna(f_val):
                continue
            mask = golden["D"].map(normalize_name) == name
            self.assertTrue(mask.any(), f"missing golden row for {name}")
            self.assertAlmostEqual(
                float(merged.loc[mask, "F"].iloc[0]),
                float(f_val),
                places=6,
                msg=f"F mismatch for {name}",
            )

    def test_merge_only_overrides_f_through_p(self) -> None:
        if not COMPUTED.exists():
            self.skipTest("computed hub missing")
        merged = build_hub_sumif_frame(GOLDEN, computed_workbook=COMPUTED)
        golden = read_hub_columns_by_letter(GOLDEN, letters=["D", "AC", "W"])
        name = "何剑"
        g = golden[golden["D"].map(normalize_name) == name].iloc[0]
        m = merged[merged["D"].map(normalize_name) == name].iloc[0]
        self.assertEqual(float(g["AC"]), float(m["AC"]))
        self.assertEqual(float(g["W"]), float(m["W"]))

    def test_override_letters_are_f_to_p(self) -> None:
        self.assertEqual(COMPUTED_HUB_OVERRIDE_LETTERS[0], "F")
        self.assertEqual(COMPUTED_HUB_OVERRIDE_LETTERS[-1], "P")

    def test_payout_letters_subset(self) -> None:
        frame = read_hub_columns_by_letter(GOLDEN, letters=PAYOUT_HUB_LETTERS[:6])
        self.assertEqual(len(frame.columns), 6)


if __name__ == "__main__":
    unittest.main()
