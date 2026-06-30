"""跨版式岗位字段拉通。"""

from salary_pipeline.calculators.field_alignment.schema import (
    FieldAlignmentFamily,
    FieldDef,
    FieldSection,
    load_alignment_family,
    list_alignment_families,
)
from salary_pipeline.calculators.field_alignment.invite_specialist import (
    applicability_matrix,
    applicability_matrix_display,
    applicability_matrix_wide,
    field_label_for_template,
    inputs_from_values,
    is_field_applicable,
    not_applicable_reason,
    values_from_inputs,
)

__all__ = [
    "FieldAlignmentFamily",
    "FieldDef",
    "FieldSection",
    "applicability_matrix",
    "applicability_matrix_display",
    "applicability_matrix_wide",
    "field_label_for_template",
    "inputs_from_values",
    "is_field_applicable",
    "list_alignment_families",
    "load_alignment_family",
    "not_applicable_reason",
    "values_from_inputs",
]
