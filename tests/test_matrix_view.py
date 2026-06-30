"""Tests for grouped matrix HTML renderer."""

from __future__ import annotations

import unittest

from salary_pipeline.app._matrix_view import grouped_matrix_html
from salary_pipeline.calculators.field_alignment import applicability_matrix_wide, load_alignment_family


class GroupedMatrixHtmlTest(unittest.TestCase):
    def test_grouped_header_colspan(self) -> None:
        wide = applicability_matrix_wide(load_alignment_family("invite_specialist"))
        html = grouped_matrix_html(wide)
        self.assertIn('colspan="4"', html)  # DMS 指标 4 列
        self.assertIn("版式", html)
        self.assertIn("西物 DCC", html)
        self.assertIn("—", html)

    def test_iframe_height_scales_with_rows(self) -> None:
        from salary_pipeline.app._matrix_view import matrix_iframe_height

        wide = applicability_matrix_wide(load_alignment_family("invite_specialist"))
        h3 = matrix_iframe_height(wide)
        wide4 = wide.copy()
        wide4.loc["保客营销店面块"] = "—"
        h4 = matrix_iframe_height(wide4)
        self.assertGreater(h4, h3)
        self.assertGreaterEqual(h4, 240)


if __name__ == "__main__":
    unittest.main()
