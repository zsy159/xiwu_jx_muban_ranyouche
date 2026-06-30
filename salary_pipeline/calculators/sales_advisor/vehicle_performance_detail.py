"""整车绩效原始数据层 — 订单级 AG 拆解与可编辑驱动项。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from salary_pipeline.calculators.performance_sheet.from_closure import (
    _compute_ag,
    _lookup_standard,
)
from salary_pipeline.calculators.performance_sheet.order_context import enrich_order_context
from salary_pipeline.data_ingestion.closure_input_sheets import load_commission_standard_frame
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name
from salary_pipeline.pipelines.performance_sheet_builder import PerformanceSheetBuilder

# 界面展示列（中文，不含 Excel 字母）
DISPLAY_COLUMNS = (
    "车架号",
    "订单号",
    "车型",
    "渠道",
    "部门",
    "台数",
    "单车提成标准",
    "标准来源",
    "单车整车绩效",
)

EDITABLE_COLUMNS = ("台数", "车型", "渠道")


@dataclass
class VehicleOrderPrimitive:
    """单笔订单的整车绩效驱动项（原始数据层）。"""

    vin: str
    order_no: str
    vehicle_type: str
    channel: str
    department: str
    units: float = 1.0
    commission_rate: float = 0.0
    rate_source: str = "提成标准"
    ag_amount: float = 0.0
    golden_ag: float | None = None

    def to_display_row(self) -> dict[str, Any]:
        return {
            "车架号": self.vin,
            "订单号": self.order_no,
            "车型": self.vehicle_type,
            "渠道": self.channel,
            "部门": self.department,
            "台数": self.units,
            "单车提成标准": self.commission_rate,
            "标准来源": self.rate_source,
            "单车整车绩效": self.ag_amount,
        }

    @classmethod
    def from_display_row(cls, row: dict[str, Any]) -> VehicleOrderPrimitive:
        return cls(
            vin=str(row.get("车架号", "")),
            order_no=str(row.get("订单号", "")),
            vehicle_type=str(row.get("车型", "")),
            channel=str(row.get("渠道", "")),
            department=str(row.get("部门", "")),
            units=float(row.get("台数", 1) or 1),
            commission_rate=float(row.get("单车提成标准", 0) or 0),
            rate_source=str(row.get("标准来源", "提成标准")),
            ag_amount=float(row.get("单车整车绩效", 0) or 0),
        )


@dataclass
class VehiclePerformanceDetail:
    """某顾问全部整车订单的原始数据层汇总。"""

    advisor_name: str
    orders: list[VehicleOrderPrimitive] = field(default_factory=list)

    @property
    def ag_sum(self) -> float:
        return sum(o.ag_amount for o in self.orders)

    @property
    def golden_ag_sum(self) -> float | None:
        vals = [o.golden_ag for o in self.orders if o.golden_ag is not None]
        if not vals:
            return None
        return float(sum(vals))

    def to_display_frame(self) -> pd.DataFrame:
        if not self.orders:
            return pd.DataFrame(columns=[*DISPLAY_COLUMNS, "金标准整车绩效"])
        rows = [o.to_display_row() for o in self.orders]
        frame = pd.DataFrame(rows)
        golden = [o.golden_ag for o in self.orders]
        if any(g is not None for g in golden):
            frame["金标准整车绩效"] = golden
        return frame


def _rate_source_label(
    department: str,
    vehicle_type: str,
    *,
    rate: float,
    matched: bool,
) -> str:
    if str(department) == "武侯自有店" and str(vehicle_type) == "星越L":
        return "星越L特例（200元/台）"
    if matched:
        return "提成标准"
    return "未匹配提成标准"


def _lookup_rate(
    standard: pd.DataFrame,
    *,
    vehicle: str,
    channel: str,
    department: str,
) -> tuple[float, bool]:
    if str(department) == "武侯自有店" and str(vehicle) == "星越L":
        return 200.0, True
    rate = _lookup_standard(
        standard,
        vehicle=vehicle,
        channel=channel,
        dept=department,
        value_col="F",
    )
    return rate, rate > 0


def _compute_order_ag(
    *,
    department: str,
    vehicle_type: str,
    channel: str,
    units: float,
    standard: pd.DataFrame,
) -> tuple[float, float, str]:
    rate, matched = _lookup_rate(
        standard,
        vehicle=vehicle_type,
        channel=channel,
        department=department,
    )
    ag = rate * units
    source = _rate_source_label(
        department, vehicle_type, rate=rate, matched=matched
    )
    return rate, ag, source


def recompute_orders(
    orders: list[VehicleOrderPrimitive],
    loader: WorkbookLoader,
) -> list[VehicleOrderPrimitive]:
    """根据可编辑驱动项重算每笔订单的提成标准与整车绩效。"""
    if not orders:
        return []
    standard = load_commission_standard_frame(loader)
    out: list[VehicleOrderPrimitive] = []
    for order in orders:
        rate, ag, source = _compute_order_ag(
            department=order.department,
            vehicle_type=order.vehicle_type,
            channel=order.channel,
            units=order.units,
            standard=standard,
        )
        out.append(
            VehicleOrderPrimitive(
                vin=order.vin,
                order_no=order.order_no,
                vehicle_type=order.vehicle_type,
                channel=order.channel,
                department=order.department,
                units=order.units,
                commission_rate=rate,
                rate_source=source,
                ag_amount=ag,
                golden_ag=order.golden_ag,
            )
        )
    return out


def recompute_from_display_frame(
    frame: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    golden_ag: list[float | None] | None = None,
) -> VehiclePerformanceDetail:
    """从 data_editor 返回的 DataFrame 重算整车绩效。"""
    orders = [VehicleOrderPrimitive.from_display_row(row) for row in frame.to_dict("records")]
    if golden_ag is not None:
        for order, g in zip(orders, golden_ag, strict=False):
            order.golden_ag = g
    recomputed = recompute_orders(orders, loader)
    advisor = ""
    return VehiclePerformanceDetail(advisor_name=advisor, orders=recomputed)


def load_vehicle_performance_detail(
    loader: WorkbookLoader,
    advisor_name: str,
    *,
    eval_perf: pd.DataFrame | None = None,
    computed_perf: pd.DataFrame | None = None,
    billing_month: str | None = None,
) -> VehiclePerformanceDetail:
    """
    加载顾问名下全部订单的整车绩效原始数据层。

  数据链：系统销售毛利（车型/渠道/部门）→ 提成标准 lookup × 台数 → 单车 AG。
    """
    builder = PerformanceSheetBuilder(loader, billing_month=billing_month)
    skeleton = builder.load_order_skeleton(source="computed")
    if skeleton.empty:
        return VehiclePerformanceDetail(advisor_name=advisor_name)

    norm = normalize_name(advisor_name)
    mask = skeleton["P"].astype(str).map(normalize_name) == norm
    advisor_skeleton = skeleton.loc[mask].copy()
    if advisor_skeleton.empty:
        return VehiclePerformanceDetail(advisor_name=advisor_name)

    ctx = enrich_order_context(advisor_skeleton, loader)
    standard = load_commission_standard_frame(loader)
    ag_series = _compute_ag(ctx, standard)

    golden_by_vin: dict[str, float] = {}
    golden_source = computed_perf if computed_perf is not None else eval_perf
    if golden_source is not None and not golden_source.empty and "O" in golden_source.columns:
        perf = golden_source.copy()
        perf["_vin"] = perf["O"].astype(str).str.strip()
        perf = perf[perf["_vin"].notna() & (perf["_vin"] != "nan")]
        if "AG" in perf.columns:
            for vin, grp in perf.groupby("_vin"):
                golden_by_vin[vin] = float(
                    pd.to_numeric(grp["AG"], errors="coerce").fillna(0).sum()
                )

    orders: list[VehicleOrderPrimitive] = []
    for idx, row in ctx.iterrows():
        sk = advisor_skeleton.loc[idx]
        vin = str(sk["O"]).strip()
        units = float(pd.to_numeric(sk.get("K"), errors="coerce") or 1.0)
        dept = str(row.get("A", ""))
        vehicle = str(row.get("H", ""))
        channel = str(row.get("I", ""))
        rate, ag, source = _compute_order_ag(
            department=dept,
            vehicle_type=vehicle,
            channel=channel,
            units=units,
            standard=standard,
        )
        orders.append(
            VehicleOrderPrimitive(
                vin=vin,
                order_no=str(sk.get("G", "")),
                vehicle_type=vehicle,
                channel=channel,
                department=dept,
                units=units,
                commission_rate=rate,
                rate_source=source,
                ag_amount=float(ag_series.loc[idx]) if idx in ag_series.index else ag,
                golden_ag=golden_by_vin.get(vin),
            )
        )

    return VehiclePerformanceDetail(advisor_name=advisor_name, orders=orders)


def detail_to_dict(detail: VehiclePerformanceDetail) -> dict[str, Any]:
    return {
        "advisor_name": detail.advisor_name,
        "orders": [asdict(o) for o in detail.orders],
        "ag_sum": detail.ag_sum,
    }


def detail_from_dict(raw: dict[str, Any]) -> VehiclePerformanceDetail:
    orders = [VehicleOrderPrimitive(**o) for o in raw.get("orders", [])]
    return VehiclePerformanceDetail(
        advisor_name=str(raw.get("advisor_name", "")),
        orders=orders,
    )
