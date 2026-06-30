"""加载岗位族字段拉通注册表。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from salary_pipeline.paths import CONFIG_DIR

_ALIGNMENT_DIR = CONFIG_DIR / "role_field_alignment"


@dataclass
class FieldDef:
    id: str
    label: str
    input_attr: str = ""
    value_type: str = "number"
    applicable: list[str] = field(default_factory=list)
    label_by_template: dict[str, str] = field(default_factory=dict)
    not_applicable_note: dict[str, str] = field(default_factory=dict)
    excel_col: Any = None
    default: Any = None
    matrix_only: bool = False


@dataclass
class FieldSection:
    id: str
    label: str
    fields: list[FieldDef]
    section_note: str = ""


@dataclass
class FieldAlignmentFamily:
    family_id: str
    family_label: str
    rules_sheet: str
    templates: dict[str, dict[str, str]]
    sections: list[FieldSection]


def _parse_field(raw: dict[str, Any]) -> FieldDef:
    return FieldDef(
        id=str(raw["id"]),
        label=str(raw["label"]),
        input_attr=str(raw.get("input_attr", "")),
        value_type=str(raw.get("value_type", "number")),
        applicable=list(raw.get("applicable", [])),
        label_by_template=dict(raw.get("label_by_template", {})),
        not_applicable_note=dict(raw.get("not_applicable_note", {})),
        excel_col=raw.get("excel_col"),
        default=raw.get("default"),
        matrix_only=bool(raw.get("matrix_only", False)),
    )


def load_alignment_family(family_id: str) -> FieldAlignmentFamily:
    path = _ALIGNMENT_DIR / f"{family_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    sections = [
        FieldSection(
            id=str(sec["id"]),
            label=str(sec["label"]),
            fields=[_parse_field(f) for f in sec.get("fields", [])],
            section_note=str(sec.get("section_note", "")),
        )
        for sec in raw.get("sections", [])
    ]
    family = FieldAlignmentFamily(
        family_id=str(raw["family_id"]),
        family_label=str(raw["family_label"]),
        rules_sheet=str(raw.get("rules_sheet", "")),
        templates=dict(raw.get("templates", {})),
        sections=sections,
    )
    if family_id == "customer_specialist":
        from salary_pipeline.calculators.field_alignment.customer_specialist import (
            enrich_customer_alignment,
        )

        return enrich_customer_alignment(family)
    return family


def list_alignment_families() -> list[tuple[str, str]]:
    if not _ALIGNMENT_DIR.is_dir():
        return []
    out: list[tuple[str, str]] = []
    for path in sorted(_ALIGNMENT_DIR.glob("*.yaml")):
        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        out.append((str(raw["family_id"]), str(raw.get("family_label", path.stem))))
    return out


def iter_fields(family: FieldAlignmentFamily):
    for section in family.sections:
        for field_def in section.fields:
            yield section, field_def
