from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CreationTime:
    value: str | None
    source: str


def derive_creation_time(
    git_first_commit: str | None,
    filesystem_earliest: str | None,
    manual_created_at: str | None,
) -> CreationTime:
    if manual_created_at:
        return CreationTime(manual_created_at, "manual")
    if git_first_commit:
        return CreationTime(git_first_commit, "git_first_commit")
    if filesystem_earliest:
        return CreationTime(filesystem_earliest, "filesystem_estimate")
    return CreationTime(None, "unknown")


@dataclass(frozen=True)
class TimelineEvent:
    at: str | None
    event_type: str
    summary: str
    source: str


@dataclass(frozen=True)
class ProjectRecord:
    id: str
    path: str
    name: str
    purpose: str
    scope: str = "项目仓库"
    manual_status: str = "未确认"
    manual_phase: str = "未确认"
    manual_priority: str = "未确认"
    next_action: str = ""
    created_at: str | None = None
    created_at_source: str = "unknown"
    last_commit_at: str | None = None
    working_tree_modified_at: str | None = None
    last_modified_at: str | None = None
    github_open_source: str = "未确认"
    github_open_source_source: str = "auto_git_remote"
    github_remote_url: str = ""
    github_auto_open_source: str = "未确认"
    github_auto_open_source_source: str = "auto_git_remote"
    manual_github_open_source: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ProjectRecord":
        return cls(
            id=str(data.get("id", "")),
            path=str(data.get("path", "")),
            name=str(data.get("name", "")),
            purpose=str(data.get("purpose", "")),
            scope=str(data.get("scope", "项目仓库")),
            manual_status=str(data.get("manual_status", "未确认")),
            manual_phase=str(data.get("manual_phase", "未确认")),
            manual_priority=str(data.get("manual_priority", "未确认")),
            next_action=str(data.get("next_action", "")),
            created_at=data.get("created_at"),
            created_at_source=str(data.get("created_at_source", "unknown")),
            last_commit_at=data.get("last_commit_at"),
            working_tree_modified_at=data.get("working_tree_modified_at"),
            last_modified_at=data.get("last_modified_at"),
            github_open_source=str(data.get("github_open_source", "未确认")),
            github_open_source_source=str(data.get("github_open_source_source", "auto_git_remote")),
            github_remote_url=str(data.get("github_remote_url", "")),
            github_auto_open_source=str(data.get("github_auto_open_source", data.get("github_open_source", "未确认"))),
            github_auto_open_source_source=str(data.get("github_auto_open_source_source", "auto_git_remote")),
            manual_github_open_source=str(data.get("manual_github_open_source", "")),
        )
