"""Tests for new media role field alignment registry."""

from __future__ import annotations

import unittest

from salary_pipeline.calculators.field_alignment.new_media import (
    applicability_matrix_wide,
    inputs_from_values,
    is_field_applicable,
    load_new_media_alignment,
    not_applicable_reason,
    values_from_inputs,
)
from salary_pipeline.calculators.new_media.types import LiveAnchorInput, MetricPair


class NewMediaFieldAlignmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.family = load_new_media_alignment()

    def test_manual_only_performance_salary(self) -> None:
        field = next(
            f
            for s in self.family.sections
            for f in s.fields
            if f.id == "performance_salary"
        )
        self.assertTrue(is_field_applicable(field, "manual"))
        self.assertFalse(is_field_applicable(field, "live_anchor"))

    def test_fans_only_live_anchor(self) -> None:
        field = next(
            f
            for s in self.family.sections
            for f in s.fields
            if f.id == "fans"
        )
        self.assertTrue(is_field_applicable(field, "live_anchor"))
        self.assertFalse(is_field_applicable(field, "video_ops"))
        self.assertIn("短视频", not_applicable_reason(field, "video_ops"))

    def test_matrix_has_four_templates(self) -> None:
        wide = applicability_matrix_wide(self.family)
        self.assertEqual(len(wide), 4)
        self.assertEqual(len(wide.columns), 19)

    def test_metric_pair_roundtrip(self) -> None:
        base = LiveAnchorInput(
            live_sessions=MetricPair(target=90, actual=82),
            leads=MetricPair(target=523, actual=580),
        )
        flat = values_from_inputs(base)
        self.assertEqual(flat["live_sessions_target"], 90)
        self.assertEqual(flat["live_sessions_actual"], 82)
        restored = inputs_from_values(base, {}, "live_anchor")
        self.assertEqual(restored.live_sessions.target, 90)
        self.assertEqual(restored.live_sessions.actual, 82)

    def test_track_session_excess_checkbox_field(self) -> None:
        field = next(
            f
            for s in self.family.sections
            for f in s.fields
            if f.id == "track_session_excess"
        )
        self.assertEqual(field.value_type, "checkbox")
        self.assertTrue(is_field_applicable(field, "live_anchor"))


if __name__ == "__main__":
    unittest.main()
