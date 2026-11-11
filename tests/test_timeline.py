from project_manager.models import TimelineEvent
from project_manager.timeline import build_timeline, project_events


def test_timeline_orders_events_newest_first():
    events = build_timeline([
        TimelineEvent("2026-01-01T00:00:00+00:00", "commit", "old", "git"),
        TimelineEvent("2026-02-01T00:00:00+00:00", "validation", "new", "test"),
    ])
    assert [event.summary for event in events] == ["new", "old"]


def test_timeline_keeps_unknown_date_after_dated_events():
    events = build_timeline([
        TimelineEvent(None, "manual", "unknown", "manual"),
        TimelineEvent("2026-02-01T00:00:00+00:00", "commit", "dated", "git"),
    ])
    assert [event.summary for event in events] == ["dated", "unknown"]


def test_project_events_include_commit_and_worktree_evidence():
    events = project_events({
        "last_commit_at": "2026-02-01T00:00:00+00:00",
        "last_subject": "add feature",
        "working_tree_modified_at": "2026-03-01T00:00:00+00:00",
        "validation": {"observed_at": "2026-04-01T00:00:00+00:00", "summary": "3 passed"},
    })
    assert [event.event_type for event in events] == ["validation", "working_tree", "commit"]


def test_project_events_show_recent_commits_without_repeating_tip():
    events = project_events({
        "last_commit_at": "2026-02-03T04:05:06+08:00",
        "last_subject": "version 2",
        "recent_commits": [
            {"sha": "b" * 40, "at": "2026-02-03T04:05:06+08:00", "subject": "version 2"},
            {"sha": "a" * 40, "at": "2025-01-02T03:04:05+08:00", "subject": "version 1"},
        ],
    })

    assert [(event.at, event.summary) for event in events if event.event_type == "commit"] == [
        ("2026-02-03T04:05:06+08:00", "version 2"),
        ("2025-01-02T03:04:05+08:00", "version 1"),
    ]


def test_project_events_include_creation_and_last_modified_evidence():
    events = project_events({
        "created_at": "2025-01-01T00:00:00+00:00",
        "created_at_source": "filesystem_estimate",
        "last_modified_at": "2026-05-01T00:00:00+00:00",
    })
    assert [(event.event_type, event.at, event.source) for event in events] == [
        ("last_modified", "2026-05-01T00:00:00+00:00", "filesystem"),
        ("created", "2025-01-01T00:00:00+00:00", "filesystem_estimate"),
    ]


def test_project_events_include_github_status_and_manual_history():
    events = project_events({
        "github_open_source": "是",
        "github_open_source_source": "auto_git_remote",
        "github_remote_url": "https://github.com/acme/demo",
        "github_open_source_history": [{
            "at": "2026-09-06T12:00:00+08:00",
            "value": "否",
            "source": "manual",
        }],
    })
    assert any(event.event_type == "github_open_source" and event.source == "auto_git_remote" for event in events)
    assert any(event.event_type == "github_open_source" and event.source == "manual" for event in events)
