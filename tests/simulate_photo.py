"""Test helper: fill the template with a font, then fake a phone photo of it
(perspective, uneven light, noise, sideways) so `learn` can be tested without paper.

    python tests/simulate_photo.py out/
"""
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import handnotes as H  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
out.mkdir(exist_ok=True)
H.make_template(out / "template.png")
probe = ImageFont.truetype(str(ROOT / "fonts/GochiHand.ttf"), 150)
ratio = -probe.getbbox("x", anchor="ls")[1] / 150
font = ImageFont.truetype(str(ROOT / "fonts/GochiHand.ttf"), int(H.CELL_H * (H.BASE_Y - H.XH_Y) * 1.05 / ratio))
rng = random.Random(1)
for p in range(1, H.PAGES_NEEDED + 1):
    img = Image.open(out / f"template-{p}.png").convert("RGB")
    d = ImageDraw.Draw(img)
    for i, ch in enumerate(H.CHARSET[(p - 1) * H.COLS * H.ROWS:p * H.COLS * H.ROWS]):
        r, c = divmod(i, H.COLS)
        x0, y0 = H.GRID_X0 + c * H.CELL_W, H.GRID_Y0 + r * H.CELL_H
        d.text((x0 + H.CELL_W * 0.35 + rng.uniform(-15, 15), y0 + H.CELL_H * H.BASE_Y + rng.uniform(-6, 6)),
               ch, font=font, fill=(25, 40, 120), anchor="ls")
    W, Hh = img.size
    canvas = Image.new("RGB", (W + 600, Hh + 600), (90, 80, 70))
    canvas.paste(img, (300, 300))
    flat = [(300, 300), (300 + W, 300), (300 + W, 300 + Hh), (300, 300 + Hh)]
    tilted = [(260, 340), (W + 330, 280), (W + 250, Hh + 360), (330, Hh + 250)]
    photo = canvas.transform(canvas.size, Image.PERSPECTIVE, H._perspective_coeffs(tilted, flat), Image.BICUBIC)
    a = np.asarray(photo).astype(np.float32)
    xx = np.mgrid[0:a.shape[0], 0:a.shape[1]][1]
    a = a * (0.72 + 0.28 * xx / a.shape[1])[..., None] + np.random.default_rng(p).normal(0, 4, a.shape)
    photo = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    photo = photo.resize((1800, int(1800 * a.shape[0] / a.shape[1]))).rotate(-90 if p == 2 else 0, expand=True)
    photo.save(out / f"fake-photo-{p}.jpg", quality=85)
print("fake photos written to", out)
