"""Hub dual-layer parity tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from salary_pipeline.observability.models import (
    gated_performance_report_from_dict,
    parity_report_from_dict,
    performance_report_from_dict,
)
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config
from salary_pipeline.validation.parity import compare_hub_parity_bundle


GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"
COMPUTED = PROJECT_ROOT / "output/2026-05/提成汇总.xlsx"


@unittest.skipUnless(GOLDEN.exists() and COMPUTED.exists(), "fixtures missing")
class HubParityBundleTest(unittest.TestCase):
    def test_bundle_has_performance_section(self) -> None:
        cfg = load_month_config(CONFIG_DIR)
        bundle = compare_hub_parity_bundle(
            COMPUTED,
            GOLDEN,
            cfg["parity"]["golden_sheet"],
            cfg["parity"],
        )
        self.assertTrue(bundle.metrics.overall_passed)
        self.assertIsNotNone(bundle.performance)
        assert bundle.performance is not None
        self.assertGreater(len(bundle.performance.compared_columns), 10)

        data = bundle.to_dict()
        self.assertIn("sections", data)
        perf = performance_report_from_dict(data)
        self.assertIsNotNone(perf)
        restored = parity_report_from_dict(data)
        self.assertTrue(restored.overall_passed)

    def test_bundle_has_gated_performance_section(self) -> None:
        cfg = load_month_config(CONFIG_DIR)
        bundle = compare_hub_parity_bundle(
            COMPUTED,
            GOLDEN,
            cfg["parity"]["golden_sheet"],
            cfg["parity"],
        )
        self.assertIsNotNone(bundle.gated_performance)
        assert bundle.gated_performance is not None
        self.assertTrue(bundle.gated_performance.overall_passed)
        gated = gated_performance_report_from_dict(bundle.to_dict())
        self.assertIsNotNone(gated)
        assert gated is not None
        self.assertTrue(gated.overall_passed)


if __name__ == "__main__":
    unittest.main()
