"""Генерира icon.png (128/48/16) за extension/icons/ — funnel върху YouTube-червен фон."""
from PIL import Image, ImageDraw

SIZE = 512  # supersample, после се смалява за anti-aliasing
RED = (230, 33, 23, 255)  # YouTube red
WHITE = (255, 255, 255, 255)

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Заоблен червен квадрат фон
margin = 8
draw.rounded_rectangle(
    [margin, margin, SIZE - margin, SIZE - margin],
    radius=110,
    fill=RED,
)

# Фуния (funnel): трапец (широк отгоре, тесен отдолу) + столче + капка
cx = SIZE / 2
top_y = 150
top_half_w = 150
mid_y = 300
mid_half_w = 40
draw.polygon(
    [
        (cx - top_half_w, top_y),
        (cx + top_half_w, top_y),
        (cx + mid_half_w, mid_y),
        (cx - mid_half_w, mid_y),
    ],
    fill=WHITE,
)
# столче на фунията
stem_w = 34
stem_bottom = 372
draw.rectangle(
    [cx - stem_w / 2, mid_y - 4, cx + stem_w / 2, stem_bottom],
    fill=WHITE,
)
# капка под фунията (филтриран/готов резултат)
drop_r = 26
drop_cy = stem_bottom + drop_r - 6
draw.ellipse(
    [cx - drop_r, drop_cy - drop_r, cx + drop_r, drop_cy + drop_r],
    fill=WHITE,
)

for size in (128, 48, 32, 16):
    resized = img.resize((size, size), Image.LANCZOS)
    resized.save(f"extension/icons/icon{size}.png")

print("Done")
