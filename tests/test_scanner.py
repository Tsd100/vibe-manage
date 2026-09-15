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
