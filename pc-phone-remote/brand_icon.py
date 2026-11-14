"""Programmatic brand logo & multi-size icon generator for PC Phone Remote Pro."""
from __future__ import annotations

import shutil
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]


APP_DIR = Path(__file__).resolve().parent
DEFAULT_ASSETS_DIR = APP_DIR / "assets"
MASTER_LOGO_NAME = "pc-phone-remote-oled-frosted-flare-1024.png"
FALLBACK_DOWNLOADS_LOGO = Path.home() / "Downloads" / "Telegram Desktop" / MASTER_LOGO_NAME


def _resolve_master_logo(assets_dir: Path | None = None) -> Path | None:
    target_dir = Path(assets_dir or DEFAULT_ASSETS_DIR)
    bundled = target_dir / MASTER_LOGO_NAME
    if bundled.exists():
        return bundled
    default_bundled = DEFAULT_ASSETS_DIR / MASTER_LOGO_NAME
    if default_bundled.exists():
        return default_bundled
    if FALLBACK_DOWNLOADS_LOGO.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FALLBACK_DOWNLOADS_LOGO, bundled)
        return bundled
    return None


def create_brand_image(
    size: int = 256,
    status_color: str | None = None,
    assets_dir: Path | None = None,
) -> "Image.Image":
    """Load the master frosted-flare logo, crop & resize, with optional tray status dot."""
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow (PIL) is required to generate brand icons.")

    canvas = 512
    master_path = _resolve_master_logo(assets_dir)
    if master_path is not None:
        with Image.open(master_path) as src:
            rgba = src.convert("RGBA")
            if rgba.size == (1024, 1024):
                rgba = rgba.crop((52, 52, 972, 972))
            img = rgba.resize((canvas, canvas), Image.Resampling.LANCZOS)
    else:
        img = Image.new("RGBA", (canvas, canvas), (13, 14, 24, 255))

    if status_color:
        draw = ImageDraw.Draw(img)
        dot_map = {
            "online": (61, 214, 140, 255),
            "green": (61, 214, 140, 255),
            "offline": (255, 92, 124, 255),
            "red": (255, 92, 124, 255),
            "warn": (245, 177, 76, 255),
        }
        fill_rgba = dot_map.get(status_color.lower(), status_color)
        draw.ellipse((356, 36, 476, 156), fill=(13, 14, 24, 255))
        draw.ellipse((368, 48, 464, 144), fill=fill_rgba)

    if size != canvas:
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    return img


def ensure_brand_assets(assets_dir: Path | None = None) -> dict[str, Path]:
    """Generate .ico and multi-resolution .png brand icons in `pc-phone-remote/assets`."""
    target = Path(assets_dir or DEFAULT_ASSETS_DIR)
    target.mkdir(parents=True, exist_ok=True)
    paths = {
        "master": target / MASTER_LOGO_NAME,
        "ico": target / "app_icon.ico",
        "png_192": target / "app_icon_192.png",
        "png_512": target / "app_icon_512.png",
        "apple_touch": target / "apple_touch_icon.png",
    }
    if Image is None:
        return paths

    master = create_brand_image(512, assets_dir=target)
    master.save(paths["png_512"], format="PNG")
    master.resize((192, 192), Image.Resampling.LANCZOS).save(paths["png_192"], format="PNG")
    master.resize((180, 180), Image.Resampling.LANCZOS).save(paths["apple_touch"], format="PNG")
    master.save(
        paths["ico"],
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return paths


if __name__ == "__main__":
    generated = ensure_brand_assets()
    for name, path in generated.items():
        print(f"{name}: {path}")
