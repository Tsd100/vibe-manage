from pathlib import Path

from project_manager.config import AppConfig, DataDirectoryError


def test_defaults_point_to_d_drive():
    config = AppConfig.from_environment({})
    assert config.repo_root == Path(r"D:\Github")
    assert config.data_dir == Path(r"D:\Program Files (x86)\ProjectManagerData")


def test_data_directory_is_created_and_writable(tmp_path):
    config = AppConfig(repo_root=tmp_path, data_dir=tmp_path / "data")
    config.ensure_data_dirs()
    assert (tmp_path / "data" / "inventory").is_dir()
    assert (tmp_path / "data" / "logs").is_dir()


def test_permission_error_is_explicit(monkeypatch, tmp_path):
    config = AppConfig(repo_root=tmp_path, data_dir=tmp_path / "data")

    def deny_mkdir(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "mkdir", deny_mkdir)
    try:
        config.ensure_data_dirs()
    except DataDirectoryError as exc:
        assert "data" in str(exc)
    else:
        raise AssertionError("expected DataDirectoryError")
