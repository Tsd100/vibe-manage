from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


MAX_SCAN_HISTORY = 50


def normalize_scan_history(value: Any) -> list[dict[str, Any]]:
    raw = value.get("runs", []) if isinstance(value, Mapping) else value
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        if not str(item.get("finished_at") or item.get("started_at") or "").strip():
            continue
        result.append(dict(item))
    return result[:MAX_SCAN_HISTORY]


def build_scan_record(
    *,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    project_count: int,
    root_count: int,
    error: str | None = None,
) -> dict[str, Any]:
    duration = max(0.0, (finished_at - started_at).total_seconds())
    return {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(duration, 2),
        "status": str(status),
        "project_count": int(project_count),
        "root_count": int(root_count),
        "error": str(error or ""),
    }


def append_scan_record(store: Any, record: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = normalize_scan_history(store.load(default={}) or {})
    records.insert(0, dict(record))
    records = records[:MAX_SCAN_HISTORY]
    store.save({"runs": records})
    return records
