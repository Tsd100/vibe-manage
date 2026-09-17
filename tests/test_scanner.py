from project_manager.scanner import discover_repositories, scan_projects, should_skip_directory


def test_discover_repositories_skips_nested_noise(tmp_path):
    (tmp_path / "good" / ".git").mkdir(parents=True)
    (tmp_path / "good" / "node_modules" / ".git").mkdir(parents=True)
    (tmp_path / "plain").mkdir()
    assert discover_repositories(tmp_path) == [tmp_path / "good"]


def test_skip_directory_names_are_case_insensitive():
    assert should_skip_directory("NODE_MODULES") is True
    assert should_skip_directory("src") is False


def test_scan_projects_keeps_repository_without_git_commits(tmp_path):
    repo = tmp_path / "no-commit"
    (repo / ".git").mkdir(parents=True)
    (repo / "README.md").write_text("# A small project\n\nPurpose text.", encoding="utf-8")
    projects = scan_projects(tmp_path)
    assert len(projects) == 1
    assert projects[0]["name"] == "no-commit"
    assert projects[0]["created_at_source"] in {"filesystem_estimate", "unknown"}


def test_scan_projects_honors_max_depth(tmp_path):
    (tmp_path / "level-one" / "level-two" / ".git").mkdir(parents=True)

    assert scan_projects(tmp_path, max_depth=1) == []


def test_scan_projects_merges_multiple_roots_without_duplicate_repositories(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    (first / "shared" / ".git").mkdir(parents=True)
    (second / "other" / ".git").mkdir(parents=True)

    projects = scan_projects([first, second, first])

    assert {project["path"] for project in projects} == {"shared", "other"}
    by_path = {project["path"]: project for project in projects}
    assert by_path["shared"]["id"] == "repo:shared"
    assert str(second.resolve()) in str(by_path["other"]["id"])


def test_parse_github_remote_supports_https_ssh_and_scp_like():
    from project_manager.scanner import parse_github_remote

    assert parse_github_remote("https://github.com/acme/demo.git") == "https://github.com/acme/demo.git"
    assert parse_github_remote("ssh://git@github.com/acme/demo.git") == "ssh://git@github.com/acme/demo.git"
    assert parse_github_remote("git@github.com:acme/demo.git") == "git@github.com:acme/demo.git"
    assert parse_github_remote("https://gitlab.com/acme/demo.git") is None


def test_git_remote_metadata_marks_github_and_non_github_remotes(monkeypatch, tmp_path):
    from project_manager import scanner

    monkeypatch.setattr(
        scanner,
        "_git_result",
        lambda _repo, *args, **_kwargs: (
            True,
            "origin\thttps://github.com/acme/demo.git (fetch)\n"
            "origin\thttps://github.com/acme/demo.git (push)"
            if args[:2] == ("remote", "-v") else "",
        ),
    )
    assert scanner.git_remote_metadata(tmp_path) == {
        "github_open_source": "是",
        "github_open_source_source": "auto_git_remote",
        "github_remote_url": "https://github.com/acme/demo.git",
    }

    monkeypatch.setattr(
        scanner,
        "_git_result",
        lambda _repo, *args, **_kwargs: (True, "origin\thttps://gitlab.com/acme/demo.git (fetch)"),
    )
    assert scanner.git_remote_metadata(tmp_path)["github_open_source"] == "否"


def test_git_remote_metadata_marks_command_failure_as_unconfirmed(monkeypatch, tmp_path):
    from project_manager import scanner

    monkeypatch.setattr(scanner, "_git_result", lambda *_args, **_kwargs: (False, ""))
    metadata = scanner.git_remote_metadata(tmp_path)

    assert metadata == {
        "github_open_source": "未确认",
        "github_open_source_source": "auto_git_remote",
        "github_remote_url": "",
    }


def test_scan_projects_includes_auto_github_fields(tmp_path, monkeypatch):
    repo = tmp_path / "demo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(
        "project_manager.scanner.git_remote_metadata",
        lambda _repo: {
            "github_open_source": "是",
            "github_open_source_source": "auto_git_remote",
            "github_remote_url": "https://github.com/acme/demo.git",
        },
    )

    project = scan_projects(tmp_path)[0]

    assert project["github_open_source"] == "是"
    assert project["github_open_source_source"] == "auto_git_remote"
    assert project["github_remote_url"] == "https://github.com/acme/demo.git"
