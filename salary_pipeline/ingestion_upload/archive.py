"""Archive uploaded originals with same-month overwrite support."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from salary_pipeline.paths import RAW_DATA_DIR

logger = logging.getLogger(__name__)


def archive_month_uploads(
    month_id: str,
    source_paths: list[Path],
    *,
    archive_root: Path | None = None,
) -> Path:
    """
    Copy originals to data/raw/_archive/YYYY-MM/<timestamp>/.

    Same-month re-upload creates a new timestamp folder; formal raw dir is
    overwritten separately in promote.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = archive_root or (RAW_DATA_DIR / "_archive" / month_id / ts)
    root.mkdir(parents=True, exist_ok=True)
    for src in source_paths:
        if not src.exists():
            continue
        dest = root / src.name
        shutil.copy2(src, dest)
    logger.info("Archived %d files -> %s", len(source_paths), root)
    return root
