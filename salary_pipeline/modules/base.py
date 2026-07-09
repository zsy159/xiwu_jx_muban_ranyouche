from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


SUMMARY_KEY_COLUMNS = ["店别", "职务", "姓名"]
PERSONNEL_SHEET = "人员信息"
PERSONNEL_FILENAME = "人员信息.xlsx"


@dataclass
class ModuleResult:
    """Single business module output, keyed for summary aggregation."""

    module_name: str
    roles: list[str]
    metrics: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        missing = [col for col in SUMMARY_KEY_COLUMNS if col not in self.metrics.columns]
        if missing:
            raise ValueError(
                f"Module {self.module_name!r} metrics missing key columns: {missing}"
            )


class BaseCommissionModule(ABC):
    """Compute one business domain; returns rows aligned to summary keys."""

    name: str
    roles: list[str]

    @abstractmethod
    def run(self, context: dict[str, Any]) -> ModuleResult:
        """Run module logic and return metric columns for aggregation."""
