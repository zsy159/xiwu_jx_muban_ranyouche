"""客户专员保客营销块 — 四行指标目录（AN–AT）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BaokeMetricSpec:
    id: str
    label: str
    metric_type: str


BAOKE_METRIC_SPECS: tuple[BaokeMetricSpec, ...] = (
    BaokeMetricSpec("phone_callback", "电话回访", "phone_callback"),
    BaokeMetricSpec("referral", "基盘客户转介绍", "referral"),
    BaokeMetricSpec("mining", "保客挖掘置换/增购", "mining"),
    BaokeMetricSpec("all_staff", "全员营销", "all_staff"),
)

BAOKE_TEMPLATES = ("left_and_baoke", "activity_summary", "baoke_store")
