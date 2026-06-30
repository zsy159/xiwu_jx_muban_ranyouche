"""销售顾问岗位族算薪类型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HubColumnFormula:
    """单 Hub 列的业务公式（由 topology 解析或 config 覆盖）。"""

    hub_column: str
    kind: str  # sumifs | sumif | sumif_chain
    perf_columns: tuple[str, ...]
    multiply_ref: str | None = None
    add_const: float = 0.0
    exclude_vehicle: str | None = None
    sumif_key_col: str = "P"
    sumif_criteria_ref: str | None = None  # e.g. E134 → 读 hub 格


@dataclass
class AdvisorPerformanceInput:
    name: str
    store: str
    title: str
    excel_row: int
    sales_completion_rate: float
    perf_frame_row_count: int = 0


@dataclass
class AdvisorPerformanceResult:
    name: str
    hub_metrics: dict[str, float] = field(default_factory=dict)
