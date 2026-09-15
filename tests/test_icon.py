from pathlib import Path

from PIL import Image

from project_manager.icon import app_icon_path, create_app_icon, save_app_icon


def test_create_app_icon_returns_blue_workbench_rgba():
    image = create_app_icon(64)

    assert image.mode == "RGBA"
    assert image.size == (64, 64)
    background = image.getpixel((32, 4))
    assert background[2] > background[0]
    assert image.getpixel((16, 20))[0] > 200


def test_save_app_icon_writes_multisize_windows_ico(tmp_path: Path):
    target = tmp_path / "project-manager-icon.ico"

    save_app_icon(target)

    with Image.open(target) as image:
        assert image.format == "ICO"
        assert image.size == (256, 256)
        assert image.info["sizes"] >= {(16, 16), (32, 32), (64, 64), (128, 128), (256, 256)}


def test_app_icon_path_points_to_the_project_windows_asset():
    asset = app_icon_path()

    assert asset.name == "project-manager-icon.ico"
    assert asset.suffix == ".ico"
    assert asset.exists()
