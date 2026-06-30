"""分组表头宽表 HTML 渲染。"""

from __future__ import annotations

import html

import pandas as pd
import streamlit.components.v1 as components

_COL_MIN_WIDTH = 118
_VERSION_COL_WIDTH = 96
_ROW_PX = 37
_HEADER_ROWS = 2
_SCROLLBAR_PX = 16
_FRAME_PAD_PX = 6


def _group_spans(groups: list[str]) -> list[tuple[str, int]]:
    spans: list[tuple[str, int]] = []
    i = 0
    while i < len(groups):
        label = groups[i]
        span = 1
        while i + span < len(groups) and groups[i + span] == label:
            span += 1
        spans.append((label, span))
        i += span
    return spans


def grouped_matrix_html(wide: pd.DataFrame) -> str:
    """MultiIndex 列宽表 → 分组表头 HTML（版式为行索引）。"""
    if not isinstance(wide.columns, pd.MultiIndex):
        raise TypeError("wide matrix requires MultiIndex columns (分组, 字段)")

    groups = [str(g) for g, _ in wide.columns]
    fields = [str(f) for _, f in wide.columns]
    group_th = "".join(
        f'<th colspan="{span}">{html.escape(label)}</th>'
        for label, span in _group_spans(groups)
    )
    field_th = "".join(f"<th>{html.escape(f)}</th>" for f in fields)
    body = []
    for i in range(len(wide)):
        label = html.escape(str(wide.index[i]))
        cells = "".join(
            f"<td>{html.escape(str(wide.iloc[i, j]))}</td>" for j in range(len(fields))
        )
        body.append(f"<tr><th class='row-head'>{label}</th>{cells}</tr>")

    min_width = _VERSION_COL_WIDTH + len(fields) * _COL_MIN_WIDTH
    return f"""
<table style="min-width:{min_width}px">
  <thead>
    <tr><th rowspan="2" class="corner">版式</th>{group_th}</tr>
    <tr>{field_th}</tr>
  </thead>
  <tbody>{"".join(body)}</tbody>
</table>
"""


def matrix_iframe_height(wide: pd.DataFrame, *, min_height: int = 180, max_height: int = 520) -> int:
    """按版式行数计算 iframe 高度，避免末行被横向滚动条裁切。"""
    total_rows = _HEADER_ROWS + len(wide)
    raw = _FRAME_PAD_PX + total_rows * _ROW_PX + _SCROLLBAR_PX
    return max(min_height, min(max_height, raw))


def render_grouped_alignment_matrix(
    wide: pd.DataFrame,
    *,
    height: int | None = None,
) -> None:
    """iframe 内分组表头 + 强制横向滚动条。"""
    if height is None:
        height = matrix_iframe_height(wide)
    table = grouped_matrix_html(wide)
    components.html(
        f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<style>
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: #31333f;
    background: #fff;
  }}
  .scroller {{
    width: 100%;
    height: 100%;
    overflow-x: scroll;
    overflow-y: hidden;
    padding-bottom: 2px;
    border: 1px solid rgba(49, 51, 63, 0.2);
    border-radius: 0.5rem;
    -webkit-overflow-scrolling: touch;
  }}
  .scroller::-webkit-scrollbar {{
    height: 14px;
  }}
  .scroller::-webkit-scrollbar-track {{
    background: #f3f4f6;
    border-radius: 0 0 0.5rem 0.5rem;
  }}
  .scroller::-webkit-scrollbar-thumb {{
    background: #9aa0a6;
    border-radius: 7px;
    border: 2px solid #f3f4f6;
  }}
  table {{
    border-collapse: collapse;
    table-layout: fixed;
    width: max-content;
  }}
  th, td {{
    padding: 0.45rem 0.55rem;
    border: 1px solid rgba(49, 51, 63, 0.14);
    text-align: center;
    white-space: nowrap;
    min-width: {_COL_MIN_WIDTH}px;
    font-size: 13px;
  }}
  th.corner, th.row-head {{
    min-width: {_VERSION_COL_WIDTH}px;
    background: #fafafa;
    text-align: left;
    font-weight: 600;
    position: sticky;
    left: 0;
    z-index: 2;
  }}
  th.corner {{
    z-index: 3;
    background: #f0f2f6;
  }}
  thead th {{
    background: #f0f2f6;
    font-weight: 600;
  }}
  tbody tr:nth-child(even) td {{
    background: #fcfcfc;
  }}
</style>
</head>
<body>
  <div class="scroller">{table}</div>
</body>
</html>""",
        height=height,
        scrolling=False,
    )
