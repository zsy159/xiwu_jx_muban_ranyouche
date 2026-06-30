"""Cross-run cache for incremental hub → overlay pipeline stages."""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from salary_pipeline.paths import CONFIG_DIR, resolve_project_path

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "run_manifest.json"
HUB_SNAPSHOT_FILENAME = "hub_pre_overlay"
PERF_SNAPSHOT_FILENAME = "computed_perf_frame"
MANIFEST_VERSION = 1

_HUB_FINGERPRINT_KEYS = (
    "workbooks.sales",
    "topology.sales",
    "config.performance_sheet_columns",
    "config.hub_performance",
    "config.month.performance_sheet",
    "config.month.hub",
    "config.sales_advisor_roles",
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_fingerprint(path: Path) -> str:
    if not path.exists():
        return f"missing:{path}"
    stat = path.stat()
    return f"sha256:{_sha256_file(path)}:{stat.st_mtime_ns}:{stat.st_size}"


def _yaml_section_fingerprint(path: Path, *keys: str) -> str:
    if not path.exists():
        return f"missing:{path}"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    section: Any = data
    for key in keys:
        section = section.get(key) if isinstance(section, dict) else None
    payload = yaml.safe_dump(section, sort_keys=True, allow_unicode=True)
    return f"sha256:{_sha256_bytes(payload.encode('utf-8'))}"


def compute_input_fingerprint(month_config: dict[str, Any]) -> dict[str, str]:
    """Hash L0 inputs that invalidate hub-stage cache when changed."""
    config_dir = CONFIG_DIR
    fingerprints: dict[str, str] = {}

    sales_wb = resolve_project_path(month_config["workbooks"]["sales"])
    topology = resolve_project_path(month_config["topology"]["sales"])
    fingerprints["workbooks.sales"] = _file_fingerprint(sales_wb)
    fingerprints["topology.sales"] = _file_fingerprint(topology)

    fingerprints["config.performance_sheet_columns"] = _file_fingerprint(
        config_dir / "performance_sheet_columns.yaml"
    )
    fingerprints["config.hub_performance"] = _file_fingerprint(
        config_dir / "hub_performance.yaml"
    )
    month_path = config_dir / "month.yaml"
    fingerprints["config.month.performance_sheet"] = _yaml_section_fingerprint(
        month_path, "performance_sheet"
    )
    fingerprints["config.month.hub"] = _yaml_section_fingerprint(month_path, "hub")
    fingerprints["config.sales_advisor_roles"] = _file_fingerprint(
        config_dir / "sales_advisor_roles.yaml"
    )
    return fingerprints


def resolve_cache_dir(month_config: dict[str, Any]) -> Path:
    outputs = month_config.get("outputs", {})
    cache_rel = outputs.get("cache_dir")
    if cache_rel:
        return resolve_project_path(cache_rel)
    commission = resolve_project_path(outputs["commission_summary_file"])
    return commission.parent / "cache"


def write_manifest(
    cache_dir: Path,
    fingerprint: dict[str, str],
    *,
    stage: str = "hub",
    artifacts: dict[str, str] | None = None,
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": MANIFEST_VERSION,
        "stage": stage,
        "fingerprint": fingerprint,
        "artifacts": artifacts or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = cache_dir / MANIFEST_FILENAME
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Wrote run manifest -> %s", path)
    return path


def read_manifest(cache_dir: Path) -> dict[str, Any] | None:
    path = cache_dir / MANIFEST_FILENAME
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _parquet_available() -> bool:
    try:
        import pyarrow  # noqa: F401

        return True
    except ImportError:
        return False


def _snapshot_paths(cache_dir: Path, stem: str) -> tuple[Path, Path]:
    parquet_path = cache_dir / f"{stem}.parquet"
    pickle_path = cache_dir / f"{stem}.pkl"
    return parquet_path, pickle_path


def save_hub_snapshot(
    cache_dir: Path,
    summary: pd.DataFrame,
    computed_perf: pd.DataFrame | None,
) -> dict[str, str]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    use_parquet = _parquet_available()

    hub_path, hub_pkl = _snapshot_paths(cache_dir, HUB_SNAPSHOT_FILENAME)
    if use_parquet:
        summary.to_parquet(hub_path, index=False)
        artifacts["hub_pre_overlay"] = hub_path.name
    else:
        with hub_pkl.open("wb") as fh:
            pickle.dump(summary, fh, protocol=pickle.HIGHEST_PROTOCOL)
        artifacts["hub_pre_overlay"] = hub_pkl.name

    perf_path, perf_pkl = _snapshot_paths(cache_dir, PERF_SNAPSHOT_FILENAME)
    perf_frame = computed_perf if computed_perf is not None else pd.DataFrame()
    if use_parquet:
        perf_frame.to_parquet(perf_path, index=False)
        artifacts["computed_perf_frame"] = perf_path.name
    else:
        with perf_pkl.open("wb") as fh:
            pickle.dump(perf_frame, fh, protocol=pickle.HIGHEST_PROTOCOL)
        artifacts["computed_perf_frame"] = perf_pkl.name

    logger.info(
        "Saved hub snapshot (%s) -> %s",
        "parquet" if use_parquet else "pickle",
        cache_dir,
    )
    return artifacts


def _load_frame(cache_dir: Path, stem: str, artifact_name: str | None) -> pd.DataFrame:
    if artifact_name:
        candidate = cache_dir / artifact_name
        if candidate.suffix == ".parquet" and candidate.exists():
            return pd.read_parquet(candidate)
        if candidate.suffix == ".pkl" and candidate.exists():
            with candidate.open("rb") as fh:
                return pickle.load(fh)

    parquet_path, pickle_path = _snapshot_paths(cache_dir, stem)
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    if pickle_path.exists():
        with pickle_path.open("rb") as fh:
            return pickle.load(fh)
    raise FileNotFoundError(
        f"Snapshot artifact missing for {stem!r} under {cache_dir}"
    )


def load_hub_snapshot(
    cache_dir: Path,
    manifest: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    manifest = manifest or read_manifest(cache_dir)
    artifacts = (manifest or {}).get("artifacts", {})
    summary = _load_frame(cache_dir, HUB_SNAPSHOT_FILENAME, artifacts.get("hub_pre_overlay"))
    perf = _load_frame(
        cache_dir, PERF_SNAPSHOT_FILENAME, artifacts.get("computed_perf_frame")
    )
    return summary, perf


def cache_is_valid(
    manifest: dict[str, Any] | None,
    current_fingerprint: dict[str, str],
    *,
    scope: str = "hub",
    cache_dir: Path | None = None,
) -> tuple[bool, str]:
    if scope != "hub":
        return False, f"unsupported cache scope: {scope!r}"

    if manifest is None:
        return False, "no run manifest; run full compute first"

    if manifest.get("version") != MANIFEST_VERSION:
        return False, "manifest version mismatch; run full compute first"

    if manifest.get("stage") != "hub":
        return False, "manifest stage is not hub; run full compute first"

    stored = manifest.get("fingerprint") or {}
    for key in _HUB_FINGERPRINT_KEYS:
        if stored.get(key) != current_fingerprint.get(key):
            return False, f"input changed: {key}"

    if cache_dir is not None:
        try:
            load_hub_snapshot(cache_dir, manifest)
        except FileNotFoundError as exc:
            return False, str(exc)

    return True, "ok"


# Canonical overlay keys (order matches sales pipeline)
OVERLAY_KEYS: tuple[str, ...] = (
    "sales-advisor",
    "new-media",
    "invite",
    "customer",
    "direct-store",
    "recruit",
)

# Overlay role keys accepted by --only (canonical + aliases)
OVERLAY_KEY_ALIASES: dict[str, str] = {
    "sales-advisor": "sales-advisor",
    "sales_advisor": "sales-advisor",
    "salesadvisor": "sales-advisor",
    "new-media": "new-media",
    "new_media": "new-media",
    "newmedia": "new-media",
    "invite": "invite",
    "invite-specialist": "invite",
    "customer": "customer",
    "customer-specialist": "customer",
    "direct-store": "direct-store",
    "direct_store": "direct-store",
    "direct-store-manager": "direct-store",
    "recruit": "recruit",
}


def normalize_overlay_key(key: str) -> str:
    canonical = OVERLAY_KEY_ALIASES.get(key.strip().lower())
    if canonical is None:
        known = ", ".join(sorted({v for v in OVERLAY_KEY_ALIASES.values()}))
        raise ValueError(f"unknown overlay key {key!r}; expected one of: {known}")
    return canonical


def normalize_overlay_keys(keys: list[str] | None) -> list[str] | None:
    if keys is None:
        return None
    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        canonical = normalize_overlay_key(key)
        if canonical not in seen:
            seen.add(canonical)
            ordered.append(canonical)
    return ordered
