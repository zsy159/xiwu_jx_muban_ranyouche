"""Trial compute progress reporting and ETA estimation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

TrialMode = Literal["full", "incremental"]

# Stage weights (sum to 100) for ETA; keys match pipeline progress_callback args.
FULL_STAGE_WEIGHTS: dict[str, tuple[float, str]] = {
    "merge_topology": (5.0, "合并账套 / 提取拓扑"),
    "check_cache": (2.0, "检查 Hub 缓存"),
    "performance_sheet": (25.0, "绩效整理表"),
    "hub_formula": (45.0, "Hub 公式回放"),
    "overlay": (20.0, "岗位绩效 overlay"),
    "export_preview": (3.0, "写出 / 预览"),
}

INCREMENTAL_STAGE_WEIGHTS: dict[str, tuple[float, str]] = {
    "merge_topology": (8.0, "合并账套 / 提取拓扑"),
    "check_cache": (4.0, "检查 Hub 缓存"),
    "load_hub": (8.0, "加载 Hub 快照"),
    "overlay": (75.0, "岗位绩效 overlay"),
    "export_preview": (5.0, "写出 / 预览"),
}

# Default total duration when no stage has completed yet (seconds).
DEFAULT_TOTAL_SECONDS: dict[TrialMode, float] = {
    "full": 10 * 60,  # mid of 8–12 min
    "incremental": 3.5 * 60,  # mid of 2–5 min
}


@dataclass(frozen=True)
class TrialProgressSnapshot:
    """Point-in-time trial progress for UI rendering."""

    mode: TrialMode
    stage_key: str
    stage_label: str
    percent: float
    elapsed_seconds: float
    remaining_seconds: float
    estimated_completion: datetime


def stage_weights(mode: TrialMode) -> dict[str, tuple[float, str]]:
    if mode == "incremental":
        return INCREMENTAL_STAGE_WEIGHTS
    return FULL_STAGE_WEIGHTS


def completed_fraction(
    mode: TrialMode,
    current_stage_key: str,
    *,
    stage_started: bool = True,
) -> float:
    """
    Fraction of weighted work done when entering (or inside) *current_stage_key*.

    When *stage_started* is True, the current stage counts as in-progress (0% of its
    weight credited). When False (stage finished), full weight is credited.
    """
    weights = stage_weights(mode)
    ordered = list(weights.keys())
    if current_stage_key not in ordered:
        return 0.0

    idx = ordered.index(current_stage_key)
    done = sum(weights[k][0] for k in ordered[:idx])
    if not stage_started:
        done += weights[current_stage_key][0]
    return done / 100.0


def estimate_remaining_seconds(
    elapsed_seconds: float,
    completed_frac: float,
    mode: TrialMode,
) -> float:
    """Estimate seconds left from elapsed time and completed weight fraction."""
    if completed_frac >= 1.0:
        return 0.0
    if completed_frac <= 0.0 or elapsed_seconds <= 0:
        return DEFAULT_TOTAL_SECONDS[mode] * (1.0 - completed_frac)

    estimated_total = elapsed_seconds / completed_frac
    return max(0.0, estimated_total - elapsed_seconds)


def format_duration(seconds: float) -> str:
    """Format seconds as Xm Ys."""
    total = int(max(0, round(seconds)))
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_completion_time(when: datetime) -> str:
    return when.strftime("%H:%M:%S")


def render_progress_markdown(snap: TrialProgressSnapshot) -> str:
    """Markdown block for Streamlit status panel."""
    return (
        f"**当前：** {snap.stage_label}  \n"
        f"**已用：** {format_duration(snap.elapsed_seconds)} · "
        f"**预计剩余：** {format_duration(snap.remaining_seconds)} · "
        f"**预计完成：** {format_completion_time(snap.estimated_completion)}"
    )


class TrialProgressReporter:
    """Tracks trial stage progress and ETA for UI callbacks."""

    def __init__(
        self,
        mode: TrialMode = "full",
        *,
        start_time: float | None = None,
    ) -> None:
        self.mode = mode
        self._start = start_time if start_time is not None else time.perf_counter()
        self._stage_key = ""
        self._stage_label = ""
        self._finished = False

    def set_mode(self, mode: TrialMode) -> None:
        self.mode = mode

    def report(self, stage_key: str, label: str | None = None) -> TrialProgressSnapshot:
        weights = stage_weights(self.mode)
        default_label = weights.get(stage_key, (0.0, stage_key))[1]
        self._stage_key = stage_key
        self._stage_label = label or default_label
        return self._snapshot(stage_started=True)

    def complete(self, label: str = "试算完成") -> TrialProgressSnapshot:
        self._finished = True
        self._stage_label = label
        return self._snapshot(stage_started=False, force_percent=100.0)

    def _snapshot(
        self,
        *,
        stage_started: bool = True,
        force_percent: float | None = None,
    ) -> TrialProgressSnapshot:
        elapsed = time.perf_counter() - self._start
        frac = (
            1.0
            if self._finished or force_percent == 100.0
            else completed_fraction(
                self.mode, self._stage_key, stage_started=stage_started
            )
        )
        percent = force_percent if force_percent is not None else min(99.0, frac * 100.0)
        if self._finished or force_percent == 100.0:
            percent = 100.0
        remaining = estimate_remaining_seconds(elapsed, frac, self.mode)
        completion = datetime.now() + timedelta(seconds=remaining)
        return TrialProgressSnapshot(
            mode=self.mode,
            stage_key=self._stage_key,
            stage_label=self._stage_label,
            percent=percent,
            elapsed_seconds=elapsed,
            remaining_seconds=remaining,
            estimated_completion=completion,
        )
