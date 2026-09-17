from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterable
from urllib.parse import urlparse

from .models import derive_creation_time


SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "target", "venv", ".venv",
    "__pycache__", "vendor", "output", "outputs",
}


def should_skip_directory(name: str) -> bool:
    return name.lower() in SKIP_DIRS


def discover_repositories(root: Path, max_depth: int = 5) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    found: list[Path] = []
    root_depth = len(root.parts)
    for current, dirs, _files in os.walk(root, topdown=True):
        current_path = Path(current)
        depth = len(current_path.parts) - root_depth
        dirs[:] = [d for d in dirs if not should_skip_directory(d)]
        if depth > max_depth:
            dirs[:] = []
            continue
        git_marker = current_path / ".git"
        if git_marker.is_dir() or git_marker.is_file():
            found.append(current_path)
            dirs[:] = []
    return sorted(found)


def discover_repositories_many(roots: Iterable[Path], max_depth: int = 5) -> list[tuple[Path, Path]]:
    """Discover repositories across roots, keeping the first owner of duplicates."""
    found: list[tuple[Path, Path]] = []
    seen: set[str] = set()
    for raw_root in roots:
        root = Path(raw_root)
        for repo in discover_repositories(root, max_depth=max_depth):
            key = os.path.normcase(os.path.abspath(str(repo)))
            if key in seen:
                continue
            seen.add(key)
            found.append((root, repo))
    return sorted(found, key=lambda pair: os.path.normcase(os.path.abspath(str(pair[1]))))


def _git(repo: Path, *args: str, timeout: float = 8.0) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def _git_result(repo: Path, *args: str, timeout: float = 8.0) -> tuple[bool, str]:
    """Run Git while preserving whether the command itself succeeded."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    return result.returncode == 0, result.stdout.strip()


def parse_github_remote(value: str) -> str | None:
    """Return a remote URL when it points at github.com, otherwise None."""
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("git@") and ":" in text:
        host = text[4:].split(":", 1)[0].lower()
    else:
        host = (urlparse(text).hostname or "").lower()
    return text if host in {"github.com", "www.github.com"} else None


def git_remote_metadata(repo: Path) -> dict[str, str]:
    """Classify a repository by its configured Git remotes."""
    succeeded, output = _git_result(repo, "remote", "-v")
    if not succeeded:
        return {
            "github_open_source": "未确认",
            "github_open_source_source": "auto_git_remote",
            "github_remote_url": "",
        }
    seen: set[str] = set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        remote = parse_github_remote(parts[1])
        if remote and remote not in seen:
            seen.add(remote)
            return {
                "github_open_source": "是",
                "github_open_source_source": "auto_git_remote",
                "github_remote_url": remote,
            }
    return {
        "github_open_source": "否",
        "github_open_source_source": "auto_git_remote",
        "github_remote_url": "",
    }


def git_metadata(repo: Path) -> dict[str, str | int | None]:
    status = _git(repo, "status", "--short")
    branch = _git(repo, "branch", "--show-current") or "DETACHED"
    last_commit = _git(repo, "log", "-1", "--format=%cI") or None
    first_commit = _git(repo, "log", "--reverse", "--format=%cI", "-1") or None
    subject = _git(repo, "log", "-1", "--format=%s")
    return {
        "branch": branch,
        "status": status,
        "dirty_files": len(status.splitlines()) if status else 0,
        "last_commit_at": last_commit,
        "first_commit_at": first_commit,
        "last_subject": subject,
        **git_remote_metadata(repo),
    }


def _iso_from_mtime(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def earliest_source_file_time(repo: Path) -> str | None:
    earliest: float | None = None
    for current, dirs, files in os.walk(repo, topdown=True):
        dirs[:] = [d for d in dirs if not should_skip_directory(d)]
        for name in files:
            path = Path(current) / name
            try:
                value = path.stat().st_mtime
            except OSError:
                continue
            earliest = value if earliest is None else min(earliest, value)
    return _iso_from_mtime(earliest) if earliest is not None else None


def latest_source_file_time(repo: Path) -> str | None:
    latest: float | None = None
    for current, dirs, files in os.walk(repo, topdown=True):
        dirs[:] = [d for d in dirs if not should_skip_directory(d)]
        for name in files:
            path = Path(current) / name
            try:
                value = path.stat().st_mtime
            except OSError:
                continue
            latest = value if latest is None else max(latest, value)
    return _iso_from_mtime(latest) if latest is not None else None


def _purpose(repo: Path) -> str:
    for filename in ("README.md", "README.en.md", "README.txt"):
        path = repo / filename
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            if not line.startswith("#") and len(line) >= 8:
                return line[:240]
        if lines:
            return lines[0][:240]
    return "用途待补充"


def scan_projects(root: Path | Iterable[Path], max_depth: int = 5) -> list[dict[str, object]]:
    roots = [Path(root)] if isinstance(root, (str, Path)) else [Path(item) for item in root]
    repositories = discover_repositories_many(roots, max_depth=max_depth)
    multiple_roots = len(roots) > 1
    projects: list[dict[str, object]] = []
    for owner_root, repo in repositories:
        relative = repo.relative_to(owner_root).as_posix()
        metadata = git_metadata(repo)
        filesystem_created = earliest_source_file_time(repo)
        creation = derive_creation_time(metadata.get("first_commit_at"), filesystem_created, None)
        last_commit = metadata.get("last_commit_at")
        working_modified = latest_source_file_time(repo)
        timestamps = [value for value in (last_commit, working_modified) if isinstance(value, str)]
        record = {
            "id": (
                f"repo:{relative}"
                if not multiple_roots or owner_root == roots[0]
                else f"repo:{owner_root.resolve()}::{relative}"
            ),
            "scope": "参考仓库" if relative.startswith("_references/") else "项目仓库",
            "path": relative,
            "root": str(owner_root),
            "name": repo.name,
            "purpose": _purpose(repo),
            "manual_status": "未确认",
            "manual_phase": "未确认",
            "manual_priority": "未确认",
            "next_action": "确认用途、阶段与下一步动作",
            "created_at": creation.value,
            "created_at_source": creation.source,
            "last_commit_at": last_commit,
            "working_tree_modified_at": working_modified,
            "last_modified_at": max(timestamps) if timestamps else None,
            "branch": metadata.get("branch"),
            "dirty_files": metadata.get("dirty_files", 0),
            "last_subject": metadata.get("last_subject", ""),
            "github_open_source": metadata.get("github_open_source", "未确认"),
            "github_open_source_source": metadata.get("github_open_source_source", "auto_git_remote"),
            "github_remote_url": metadata.get("github_remote_url", ""),
            "github_open_source_history": [],
        }
        projects.append(record)
    return projects
