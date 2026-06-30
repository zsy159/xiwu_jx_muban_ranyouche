#!/usr/bin/env python3
"""Dependency closure report from formula topology JSON, anchored on an output sheet."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOPOLOGY = (
    PROJECT_ROOT
    / "data"
    / "topology"
    / "2026-05"
    / "燃油车-2026年05月西物超市销售提成(终)(1).topology.json"
)
SHEET_REGISTRY = PROJECT_ROOT / "salary_pipeline" / "config" / "sheet_registry.yaml"


def split_sheet_ref(ref: str) -> tuple[str, str]:
    sheet, _, addr = ref.partition("!")
    return sheet, addr


def load_sheet_roles() -> dict[str, str]:
    if not SHEET_REGISTRY.exists():
        return {}
    data = yaml.safe_load(SHEET_REGISTRY.read_text(encoding="utf-8")) or {}
    roles: dict[str, str] = {}
    for section in data.values():
        if not isinstance(section, dict):
            continue
        for sheet_name, meta in section.items():
            if isinstance(meta, dict) and "role" in meta:
                roles[sheet_name] = meta["role"]
    return roles


def list_topology_sheets(topology: dict[str, Any]) -> list[dict[str, Any]]:
    cells: dict[str, dict[str, Any]] = topology["cells"]
    counts: dict[str, int] = defaultdict(int)
    for info in cells.values():
        counts[info["sheet"]] += 1
    rows = []
    for name in topology["meta"]["sheet_names"]:
        rows.append({"sheet": name, "formula_cells": counts.get(name, 0)})
    return rows


def suggest_sheet_name(target: str, candidates: list[str]) -> list[str]:
    target_norm = target.strip().lower()
    scored: list[tuple[int, str]] = []
    for name in candidates:
        name_norm = name.strip().lower()
        if target_norm in name_norm or name_norm in target_norm:
            scored.append((0, name))
        elif target_norm.replace(" ", "") == name_norm.replace(" ", ""):
            scored.append((1, name))
    scored.sort(key=lambda item: (item[0], len(item[1])))
    return [name for _, name in scored[:5]]


def build_closure(
    topology: dict[str, Any],
    anchor_sheet: str,
) -> dict[str, Any]:
    cells: dict[str, dict[str, Any]] = topology["cells"]
    all_sheets: list[str] = topology["meta"]["sheet_names"]
    formula_sheets = {info["sheet"] for info in cells.values()}

    if anchor_sheet not in all_sheets:
        hints = suggest_sheet_name(anchor_sheet, all_sheets)
        hint = f" Did you mean: {', '.join(hints)}?" if hints else ""
        raise ValueError(f"Anchor sheet not in workbook: {anchor_sheet}.{hint}")

    anchor_cells = sorted(
        key for key, info in cells.items() if info["sheet"] == anchor_sheet
    )
    if not anchor_cells:
        raise ValueError(f"No formula cells found for anchor sheet: {anchor_sheet}")

    visited_formula_cells: set[str] = set()
    static_cell_refs: set[str] = set()
    range_refs: set[str] = set()
    queue: deque[str] = deque(anchor_cells)
    cell_depth: dict[str, int] = {key: 0 for key in anchor_cells}
    sheet_edges: dict[tuple[str, str], int] = defaultdict(int)

    def record_edge(from_sheet: str, to_ref: str) -> None:
        to_sheet = split_sheet_ref(to_ref)[0]
        if to_sheet and to_sheet != from_sheet:
            sheet_edges[(from_sheet, to_sheet)] += 1

    def visit_cell(key: str) -> None:
        if key in visited_formula_cells:
            return
        visited_formula_cells.add(key)
        info = cells[key]
        from_sheet = info["sheet"]
        depth = cell_depth.get(key, 0)
        for dep in info.get("depends_on", []):
            record_edge(from_sheet, dep)
            if dep in cells:
                if dep not in cell_depth or cell_depth[dep] > depth + 1:
                    cell_depth[dep] = depth + 1
                queue.append(dep)
            else:
                static_cell_refs.add(dep)
        for range_ref in info.get("depends_on_ranges", []):
            range_refs.add(range_ref)
            record_edge(from_sheet, range_ref)

    while queue:
        visit_cell(queue.popleft())

    # SUMIF 等通过整列区域引用上游公式表时，需展开该 sheet 内全部公式格再继续追溯。
    while True:
        progress = False
        range_sheets = {split_sheet_ref(ref)[0] for ref in range_refs}
        for sheet in range_sheets:
            if sheet not in formula_sheets:
                continue
            before = len(visited_formula_cells)
            for key, info in cells.items():
                if info["sheet"] == sheet:
                    queue.append(key)
            while queue:
                visit_cell(queue.popleft())
            if len(visited_formula_cells) > before:
                progress = True
        if not progress:
            break

    closure_formula_sheets = sorted(
        {cells[key]["sheet"] for key in visited_formula_cells}
    )
    referenced_sheets = sorted(
        {split_sheet_ref(ref)[0] for ref in static_cell_refs}
        | {split_sheet_ref(ref)[0] for ref in range_refs}
    )
    input_data_sheets = sorted(
        sheet
        for sheet in referenced_sheets
        if sheet not in closure_formula_sheets or sheet == anchor_sheet
    )
    pure_input_sheets = sorted(
        sheet for sheet in referenced_sheets if sheet not in formula_sheets
    )
    intermediate_formula_sheets = sorted(
        sheet
        for sheet in closure_formula_sheets
        if sheet != anchor_sheet and sheet in formula_sheets
    )

    sheet_formula_counts: dict[str, int] = defaultdict(int)
    sheet_min_depth: dict[str, int] = {}
    for key in visited_formula_cells:
        sheet = cells[key]["sheet"]
        sheet_formula_counts[sheet] += 1
        depth = cell_depth.get(key, 0)
        if sheet not in sheet_min_depth or depth < sheet_min_depth[sheet]:
            sheet_min_depth[sheet] = depth

    static_refs_by_sheet: dict[str, list[str]] = defaultdict(list)
    for ref in sorted(static_cell_refs):
        static_refs_by_sheet[split_sheet_ref(ref)[0]].append(ref)

    roles = load_sheet_roles()
    unregistered_sheets = sorted(
        {
            sheet
            for sheet in set(referenced_sheets) | set(closure_formula_sheets)
            if sheet not in roles
        }
    )

    edge_rows = [
        {
            "from": src,
            "to": dst,
            "ref_count": count,
            "from_role": roles.get(src, "unregistered"),
            "to_role": roles.get(dst, "unregistered"),
        }
        for (src, dst), count in sorted(
            sheet_edges.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )
    ]

    return {
        "meta": {
            "source_topology": topology["meta"]["source_file"],
            "anchor_sheet": anchor_sheet,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "workbook_sheet_count": len(all_sheets),
        },
        "counts": {
            "anchor_formula_cells": len(anchor_cells),
            "closure_formula_cells": len(visited_formula_cells),
            "static_cell_refs": len(static_cell_refs),
            "range_refs": len(range_refs),
            "closure_formula_sheets": len(closure_formula_sheets),
            "input_data_sheets": len(input_data_sheets),
            "pure_input_sheets": len(pure_input_sheets),
            "sheet_dependency_edges": len(edge_rows),
        },
        "closure_formula_sheets": closure_formula_sheets,
        "intermediate_formula_sheets": intermediate_formula_sheets,
        "input_data_sheets": input_data_sheets,
        "pure_input_sheets": pure_input_sheets,
        "sheet_formula_counts": dict(
            sorted(sheet_formula_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "sheet_min_depth_from_anchor": dict(
            sorted(sheet_min_depth.items(), key=lambda item: (item[1], item[0]))
        ),
        "sheet_dependency_edges": edge_rows[:200],
        "range_refs": sorted(range_refs),
        "static_cell_refs": sorted(static_cell_refs),
        "static_refs_by_sheet": {
            sheet: refs[:50] for sheet, refs in sorted(static_refs_by_sheet.items())
        },
        "static_refs_by_sheet_truncated": {
            sheet: len(refs) > 50 for sheet, refs in static_refs_by_sheet.items()
        },
        "sheet_roles_from_registry": {
            sheet: roles.get(sheet, "unregistered") for sheet in closure_formula_sheets
        },
        "unregistered_sheets": unregistered_sheets,
        "out_of_closure_workbook_sheets": sorted(
            set(all_sheets) - set(closure_formula_sheets) - set(referenced_sheets)
        ),
    }


def render_mermaid(report: dict[str, Any], max_edges: int = 25) -> str:
    anchor = report["meta"]["anchor_sheet"]
    lines = ["```mermaid", "flowchart BT"]
    seen_nodes: set[str] = {anchor}
    for edge in report["sheet_dependency_edges"][:max_edges]:
        src = edge["from"].replace('"', "'")
        dst = edge["to"].replace('"', "'")
        lines.append(f'  "{src}" -->|"x{edge["ref_count"]}"| "{dst}"')
        seen_nodes.add(edge["from"])
        seen_nodes.add(edge["to"])
    if anchor in seen_nodes:
        safe_anchor = anchor.replace('"', "'")
        lines.append(f'  class "{safe_anchor}" anchor;')
        lines.append("  classDef anchor fill:#ffe8a3,stroke:#b58900;")
    lines.append("```")
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    meta = report["meta"]
    counts = report["counts"]
    anchor = meta["anchor_sheet"]
    roles = report["sheet_roles_from_registry"]
    lines = [
        f"# 依赖闭包报告 — {anchor}",
        "",
        f"- 来源拓扑：`{meta['source_topology']}`",
        f"- 生成时间：{meta['generated_at']}",
        f"- 工作簿 sheet 总数：{meta['workbook_sheet_count']}",
        "",
        "## 术语说明",
        "",
        "本报告从**锚点表**出发，沿公式依赖**向上追溯**（BFS），回答「要算出这张表，最少涉及哪些 sheet」。",
        "",
        f"- **锚点表**：`{anchor}`。闭包方向是**上游**（算它需要什么），不是下游（谁用它）。",
        "- **闭包公式 sheet**：闭包内且含公式格的 sheet，需用代码重算或理解其公式逻辑。",
        "- **中间公式 sheet**：闭包公式 sheet 去掉锚点本身。",
        "- **输入数据 sheet**：被闭包内公式引用到、需当原始数据读入的 sheet。",
        "- **纯输入 sheet**：被引用且整张工作簿无公式格。",
        "- **深度**：距锚点表的最少依赖跳数，越小越靠近最终输出。",
        "- **区域展开**：对 `SUMIF(提成汇总!D:D, …, 提成汇总!F:F)` 类整列引用，会将目标公式 sheet 全部公式格纳入闭包后继续向上追溯。",
        "",
        "**业务提示：** `提成汇总` 是汇总枢纽（hub），`XW提成-发` 等是最终发薪表（output）。",
        "以 `提成汇总` 为锚时，`XW提成-发` 出现在闭包内多因汇总表 BB/BC 等列**回引**发薪表；",
        "以 `XW提成-发` 为锚时，`提成汇总` 会作为**上游**出现（发薪表约 55% 公式格从汇总表 SUMIF 取数）。",
        "",
        "## 统计",
        "",
        f"- 锚点公式格：{counts['anchor_formula_cells']}",
        f"- 闭包公式格：{counts['closure_formula_cells']}",
        f"- 静态单元格引用：{counts['static_cell_refs']}",
        f"- 区域引用：{counts['range_refs']}",
        f"- 闭包内公式 sheet：{counts['closure_formula_sheets']}",
        f"- 输入数据 sheet（被引用）：{counts['input_data_sheets']}",
        f"- 纯输入 sheet（无公式）：{counts['pure_input_sheets']}",
        f"- sheet 级依赖边：{counts['sheet_dependency_edges']}",
        "",
        "## 闭包公式 sheet（含深度与公式格数）",
        "",
        "| sheet | role | 深度 | 闭包内公式格 |",
        "| --- | --- | ---: | ---: |",
    ]
    depth_map = report["sheet_min_depth_from_anchor"]
    count_map = report["sheet_formula_counts"]
    for sheet in report["closure_formula_sheets"]:
        role = roles.get(sheet, "unregistered")
        depth = depth_map.get(sheet, "-")
        cell_count = count_map.get(sheet, 0)
        lines.append(f"| `{sheet}` | {role} | {depth} | {cell_count} |")

    lines.extend(["", "## 主要 sheet 依赖边（按引用次数 Top 25）", ""])
    lines.extend(
        [
            "| from | to | 引用次数 | from_role | to_role |",
            "| --- | --- | ---: | --- | --- |",
        ]
    )
    for edge in report["sheet_dependency_edges"][:25]:
        lines.append(
            f"| `{edge['from']}` | `{edge['to']}` | {edge['ref_count']} | "
            f"{edge['from_role']} | {edge['to_role']} |"
        )

    lines.extend(["", "## 依赖关系简图（Top 边）", "", render_mermaid(report), ""])

    lines.extend(["", "## 中间公式 sheet（非锚点）", ""])
    for sheet in report["intermediate_formula_sheets"]:
        lines.append(f"- `{sheet}`")

    lines.extend(["", "## 输入数据 sheet", ""])
    for sheet in report["input_data_sheets"]:
        lines.append(f"- `{sheet}`")

    lines.extend(["", "## 纯输入 sheet（工作簿内无公式）", ""])
    for sheet in report["pure_input_sheets"]:
        lines.append(f"- `{sheet}`")

    if report["unregistered_sheets"]:
        lines.extend(["", "## 未在 sheet_registry 登记的 sheet", ""])
        for sheet in report["unregistered_sheets"]:
            lines.append(f"- `{sheet}`")

    if report["static_refs_by_sheet"]:
        lines.extend(["", "## 静态引用按 sheet 汇总（每 sheet 最多列 50 个）", ""])
        for sheet, refs in report["static_refs_by_sheet"].items():
            total = len(report.get("static_refs_by_sheet_truncated", {}))
            truncated = report["static_refs_by_sheet_truncated"].get(sheet, False)
            suffix = " …" if truncated else ""
            lines.append(f"### `{sheet}` ({len(refs)} shown{suffix})")
            for ref in refs[:10]:
                lines.append(f"- `{ref}`")
            if len(refs) > 10:
                lines.append(f"- … 另有 {len(refs) - 10} 个")

    if report["out_of_closure_workbook_sheets"]:
        lines.extend(["", "## 工作簿内未进入闭包的 sheet", ""])
        for sheet in report["out_of_closure_workbook_sheets"][:30]:
            lines.append(f"- `{sheet}`")
        if len(report["out_of_closure_workbook_sheets"]) > 30:
            lines.append(f"- … 另有 {len(report['out_of_closure_workbook_sheets']) - 30} 个")

    return "\n".join(lines) + "\n"


def default_output_dir(month: str) -> Path:
    safe_month = re.sub(r"[^\w\-]", "-", month)
    return PROJECT_ROOT / "docs" / "iterations" / f"iteration-{safe_month}" / "artifacts"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build dependency closure report from topology JSON."
    )
    parser.add_argument(
        "--topology",
        type=Path,
        default=DEFAULT_TOPOLOGY,
        help="Path to *.topology.json",
    )
    parser.add_argument(
        "--anchor",
        default="提成汇总",
        help="Anchor output sheet name (default: 提成汇总)",
    )
    parser.add_argument(
        "--anchors",
        nargs="+",
        default=None,
        help="Generate reports for multiple anchor sheets in one run",
    )
    parser.add_argument(
        "--list-sheets",
        action="store_true",
        help="List workbook sheets and formula-cell counts, then exit",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: docs/iterations/iteration-<month>/artifacts)",
    )
    parser.add_argument(
        "--month",
        default="2026-05",
        help="Month label for default output path",
    )
    parser.add_argument(
        "--format",
        choices=("json", "md", "both"),
        default="both",
        help="Output format (default: both)",
    )
    args = parser.parse_args()

    topology_path = args.topology.resolve()
    if not topology_path.exists():
        print(f"Topology not found: {topology_path}", file=sys.stderr)
        return 1

    topology = json.loads(topology_path.read_text(encoding="utf-8"))

    if args.list_sheets:
        roles = load_sheet_roles()
        print(f"{'sheet':<40} {'formula_cells':>13}  role")
        for row in list_topology_sheets(topology):
            role = roles.get(row["sheet"], "-")
            print(f"{row['sheet']:<40} {row['formula_cells']:>13}  {role}")
        return 0

    anchors = args.anchors or [args.anchor]
    out_dir = args.output_dir.resolve() if args.output_dir else default_output_dir(args.month)
    out_dir.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    for anchor in anchors:
        try:
            report = build_closure(topology, anchor)
        except ValueError as exc:
            print(f"[error] anchor={anchor}: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        stem = f"closure_{anchor}"
        if args.format in ("json", "both"):
            json_path = out_dir / f"{stem}.json"
            json_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[ok] {json_path.relative_to(PROJECT_ROOT)}")
        if args.format in ("md", "both"):
            md_path = out_dir / f"{stem}.md"
            md_path.write_text(render_markdown(report), encoding="utf-8")
            print(f"[ok] {md_path.relative_to(PROJECT_ROOT)}")
        print(
            f"closure[{anchor}]: {report['counts']['closure_formula_sheets']} formula sheets, "
            f"{report['counts']['pure_input_sheets']} pure input sheets"
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
