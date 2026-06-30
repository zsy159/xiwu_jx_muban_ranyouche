#!/usr/bin/env python3
"""Launch observability console with project root on PYTHONPATH."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SALARY_PIPELINE = ROOT / "salary_pipeline"

os.chdir(ROOT)


def _prepend_pythonpath(entry: str) -> None:
    """Streamlit only treats PYTHONPATH (not sys.path) as extra watch roots."""
    existing = os.environ.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if entry not in parts:
        os.environ["PYTHONPATH"] = (
            os.pathsep.join([entry, *parts]) if parts else entry
        )


_prepend_pythonpath(str(ROOT))

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.web import cli as stcli

APP = SALARY_PIPELINE / "app" / "streamlit_app.py"

# 默认开启保存即重跑；显式监视整个 salary_pipeline（pipelines/ 等不在 app/ 下的模块）
_DEFAULT_FLAGS = (
    "--server.runOnSave",
    "true",
    "--server.fileWatcherType",
    "auto",
    "--server.folderWatchList",
    str(SALARY_PIPELINE),
)

if __name__ == "__main__":
    sys.argv = ["streamlit", "run", str(APP), *_DEFAULT_FLAGS, *sys.argv[1:]]
    raise SystemExit(stcli.main())
