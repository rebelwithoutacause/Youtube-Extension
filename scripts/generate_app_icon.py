"""Генерира assets/app.ico (+ assets/app.png) — същият funnel дизайн като
extension/icons/, за визуална консистентност между разширението и десктоп
приложението. Стартирайте от repo root: python scripts/generate_app_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024  # supersample, после се смалява за anti-aliasing
RED = (230, 33, 23, 255)  # YouTube red
WHITE = (255, 255, 255, 255)

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"


def render() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = 16
    draw.rounded_rectangle(
        [margin, margin, SIZE - margin, SIZE - margin],
        radius=220,
        fill=RED,
    )

    cx = SIZE / 2
    top_y = 300
    top_half_w = 300
    mid_y = 600
    mid_half_w = 80
    draw.polygon(
        [
            (cx - top_half_w, top_y),
            (cx + top_half_w, top_y),
            (cx + mid_half_w, mid_y),
            (cx - mid_half_w, mid_y),
        ],
        fill=WHITE,
    )
    stem_w = 68
    stem_bottom = 744
    draw.rectangle(
        [cx - stem_w / 2, mid_y - 8, cx + stem_w / 2, stem_bottom],
        fill=WHITE,
    )
    drop_r = 52
    drop_cy = stem_bottom + drop_r - 12
    draw.ellipse(
        [cx - drop_r, drop_cy - drop_r, cx + drop_r, drop_cy + drop_r],
        fill=WHITE,
    )
    return img


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    img = render()

    png_path = ASSETS_DIR / "app.png"
    img.resize((256, 256), Image.LANCZOS).save(png_path)

    ico_path = ASSETS_DIR / "app.ico"
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=ico_sizes)

    print(f"Written {png_path} and {ico_path}")


if __name__ == "__main__":
    main()
