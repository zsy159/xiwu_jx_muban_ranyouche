"""Project directory layout — single source of truth for all paths."""

from __future__ import annotations

from pathlib import Path

# salary_pipeline/paths.py → project root is parent of package
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DOCS_DIR = PROJECT_ROOT / "docs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
TOPOLOGY_DIR = DATA_DIR / "topology"
OUTPUT_DIR = PROJECT_ROOT / "output"

CONFIG_DIR = Path(__file__).resolve().parent / "config"


def raw_month_dir(month: str) -> Path:
    return RAW_DATA_DIR / month


def topology_month_dir(month: str) -> Path:
    return TOPOLOGY_DIR / month


def output_month_dir(month: str) -> Path:
    return OUTPUT_DIR / month


def resolve_project_path(relative: str | Path) -> Path:
    path = Path(relative)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path
