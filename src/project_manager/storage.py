from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


class JsonStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self, default: Any = None) -> Any:
        if not self.path.exists():
            return default
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, value: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)


def merge_manual_overrides(auto_record: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(auto_record)
    project_id = str(auto_record.get("id", ""))
    manual = overrides.get(project_id, {})
    if isinstance(manual, Mapping):
        merged.update(manual)
    return merged
