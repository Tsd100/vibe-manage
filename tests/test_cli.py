import json

from project_manager.config import AppConfig
from project_manager.main import WINDOWS_APP_USER_MODEL_ID, self_check, set_windows_app_user_model_id


def test_self_check_reports_explicit_data_root(tmp_path, capsys):
    code = self_check(AppConfig(repo_root=tmp_path, data_dir=tmp_path / "data"))
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["data_dir"].endswith("data")
    assert payload["repository_count"] == 0


def test_self_check_reports_saved_multiple_repo_roots(tmp_path, capsys):
    first = tmp_path / "first"
    second = tmp_path / "second"
    (first / "alpha" / ".git").mkdir(parents=True)
    (second / "beta" / ".git").mkdir(parents=True)
    data_dir = tmp_path / "data"
    (data_dir / "settings.json").parent.mkdir(parents=True)
    (data_dir / "settings.json").write_text(
        json.dumps({"repo_roots": [str(first), str(second)]}),
        encoding="utf-8",
    )

    code = self_check(AppConfig(repo_root=first, data_dir=data_dir))
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["repository_count"] == 2
    assert payload["repo_roots"] == [str(first), str(second)]


def test_windows_taskbar_identity_is_stable_and_non_windows_safe(monkeypatch):
    import project_manager.main as main_module

    assert WINDOWS_APP_USER_MODEL_ID == "VibeManage.ProjectManager"
    monkeypatch.setattr(main_module.os, "name", "posix")
    assert set_windows_app_user_model_id() is False
