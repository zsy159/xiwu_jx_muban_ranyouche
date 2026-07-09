"""Regression: empty topology.sales must not resolve to project root."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from salary_pipeline.calculators.sales_advisor.topology_specs import (
    _resolve_default_topology_path,
    load_row_specs,
)
from salary_pipeline.paths import PROJECT_ROOT, resolve_project_path


class TopologyPathResolutionTests(unittest.TestCase):
    def test_resolve_project_path_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            resolve_project_path("")

    def test_default_topology_falls_back_to_month_yaml(self) -> None:
        stub_month = {
            "month": "2026-05",
            "topology": {"sales": ""},
        }
        with mock.patch(
            "salary_pipeline.calculators.sales_advisor.topology_specs.load_month_config",
            return_value=stub_month,
        ):
            path = _resolve_default_topology_path()
        self.assertTrue(path.is_file())
        self.assertNotEqual(path.resolve(), PROJECT_ROOT.resolve())

    def test_load_row_specs_uses_explicit_topology(self) -> None:
        topo = resolve_project_path(
            "data/topology/2026-05/销售账套-合并-2026-05.topology.json"
        )
        specs = load_row_specs(32, topology_path=topo)
        self.assertIsInstance(specs, dict)


if __name__ == "__main__":
    unittest.main()
