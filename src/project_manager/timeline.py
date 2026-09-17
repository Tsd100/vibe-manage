from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Mapping

from .models import TimelineEvent


def build_timeline(events: Iterable[TimelineEvent]) -> list[TimelineEvent]:
    return sorted(
        events,
        key=lambda event: (event.at is not None, event.at or ""),
        reverse=True,
    )


def project_events(project: Mapping[str, Any]) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    github_status = str(project.get("github_open_source") or "").strip()
    if github_status:
        source = str(project.get("github_open_source_source") or "auto_git_remote")
        remote = str(project.get("github_remote_url") or "").strip()
        suffix = f" · {remote}" if remote else ""
        events.append(TimelineEvent(
            None,
            "github_open_source",
            f"GitHub 开源状态：{github_status}{suffix}",
            source,
        ))
    history = project.get("github_open_source_history")
    if isinstance(history, Iterable) and not isinstance(history, (str, bytes, Mapping)):
        for item in history:
            if not isinstance(item, Mapping):
                continue
            value = str(item.get("value") or "未确认")
            events.append(TimelineEvent(
                str(item.get("at")) if item.get("at") else None,
                "github_open_source",
                f"GitHub 开源状态：{value}",
                str(item.get("source") or "manual"),
            ))
    if project.get("created_at"):
        events.append(TimelineEvent(
            str(project["created_at"]), "created", "项目创建时间",
            str(project.get("created_at_source") or "unknown"),
        ))
    if project.get("last_commit_at"):
        events.append(TimelineEvent(
            str(project["last_commit_at"]), "commit",
            str(project.get("last_subject") or "最近一次提交"), "git",
        ))
    if project.get("last_modified_at"):
        events.append(TimelineEvent(
            str(project["last_modified_at"]), "last_modified", "项目最后修改",
            "filesystem",
        ))
    if project.get("working_tree_modified_at"):
        events.append(TimelineEvent(
            str(project["working_tree_modified_at"]), "working_tree",
            "工作树最近有文件修改", "filesystem",
        ))
    validation = project.get("validation")
    if isinstance(validation, Mapping) and validation.get("observed_at"):
        events.append(TimelineEvent(
            str(validation["observed_at"]), "validation",
            str(validation.get("summary") or "验证事件"), "test",
        ))
    return build_timeline(events)
