"""Tests for golden 绩效整理表 parity skip rules."""

from __future__ import annotations

import unittest
from pathlib import Path

from salary_pipeline.paths import PROJECT_ROOT
from salary_pipeline.validation.golden_perf_skips import (
    hub_parity_skip_erwang_blank_ah,
    is_golden_erwang_channel,
    load_computed_ah_by_vin,
    load_golden_erwang_blank_ah_adjustments,
)

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"
COMPUTED_PERF = PROJECT_ROOT / "output/2026-05/绩效整理表-系统生成.xlsx"


class GoldenPerfSkipsTests(unittest.TestCase):
    def test_is_golden_erwang_channel(self) -> None:
        self.assertTrue(is_golden_erwang_channel("直营店二网"))
        self.assertFalse(is_golden_erwang_channel("自有店"))
        self.assertFalse(is_golden_erwang_channel("分公司"))

    @unittest.skipUnless(GOLDEN.exists() and COMPUTED_PERF.exists(), "fixtures missing")
    def test_puxi_erwang_adjustment_matches_vin(self) -> None:
        computed_ah = load_computed_ah_by_vin(COMPUTED_PERF)
        adjustments = load_golden_erwang_blank_ah_adjustments(GOLDEN, computed_ah)
        self.assertIn("蒲喜", adjustments)
        self.assertAlmostEqual(adjustments["蒲喜"], -216.72, places=2)
        self.assertTrue(
            hub_parity_skip_erwang_blank_ah(
                "蒲喜",
                "权限结余绩效",
                -747.3054,
                -964.0254,
                adjustments,
                tolerance=0.01,
            )
        )


if __name__ == "__main__":
    unittest.main()
