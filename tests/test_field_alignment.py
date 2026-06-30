"""Tests for role field alignment registry."""

from __future__ import annotations

import unittest

from salary_pipeline.calculators.field_alignment import (
    applicability_matrix,
    applicability_matrix_wide,
    is_field_applicable,
    load_alignment_family,
    not_applicable_reason,
)
from salary_pipeline.calculators.field_alignment.invite_specialist import (
    inputs_from_values,
    values_from_inputs,
)
from salary_pipeline.calculators.invite_specialist.types import InviteDccInput


class InviteFieldAlignmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.family = load_alignment_family("invite_specialist")

    def test_cool_models_only_chaoshi(self) -> None:
        field = next(
            f
            for _, f in (
                (s, fd)
                for s in self.family.sections
                for fd in s.fields
            )
            if f.id == "achieved_invite_volume"
        )
        self.assertTrue(is_field_applicable(field, "chaoshi_dcc"))
        self.assertFalse(is_field_applicable(field, "xiwu_dcc"))
        self.assertIn("P 列", not_applicable_reason(field, "xiwu_dcc"))

    def test_invite_rate_bonus_not_chaoshi(self) -> None:
        field = next(
            f
            for s in self.family.sections
            for f in s.fields
            if f.id == "invite_rate_bonus_per_group"
        )
        self.assertFalse(is_field_applicable(field, "chaoshi_dcc"))
        self.assertTrue(is_field_applicable(field, "xiwu_dcc"))

    def test_pickup_400_all_templates(self) -> None:
        field = next(
            f
            for s in self.family.sections
            for f in s.fields
            if f.id == "call_answer_penalty"
        )
        for tpl in ("xiwu_dcc", "chaoshi_dcc", "chongzhou_invite"):
            self.assertTrue(is_field_applicable(field, tpl))

    def test_task_penalty_not_xiwu(self) -> None:
        field = next(
            f
            for s in self.family.sections
            for f in s.fields
            if f.id == "task_penalty"
        )
        self.assertFalse(is_field_applicable(field, "xiwu_dcc"))
        self.assertTrue(is_field_applicable(field, "chaoshi_dcc"))

    def test_invite_task_target_xiwu_aa(self) -> None:
        field = next(
            f
            for s in self.family.sections
            for f in s.fields
            if f.id == "invite_task_target"
        )
        self.assertTrue(is_field_applicable(field, "xiwu_dcc"))
        self.assertEqual(field.excel_col["xiwu_dcc"], "AA")
        self.assertEqual(field.excel_col["chongzhou_invite"], "AA")

    def test_matrix_has_three_templates(self) -> None:
        matrix = applicability_matrix(self.family)
        self.assertEqual(len(matrix.columns), 5)  # 分组, 字段, 3 templates
        self.assertEqual(len(matrix), 19)

    def test_matrix_wide_fields_as_columns(self) -> None:
        wide = applicability_matrix_wide(self.family)
        self.assertEqual(len(wide), 3)
        self.assertEqual(wide.index.name, "版式")
        self.assertEqual(list(wide.columns.names), ["分组", "字段"])
        self.assertEqual(len(wide.columns), 19)

    def test_roundtrip_inputs(self) -> None:
        base = InviteDccInput(invite_groups=38, achieved_invite_volume=6)
        vals = values_from_inputs(base)
        restored = inputs_from_values(None, vals)
        self.assertEqual(restored.invite_groups, 38)
        self.assertEqual(restored.achieved_invite_volume, 6)


if __name__ == "__main__":
    unittest.main()
