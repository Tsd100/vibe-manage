"""Shared application icon for the window and Windows notification area."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ICON_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)
_CANVAS_SIZE = 256
ICON_FILENAME = "project-manager-icon.ico"


def app_icon_path() -> Path:
    """Return the checked-in Windows icon asset used by the desktop window."""

    return Path(__file__).resolve().parents[2] / "assets" / ICON_FILENAME


def create_app_icon(size: int = 64) -> Image.Image:
    """Create the blue workbench icon at ``size`` pixels.

    The graphic is rendered on a large transparent canvas before being resized so
    that the rounded corners and small status dots remain legible at tray sizes.
    """

    if not isinstance(size, int) or size < 16:
        raise ValueError("icon size must be an integer of at least 16 pixels")

    image = Image.new("RGBA", (_CANVAS_SIZE, _CANVAS_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (4, 4, _CANVAS_SIZE - 4, _CANVAS_SIZE - 4),
        radius=52,
        fill=(37, 99, 235, 255),
    )
    draw.rounded_rectangle(
        (44, 48, 212, 184),
        radius=20,
        fill=(239, 246, 255, 255),
        outline=(219, 234, 254, 255),
        width=4,
    )

    line_fill = (29, 78, 216, 255)
    for y, right in ((92, 184), (124, 170), (156, 156)):
        draw.rounded_rectangle((72, y, right, y + 12), radius=6, fill=line_fill)

    dot_y = 218
    for x, fill in (
        (82, (251, 191, 36, 255)),
        (128, (34, 197, 94, 255)),
        (174, (239, 246, 255, 255)),
    ):
        draw.ellipse((x - 11, dot_y - 11, x + 11, dot_y + 11), fill=fill)

    if size == _CANVAS_SIZE:
        return image
    return image.resize((size, size), Image.Resampling.LANCZOS)


def save_app_icon(path: str | Path) -> Path:
    """Write the application icon as a multi-size Windows ``.ico`` file."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image = create_app_icon(max(ICON_SIZES))
    image.save(target, format="ICO", sizes=[(size, size) for size in ICON_SIZES])
    return target
