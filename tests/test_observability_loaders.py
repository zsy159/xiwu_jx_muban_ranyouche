"""Tests for observability loaders."""

from __future__ import annotations

import unittest

from salary_pipeline.observability.loaders import (
    discover_months,
    find_latest_parity_report,
    get_anchor_snapshots,
    load_month_config_for,
    load_parity_report,
    render_acceptance_markdown,
    build_acceptance_summary,
)
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path


class ObservabilityLoadersTest(unittest.TestCase):
    def test_discover_months_includes_2026_05(self) -> None:
        months = discover_months()
        ids = [m.month_id for m in months]
        self.assertIn("2026-05", ids)

    def test_load_month_config_for_default_month(self) -> None:
        cfg = load_month_config_for("2026-05")
        self.assertEqual(cfg["month"], "2026-05")

    def test_find_latest_hub_report(self) -> None:
        report_dir = PROJECT_ROOT / "output/2026-05/reports"
        if not report_dir.exists():
            self.skipTest("no reports")
        path = find_latest_parity_report(
            report_dir, computed_match="提成汇总.xlsx"
        )
        self.assertIsNotNone(path)
        report = load_parity_report(path)
        self.assertGreater(len(report.roles), 0)

    def test_anchor_snapshots_hub(self) -> None:
        snaps = get_anchor_snapshots("2026-05")
        hub = next(s for s in snaps if s.anchor_id == "hub")
        self.assertTrue(hub.has_output or hub.report_path is None)

    def test_acceptance_markdown(self) -> None:
        summary = build_acceptance_summary("2026-05")
        md = render_acceptance_markdown(summary)
        self.assertIn("验收摘要", md)
        self.assertIn("提成汇总", md)


if __name__ == "__main__":
    unittest.main()
