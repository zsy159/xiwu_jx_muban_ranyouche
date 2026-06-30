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

# 默认关闭保存即重跑，避免长试算被页面重载打断；仅监视 app 目录热重载 UI
_DEFAULT_FLAGS = (
    "--server.runOnSave",
    "false",
    "--server.fileWatcherType",
    "auto",
    "--server.folderWatchList",
    str(SALARY_PIPELINE / "app"),
)

if __name__ == "__main__":
    sys.argv = ["streamlit", "run", str(APP), *_DEFAULT_FLAGS, *sys.argv[1:]]
    raise SystemExit(stcli.main())
