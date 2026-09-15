from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DEFAULT_REPO_ROOT = Path(r"D:\Github")
DEFAULT_DATA_DIR = Path(r"D:\Program Files (x86)\ProjectManagerData")


class DataDirectoryError(RuntimeError):
    """Raised when the configured runtime data directory cannot be prepared."""


@dataclass(frozen=True)
class AppConfig:
    repo_root: Path = DEFAULT_REPO_ROOT
    data_dir: Path = DEFAULT_DATA_DIR

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "AppConfig":
        env = os.environ if environ is None else environ
        return cls(
            repo_root=Path(env.get("PROJECT_MANAGER_REPO_ROOT", str(DEFAULT_REPO_ROOT))),
            data_dir=Path(env.get("PROJECT_MANAGER_DATA_DIR", str(DEFAULT_DATA_DIR))),
        )

    def ensure_data_dirs(self) -> None:
        try:
            for name in ("inventory", "overrides", "timeline", "logs"):
                (self.data_dir / name).mkdir(parents=True, exist_ok=True)
            probe = self.data_dir / "logs" / ".write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise DataDirectoryError(f"无法写入数据目录：{self.data_dir}: {exc}") from exc
