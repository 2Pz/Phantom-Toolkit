from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def _render_base(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (20, 24, 35, 255))
    d = ImageDraw.Draw(img)

    # Simple diagonal gradient-ish blocks (placeholder, but recognizable)
    d.rectangle([0, 0, size, size], fill=(18, 20, 28, 255))
    d.polygon([(0, 0), (size, 0), (0, size)], fill=(40, 90, 180, 255))
    d.polygon([(size, size), (size, 0), (0, size)], fill=(90, 40, 180, 255))

    # Center badge
    pad = size // 10
    d.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=size // 8,
        outline=(255, 255, 255, 220),
        width=max(2, size // 64),
    )

    # Text
    font = ImageFont.load_default()
    text = "PT"
    tw, th = d.textbbox((0, 0), text, font=font)[2:]
    # Scale-ish: draw text multiple times offset to appear bolder
    x = (size - tw) // 2
    y = (size - th) // 2
    for ox, oy in [(0, 0), (1, 0), (0, 1), (1, 1)]:
        d.text((x + ox, y + oy), text, font=font, fill=(255, 255, 255, 240))

    return img


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Define paths
    root_dir = Path(__file__).resolve().parent.parent
    assets_dir = root_dir / "assets"
    build_assets_dir = root_dir / "build" / "assets"

    assets_dir.mkdir(parents=True, exist_ok=True)
    build_assets_dir.mkdir(parents=True, exist_ok=True)

    src_icon_path = assets_dir / "icon.png"
    src_ico_path = assets_dir / "icon.ico"
    out_png_path = build_assets_dir / "phantom-toolkit.png"
    out_ico_path = build_assets_dir / "phantom-toolkit.ico"

    # Load or Generate Source
    if src_icon_path.exists():
        logger.info("Using source PNG icon: %s", src_icon_path)
        img = Image.open(src_icon_path).convert("RGBA")
    elif src_ico_path.exists():
        logger.info("Source PNG not found. Using ICO icon: %s", src_ico_path)
        # Opening an ICO with Pillow returns the first image/best quality match
        img = Image.open(src_ico_path).convert("RGBA")
    else:
        logger.info("Source icons not found. Generating placeholder...")
        img = _render_base(512)
        img.save(src_icon_path)
        logger.info("Saved placeholder source icon to: %s", src_icon_path)

    # Save outputs
    # 1. PNG for Linux
    img_resized = img.resize((256, 256), Image.Resampling.LANCZOS)
    img_resized.save(out_png_path, format="PNG")

    # 2. ICO for Windows
    img.save(
        out_ico_path,
        format="ICO",
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )

    logger.info("Wrote %s", out_png_path)
    logger.info("Wrote %s", out_ico_path)


if __name__ == "__main__":
    main()
