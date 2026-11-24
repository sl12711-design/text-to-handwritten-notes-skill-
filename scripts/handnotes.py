#!/usr/bin/env python3
"""handnotes: turn text into handwritten-looking notes (PDF / PNG).

Only needs Pillow and numpy, which are already installed in the ChatGPT
and Claude code sandboxes.

    python handnotes.py render notes.md -o notes.pdf --paper grid --font caveat
    python handnotes.py template -o my-template.pdf          # sheet to fill by hand
    python handnotes.py learn page1.jpg page2.jpg -o my-hand  # learn your handwriting
    python handnotes.py render notes.md -o notes.pdf --hand my-hand

Notes markup (one idea per line):
    # Title            big, underlined by hand
    ## Heading         medium
    ### Sub-heading    small, underlined
    - item             bullet (indent 2 spaces per level), also * or +
    1. item            numbered
    -> item            hand-drawn arrow, then text
    !! item            IMPORTANT line, red ink with an arrow
    > item             side note in the accent ink
    [ ] item / [x]     checkbox
    ---                hand-drawn separator
    (blank line)       skip a line
Inline:
    ==text==  highlighter      =={pink}text==  other colour (yellow green pink blue orange)
    **text**  bold             __text__  underline       ~~text~~  crossed out
    {red}text{/}  ink colour (black blue red green purple pencil)
    ->  or  =>  drawn arrow
    $...$  maths (LaTeX subset): \frac \sum \int \sqrt x^2 x_i \left( \right) \mathbb{R}
           \in \forall \exists \leq \neq \infty Greek letters, intervals [0, 1[ ...
    $$...$$ on its own line: a displayed formula
"""
import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
FONT_DIRS = [HERE.parent / "fonts", HERE / "fonts", Path.cwd() / "fonts", Path.cwd()]
FONTS = {
    "caveat": "Caveat.ttf",
    "kalam": "Kalam.ttf",
    "patrick": "PatrickHand.ttf",
    "gochi": "GochiHand.ttf",
    "indie": "IndieFlower.ttf",
    "playpen": "PlaypenSans.ttf",
}
INKS = {
    "black": (18, 18, 22),
    "blue": (24, 72, 192),
    "red": (200, 48, 44),
    "green": (28, 122, 68),
    "purple": (106, 56, 166),
    "pencil": (82, 82, 88),
}
HIGHLIGHTS = {
    "yellow": (255, 238, 70),
    "green": (160, 240, 150),
    "pink": (255, 170, 205),
    "blue": (160, 215, 255),
    "orange": (255, 196, 110),
}
PAGES = {  # pixels at 300 dpi, physical width in mm
    "a4": ((2480, 3508), 210),
    "letter": ((2550, 3300), 216),
    "ipad": ((2480, 3306), 210),
    "ipad-landscape": ((3306, 2480), 280),
}
SIZES = {"small": 0.82, "medium": 1.0, "large": 1.22}
DRAWN = {"∩": 1.1, "∪": 1.1, "∅": 1.2, "∈": 1.05, "⇒": 2.1, "←": 2.0,  # advance in x-heights
         "∀": 1.2, "∃": 1.0, "∉": 1.1, "⊂": 1.1, "⊆": 1.1, "≡": 1.05, "→": 1.85, "⇔": 2.4,
         "↦": 1.95, "∘": 0.75, "∇": 1.2, "⋯": 1.5,
         "=": 1.0, "−": 0.95, "-": 0.72, "+": 0.96, "<": 0.98, ">": 0.98, "∞": 1.34,
         "≈": 1.05, "≠": 1.05, "±": 1.05, "∓": 1.05,
         "×": 0.95, "≤": 1.05, "≥": 1.05, "∴": 1.15, "∵": 1.15, "~": 1.0, ".": 0.34,
         "/": 0.64, "(": 0.48, ")": 0.48, "[": 0.50, "]": 0.50, "|": 0.38, "{": 0.56, "}": 0.56,
         "∑": 1.18, "Σ": 1.18, "∏": 1.15}
SYM_ASC = {"∀": 1.45, "∃": 1.45, "∇": 1.45, "∅": 1.15, "⊆": 1.1,
           "/": 1.38, "(": 1.44, ")": 1.44, "[": 1.44, "]": 1.44, "|": 1.44, "{": 1.46, "}": 1.46,
           "∑": 1.38, "Σ": 1.38, "∏": 1.38}
SYM_DESC = {"/": 0.18, "(": 0.24, ")": 0.24, "[": 0.24, "]": 0.24, "|": 0.24, "{": 0.26, "}": 0.26}
SYSTEM_FALLBACKS = [  # last resort for Greek and rare symbols (not handwritten, but no empty boxes)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "C:/Windows/Fonts/seguisym.ttf",
]


# --------------------------------------------------------------------------- utils

def find_font(name):
    fname = FONTS.get(name.lower(), name)
    p = Path(fname)
    if p.is_file():
        return p
    for d in FONT_DIRS:
        if (d / fname).is_file():
            return d / fname
    sys.exit(f"font not found: {name} (looked in {', '.join(str(d) for d in FONT_DIRS)})")


def wobble_points(p0, p1, amp, rng, n=None):
    """Points along p0 -> p1 with a slow hand-made wobble."""
    (x0, y0), (x1, y1) = p0, p1
    length = math.hypot(x1 - x0, y1 - y0) or 1
    n = n or max(4, int(length / 12))
    nx, ny = -(y1 - y0) / length, (x1 - x0) / length
    ph1, ph2 = rng.uniform(0, 6.28), rng.uniform(0, 6.28)
    f1, f2 = rng.uniform(0.6, 1.4), rng.uniform(2.0, 3.5)
    pts = []
    for i in range(n + 1):
        t = i / n
        off = amp * (0.7 * math.sin(f1 * 3.14 * t + ph1) + 0.3 * math.sin(f2 * 3.14 * t + ph2))
        pts.append((x0 + (x1 - x0) * t + nx * off, y0 + (y1 - y0) * t + ny * off))
    return pts


def warp_glyph(m, amp, rng, cells=4):
    """Smooth random elastic distortion focused tightly on the active glyph ink box."""
    if amp <= 0.25:
        return m
    bb = m.getbbox()
    if not bb:
        return m
    bx0, by0, bx1, by1 = bb
    gx0 = max(1, bx0 - 4)
    gy0 = max(1, by0 - 4)
    gx1 = min(m.width - 1, bx1 + 4)
    gy1 = min(m.height - 1, by1 + 4)
    if gx1 - gx0 < 6 or gy1 - gy0 < 6:
        return m
    xs_dst = [0] + [int(round(gx0 + (gx1 - gx0) * i / cells)) for i in range(cells + 1)] + [m.width]
    ys_dst = [0] + [int(round(gy0 + (gy1 - gy0) * j / cells)) for j in range(cells + 1)] + [m.height]
    # Deduplicate strictly monotonic grid coordinates
    xs_u, ys_u = [xs_dst[0]], [ys_dst[0]]
    for v in xs_dst[1:]:
        if v > xs_u[-1]:
            xs_u.append(v)
    for v in ys_dst[1:]:
        if v > ys_u[-1]:
            ys_u.append(v)
    nx, ny = len(xs_u) - 1, len(ys_u) - 1
    if nx < 2 or ny < 2:
        return m
    pts = []
    for j in range(ny + 1):
        row = []
        for i in range(nx + 1):
            is_inner = (0 < i < nx) and (0 < j < ny)
            dx = rng.gauss(0, amp) if is_inner else 0.0
            dy = rng.gauss(0, amp) if is_inner else 0.0
            row.append((xs_u[i] + dx, ys_u[j] + dy))
        pts.append(row)
    mesh = []
    for j in range(ny):
        for i in range(nx):
            box = (xs_u[i], ys_u[j], xs_u[i + 1], ys_u[j + 1])
            a, b, c, d = pts[j][i], pts[j + 1][i], pts[j + 1][i + 1], pts[j][i + 1]
            mesh.append((box, (a[0], a[1], b[0], b[1], c[0], c[1], d[0], d[1])))
    return m.transform(m.size, Image.MESH, mesh, Image.BICUBIC)


def deform_glyph(m, bx, by, gx, mess, rng, extra_deg=0.0):
    """Apply subtle per-character aspect-ratio, slant/shear, rotation, and smooth curve jitter
    so repeated letters/digits have natural human micro-differences while staying 100% sharp."""
    jm = min(1.4, mess / 0.55)
    if jm <= 1e-4 and abs(extra_deg) <= 1e-4:
        return m
    sx = max(0.90, min(1.11, 1.0 + rng.gauss(0, 0.048 * jm))) if jm > 0 else 1.0
    sy = max(0.91, min(1.10, 1.0 + rng.gauss(0, 0.042 * jm))) if jm > 0 else 1.0
    sh = max(-0.12, min(0.12, rng.gauss(0, 0.055 * jm))) if jm > 0 else 0.0
    deg = (rng.gauss(0, 2.2 * jm) if jm > 0 else 0.0) + extra_deg
    rad = math.radians(-deg)
    cs, sn = math.cos(rad), math.sin(rad)
    # Inverse affine mapping anchored strictly at (bx, by)
    a0 = cs / sx + (sh * (-sn)) / (sx * sy)
    a1 = sn / sx + (sh * cs) / (sx * sy)
    a2 = bx - a0 * bx - a1 * by
    b0 = -sn / sy
    b1 = cs / sy
    b2 = by - b0 * bx - b1 * by
    m = m.transform(m.size, Image.AFFINE, (a0, a1, a2, b0, b1, b2), Image.BICUBIC)
    if jm > 0:
        m = warp_glyph(m, min(1.30, max(0.55, gx * 0.033 * jm)), rng, cells=3)
    # Restore crisp alpha edge after bicubic resampling so strokes never blur
    m = m.point(lambda v: max(0, min(255, int((v - 18) * 255 / 206))))
    return m


def pen_line(draw, pts, width):
    w_px = max(1, int(round(width)))
    draw.line(pts, fill=255, width=w_px, joint="curve")
    if w_px >= 3:
        r = (w_px - 1) * 0.42
        for x, y in (pts[0], pts[-1]):
            draw.ellipse((x - r, y - r, x + r, y + r), fill=255)


# --------------------------------------------------------------------------- glyph sources

class FontSource:
    """Glyphs from a handwriting TTF."""

    def __init__(self, path):
        self.path = str(path)
        self.cache = {}
        f = ImageFont.truetype(self.path, 200)
        self.xh_ratio = -f.getbbox("x", anchor="ls")[1] / 200.0
        self.space_ratio = f.getlength(" ") / 200.0
        self.cov, self.notdef, self.fallbacks = {}, None, []

    def font(self, px):
        px = max(6, int(round(px)))
        if px not in self.cache:
            self.cache[px] = ImageFont.truetype(self.path, px)
        return self.cache[px]

    def covers(self, ch):
        """True if the font really has this character (not the empty 'tofu' box)."""
        if ch not in self.cov:
            f = self.font(48)

            def sig(c):
                im = Image.new("L", (90, 90), 0)
                ImageDraw.Draw(im).text((20, 15), c, font=f, fill=255)
                return im.tobytes()

            if self.notdef is None:
                self.notdef = sig("\ue000")
            self.cov[ch] = ch.isspace() or sig(ch) != self.notdef
        return self.cov[ch]

    def pick(self, ch):
        if self.covers(ch):
            return self
        for fb in self.fallbacks:
            if fb.covers(ch):
                return fb
        return self

    def has(self, ch):
        return True

    def metrics(self, ch, xh):
        src = self.pick(ch)
        f = src.font(xh / src.xh_ratio)
        x0, y0, x1, y1 = f.getbbox(ch, anchor="ls")
        return f.getlength(ch), max(0, -y0), max(0, y1)

    def width(self, ch, xh):
        src = self.pick(ch)
        return src.font(xh / src.xh_ratio).getlength(ch)

    def glyph(self, ch, xh, rng):
        """Return (mask L, baseline_x, baseline_y, advance) for x-height xh px."""
        src = self.pick(ch)
        if src is not self:
            return src.glyph(ch, xh, rng)
        f = self.font(xh / self.xh_ratio)
        x0, y0, x1, y1 = f.getbbox(ch, anchor="ls")
        pad = int(xh * 0.8) + 4
        w, h = max(1, x1 - x0) + 2 * pad, max(1, y1 - y0) + 2 * pad
        m = Image.new("L", (w, h), 0)
        bx, by = pad - x0, pad - y0
        ImageDraw.Draw(m).text((bx, by), ch, font=f, fill=255, anchor="ls")
        return m, bx, by, f.getlength(ch)

    def space(self, xh):
        return max(xh / self.xh_ratio * self.space_ratio, xh * 0.85)


class HandSource:
    """Glyphs learned from a filled template (see `learn`)."""

    def __init__(self, folder, fallback):
        self.dir = Path(folder)
        meta = json.loads((self.dir / "hand.json").read_text())
        self.xh_px = meta["xheight_px"]
        self.glyphs = {}
        for g in meta["glyphs"]:
            img = Image.open(self.dir / g["file"]).convert("L")
            self.glyphs.setdefault(g["char"], []).append((img, g["baseline"]))
        self.fallback = fallback
        self.gap = 0.04
        # whole words / letter pairs cut from real pages ("the", "he", "dollar") are used as one piece
        self.multi = sorted((k for k in self.glyphs if len(k) > 1), key=len, reverse=True)

    def merge(self, chars):
        """Replace runs of characters that exist as one handwritten piece."""
        if not self.multi:
            return chars
        out, i = [], 0
        while i < len(chars):
            for k in self.multi:
                n = len(k)
                seg = chars[i:i + n]
                if len(seg) == n and "".join(c for c, _ in seg) == k and all(st == seg[0][1] for _, st in seg):
                    out.append((k, seg[0][1]))
                    i += n
                    break
            else:
                out.append(chars[i])
                i += 1
        return out

    def accented(self, ch):
        """é -> ('e', acute) when only the plain letter was learned."""
        if ch in self.glyphs or len(ch) != 1:
            return None
        import unicodedata
        d = unicodedata.normalize("NFD", ch)
        if len(d) == 2 and d[0] in self.glyphs and d[1] in "\u0301\u0300\u0302\u0308\u0327":
            return d[0], d[1]
        return None

    def built_percent(self, ch):
        """% not learned: build it from the writer's own small o's and a short slash."""
        return ch == "%" and "%" not in self.glyphs and ("o" in self.glyphs or "0" in self.glyphs)

    def has(self, ch):
        return ch in self.glyphs or self.accented(ch) is not None or self.built_percent(ch)

    def metrics(self, ch, xh):
        if self.built_percent(ch):
            return self.width(ch, xh), xh * 1.5, xh * 0.05
        acc = self.accented(ch)
        if acc:
            return self.metrics(acc[0], xh)
        if ch not in self.glyphs:
            return self.fallback.metrics(ch, xh)
        img, base = self.glyphs[ch][0]
        s = xh / self.xh_px
        return self.width(ch, xh), base * s, max(0, (img.height - base) * s)

    def width(self, ch, xh):
        if self.built_percent(ch):
            return xh * 1.05 + xh * self.gap
        acc = self.accented(ch)
        if acc:
            return self.width(acc[0], xh)
        if ch not in self.glyphs:
            return self.fallback.width(ch, xh)
        avg = sum(img.width for img, _ in self.glyphs[ch]) / len(self.glyphs[ch])
        gp = 0.11 if ch.isdigit() else (0.08 if ch in "lI1" else self.gap)
        return avg * xh / self.xh_px + xh * gp

    def percent(self, xh, rng):
        """A real % is compact: two small loops hugging a short slash."""
        pad = int(xh * 0.8) + 4
        W0, top = xh * 1.05, xh * 1.5            # glyph box: digit height
        m = Image.new("L", (int(W0) + 2 * pad, int(top + xh * 0.1) + 2 * pad), 0)
        bx, by = pad, pad + top
        w = max(1, int(round(xh * 0.12)))
        sl = rng.uniform(-0.04, 0.04) * xh
        d = ImageDraw.Draw(m)
        d.line([(bx + W0 * 0.12 + sl, by + xh * 0.02), (bx + W0 * 0.5, by - top * 0.52),
                (bx + W0 * 0.88 + sl, by - top * 0.98)], fill=255, width=w, joint="curve")
        src = self.glyphs.get("o") or self.glyphs.get("0")
        for cx, cy in ((0.2, 0.78), (0.8, 0.2)):     # top-left loop, bottom-right loop
            img, _ = rng.choice(src)
            bb = img.getbbox() or (0, 0, img.width, img.height)
            img = img.crop(bb)
            k = xh * 0.52 / max(1, img.height)
            g = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)
            x = bx + W0 * cx - g.width / 2 + rng.gauss(0, xh * 0.02)
            y = by - top * cy - g.height / 2 + rng.gauss(0, xh * 0.02)
            m.paste(ImageChops.lighter(m.crop((int(x), int(y), int(x) + g.width, int(y) + g.height)), g), (int(x), int(y)))
        return m, bx, by, W0 + xh * self.gap

    def glyph(self, ch, xh, rng):
        if self.built_percent(ch):
            return self.percent(xh, rng)
        acc = self.accented(ch)
        if acc:
            m, bx, by, adv = self.glyph(acc[0], xh, rng)
            box = m.getbbox() or (bx, by - xh, bx + xh * 0.6, by)
            cx = (box[0] + box[2]) / 2 + rng.gauss(0, xh * 0.04)
            top, bot = box[1], box[3]
            d = ImageDraw.Draw(m)
            w = max(1, int(round(xh * 0.09)))
            k = acc[1]
            if k == "\u0301":    # acute
                pts = [(cx - xh * 0.12, top - xh * 0.18), (cx + xh * 0.2, top - xh * 0.55)]
            elif k == "\u0300":  # grave
                pts = [(cx - xh * 0.2, top - xh * 0.55), (cx + xh * 0.12, top - xh * 0.18)]
            elif k == "\u0302":  # circumflex
                pts = [(cx - xh * 0.25, top - xh * 0.2), (cx, top - xh * 0.5), (cx + xh * 0.25, top - xh * 0.2)]
            elif k == "\u0308":  # diaeresis
                for dx in (-0.17, 0.17):
                    x0, y0 = cx + dx * xh, top - xh * 0.3
                    d.ellipse((x0 - w, y0 - w, x0 + w, y0 + w), fill=255)
                pts = None
            else:                 # cedilla
                pts = [(cx, bot - 1), (cx + xh * 0.05, bot + xh * 0.15), (cx + xh * 0.2, bot + xh * 0.25),
                       (cx + xh * 0.05, bot + xh * 0.45), (cx - xh * 0.15, bot + xh * 0.42)]
            if pts:
                d.line(pts, fill=255, width=w, joint="curve")
            return m, bx, by, adv
        if ch not in self.glyphs:
            return self.fallback.glyph(ch, xh, rng)
        img, base = rng.choice(self.glyphs[ch])
        s = xh / self.xh_px
        w, h = max(1, int(img.width * s)), max(1, int(img.height * s))
        g = img.resize((w, h), Image.LANCZOS)
        if s < 0.75:
            boost = 1.38 if s < 0.48 else 1.20
            g = g.point(lambda v, b=boost: min(255, int(v * b)))
        pad = int(xh * 0.8) + 4
        m = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
        m.paste(g, (pad, pad))
        gp = 0.11 if ch.isdigit() else (0.08 if ch in "lI1" else self.gap)
        return m, pad, pad + base * s, w + xh * gp

    def space(self, xh):
        return xh * 0.62


# --------------------------------------------------------------------------- iPad engine
# The notebook engine keeps the photo texture of each learned letter (pressure, faint parts).
# The iPad engine is separate: it retraces every letter as one clean, even Apple Pencil stroke.

def _thin(b):
    """Zhang-Suen thinning: reduce a stroke to its centre line (numpy only)."""
    I = np.pad(b.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            P2, P3, P4 = I[:-2, 1:-1], I[:-2, 2:], I[1:-1, 2:]
            P5, P6, P7 = I[2:, 2:], I[2:, 1:-1], I[2:, :-2]
            P8, P9 = I[1:-1, :-2], I[:-2, :-2]
            seq = [P2, P3, P4, P5, P6, P7, P8, P9, P2]
            B = sum(seq[:8].__iter__())
            A = sum(((seq[k] == 0) & (seq[k + 1] == 1)).astype(np.uint8) for k in range(8))
            C = I[1:-1, 1:-1] == 1
            if step == 0:
                c2 = (P2 * P4 * P6 == 0) & (P4 * P6 * P8 == 0)
            else:
                c2 = (P2 * P4 * P8 == 0) & (P2 * P6 * P8 == 0)
            kill = C & (B >= 2) & (B <= 6) & (A == 1) & c2
            if kill.any():
                I[1:-1, 1:-1][kill] = 0
                changed = True
        if not changed:
            return I[1:-1, 1:-1].astype(bool)


PENCIL_VERSION = "4"  # bump when pencil_stroke changes, so cached strokes are rebuilt


def pencil_stroke(img, width):
    """Learned letter (photo cut) -> one smooth stroke of even width, no faint or missing parts.
    Works at 3x size with gentle closing so small loops in 4, 5, 8, e, a stay crisp and open."""
    K = 3
    a = np.asarray(img, dtype=np.float32) / 255.0
    pad = int(width) + 4
    a = np.pad(a, pad)
    big_img = Image.fromarray((a * 255).astype(np.uint8)).resize((a.shape[1] * K, a.shape[0] * K), Image.BICUBIC)
    b = Image.fromarray(((np.asarray(big_img) > 26) * 255).astype(np.uint8))
    b = b.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))     # close micro-gaps while keeping inner loops open
    b = b.filter(ImageFilter.GaussianBlur(K * 0.85))                            # smooth outline without melting counters shut
    sk = _thin(np.asarray(b) > 127)
    comps = _components(sk)
    if len(comps) > 1:  # photo specks would become dots: drop tiny pieces, keep real dots (i, j, :)
        bigc = max(c[4] for c in comps)
        for c in comps:
            if c[4] < max(4 * K, 0.06 * bigc) and c[4] < 7 * K:
                for (y, s0, e0) in c[5]:
                    sk[y, s0:e0] = False
    st = Image.fromarray((sk * 255).astype(np.uint8))
    r = max(1, int(round(width * K / 2)))
    for _ in range(r):
        st = st.filter(ImageFilter.MaxFilter(3))
    st = st.filter(ImageFilter.GaussianBlur(r * 0.72))            # crisp rounded stroke edges
    st = st.point(lambda v: max(0, min(255, int((v - 62) * 255 / 55))))
    st = st.resize((st.width // K, st.height // K), Image.LANCZOS)  # back to size, anti-aliased
    return st.crop((pad, pad, st.width - pad, st.height - pad))


def PencilHandSource(hand):
    """The iPad engine's copy of a handwriting: every learned letter retraced once, at full
    resolution, as an even pencil stroke (the notebook engine keeps the original samples)."""
    import copy
    import hashlib
    ph = copy.copy(hand)
    w = max(2.6, hand.xh_px * 0.092)
    cache = Path(hand.dir) / "pencil"   # computed once, then reused (shipped for the default hand)
    try:
        cache.mkdir(exist_ok=True)
    except OSError:
        cache = None
    ph.glyphs = {}
    for c, v in hand.glyphs.items():
        out = []
        for img, base in v:
            key = hashlib.md5(img.tobytes() + str(img.size).encode() + PENCIL_VERSION.encode()).hexdigest()[:16]
            f = cache / f"{key}.png" if cache else None
            if f is not None and f.is_file():
                g = Image.open(f).convert("L")
            else:
                g = pencil_stroke(img, w)
                if f is not None:
                    try:
                        g.save(f)
                    except OSError:
                        pass
            out.append((g, base))
        ph.glyphs[c] = out
    return ph


# --------------------------------------------------------------------------- markup parsing

INLINE = re.compile(
    r"(\$(?P<math>[^$]+)\$)|"
    r"(==(?:\{(?P<hlc>[a-z]+)\})?(?P<hl>.+?)==)"
    r"|(\*\*(?P<b>.+?)\*\*)"
    r"|(__(?P<u>.+?)__)"
    r"|(~~(?P<s>.+?)~~)"
    r"|(\{(?P<col>[a-z]+)\}(?P<ct>.+?)\{/\})"
    r"|(?P<arrow>->|=>|→)"
)


def parse_inline(text, base):
    """Return a list of (char, style). '\x01' stands for a drawn arrow."""
    out = []

    def emit(s, st):
        pos = 0
        for m in INLINE.finditer(s):
            for c in s[pos:m.start()]:
                out.append((c, st))
            if m.group("math") is not None:
                out.append(("\x02", {**st, "math": m.group("math")}))
            elif m.group("arrow"):
                out.append(("\x01", st))
            elif m.group("hl") is not None:
                emit(m.group("hl"), {**st, "hl": m.group("hlc") or "yellow"})
            elif m.group("b") is not None:
                emit(m.group("b"), {**st, "bold": True})
            elif m.group("u") is not None:
                emit(m.group("u"), {**st, "ul": True})
            elif m.group("s") is not None:
                emit(m.group("s"), {**st, "strike": True})
            elif m.group("ct") is not None:
                emit(m.group("ct"), {**st, "ink": m.group("col")})
            pos = m.end()
        for c in s[pos:]:
            out.append((c, st))

    emit(unicode_scripts_to_math(text.replace("\\$", "\x03")), base)
    out = [("$" if c == "\x03" else c, st) for c, st in out]
    return out


def parse_blocks(src):
    blocks = []
    for raw in src.splitlines():
        line = raw.rstrip()
        if not line.strip():
            blocks.append({"kind": "blank"})
            continue
        indent = (len(line.expandtabs(2)) - len(line.expandtabs(2).lstrip())) // 2
        s = line.strip()
        b = {"kind": "text", "level": indent, "text": s}
        if re.fullmatch(r"-{3,}|_{3,}|\*{3,}", s):
            b = {"kind": "rule"}
        elif s.startswith("### "):
            b = {"kind": "h3", "text": s[4:]}
        elif s.startswith("## "):
            b = {"kind": "h2", "text": s[3:]}
        elif s.startswith("# "):
            b = {"kind": "h1", "text": s[2:]}
        elif s.startswith("!! "):
            b = {"kind": "important", "level": indent, "text": s[3:]}
        elif s.startswith(("-> ", "=> ", "→ ")):
            b = {"kind": "arrow", "level": indent, "text": s.split(" ", 1)[1]}
        elif re.match(r"\[( |x|X)\] ", s):
            b = {"kind": "check", "level": indent, "done": s[1] in "xX", "text": s[4:]}
        elif re.match(r"[-*+•] ", s):
            b = {"kind": "bullet", "level": indent, "text": s[2:]}
        elif re.match(r"\d{1,3}[.)] ", s):
            num, rest = s.split(" ", 1)
            b = {"kind": "number", "level": indent, "num": num, "text": rest}
        elif s.startswith("> "):
            b = {"kind": "aside", "level": indent, "text": s[2:]}
        elif s.startswith("$$") and s.endswith("$$") and len(s) > 4:
            b = {"kind": "math", "level": indent, "text": s[2:-2]}
        blocks.append(b)
    while blocks and blocks[-1]["kind"] == "blank":
        blocks.pop()
    return blocks


# --------------------------------------------------------------------------- paper

def make_paper(kind, size, line_h, first_base, margin_x, mm, rng):
    W, H = size
    bg = (255, 255, 255) if kind in ("grid", "dots", "blank", "lines") else (252, 251, 246)
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    if kind == "grid":
        step = line_h / 2
        col = (206, 212, 222)
        y = first_base % step
        while y < H:
            d.line([(0, y), (W, y)], fill=col, width=1)
            y += step
        x = margin_x % step
        while x < W:
            d.line([(x, 0), (x, H)], fill=col, width=1)
            x += step
    elif kind == "dots":
        step = line_h / 2
        y = first_base % step
        while y < H:
            x = margin_x % step
            while x < W:
                d.ellipse((x - 1.6, y - 1.6, x + 1.6, y + 1.6), fill=(180, 186, 196))
                x += step
            y += step
    elif kind == "squared":
        step = 5 * mm
        col = (178, 192, 216)
        y = first_base % step
        while y < H:
            d.line([(0, y), (W, y)], fill=col, width=1)
            y += step
        x = 0.0
        while x < W:
            d.line([(x, 0), (x, H)], fill=col, width=1)
            x += step
        mx = margin_x - 0.5 * step
        d.line([(mx, 0), (mx, H)], fill=(222, 120, 128), width=2)
    elif kind == "lines":
        lw = max(1, int(round(0.15 * mm)))
        col = (212, 214, 220)  # clean tablet light-gray ruled lines
        y = first_base
        while y < H - 6 * mm:
            d.line([(0, int(round(y))), (W, int(round(y)))], fill=col, width=lw)
            y += line_h
        mx = int(round(margin_x - 3.0 * mm))  # subtle tablet margin line
        d.line([(mx, 0), (mx, H)], fill=(204, 206, 214), width=lw)
    elif kind == "college":
        col = (170, 196, 232)  # notebook blue
        y = first_base
        while y < H - line_h * 0.3:
            d.line([(0, y), (W, y)], fill=col, width=2)
            y += line_h
        mx = margin_x - 0.45 * line_h  # red margin line, like a real lined notebook
        d.line([(mx, 0), (mx, H)], fill=(232, 140, 150), width=2)
    elif kind == "seyes":
        big, small = line_h, line_h / 4
        heavy, light, vert = (150, 140, 205), (205, 200, 236), (205, 200, 236)
        y = first_base - big * math.floor(first_base / big)
        k = 0
        while y < H:
            d.line([(0, y), (W, y)], fill=heavy if k % 4 == 0 else light, width=2 if k % 4 == 0 else 1)
            y += small
            k += 1
        x = margin_x
        while x < W:
            d.line([(x, 0), (x, H)], fill=vert, width=1)
            x += big
        d.line([(margin_x - 0.35 * big, 0), (margin_x - 0.35 * big, H)], fill=(225, 110, 120), width=2)
    if kind in ("seyes", "college", "squared"):
        a = np.asarray(img).astype(np.int16)
        noise = np.random.default_rng(rng.randint(0, 1 << 30)).normal(0, 2.0, a.shape[:2])[..., None]
        img = Image.fromarray(np.clip(a + noise, 0, 255).astype(np.uint8))
    return img


# --------------------------------------------------------------------------- renderer

# --------------------------------------------------------------------------- maths ($...$)
# A small LaTeX subset laid out by hand: fractions, sums/products/integrals with bounds,
# limits, roots, powers and indices, \left( \right), intervals, \mathbb, accents, Greek.

MATH_SYMBOLS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ",
    "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ",
    "Theta": "Θ", "Lambda": "Λ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "infty": "∞", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "approx": "≈", "simeq": "≈", "sim": "~", "equiv": "≡", "pm": "±", "mp": "∓", "times": "×",
    "cdot": "·", "div": "÷", "in": "∈", "notin": "∉", "subset": "⊂", "subseteq": "⊆",
    "cup": "∪", "cap": "∩", "emptyset": "∅", "varnothing": "∅", "forall": "∀", "exists": "∃",
    "to": "→", "rightarrow": "→", "longrightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒",
    "implies": "⇒", "Leftrightarrow": "⇔", "iff": "⇔", "mapsto": "↦", "partial": "∂",
    "nabla": "∇", "circ": "∘", "ldots": "…", "dots": "…", "cdots": "⋯", "prime": "′",
    "mid": "|", "vert": "|", "|": "‖", "{": "{", "}": "}", "%": "%", "#": "#", "&": "&",
    "_": "_", "neg": "¬", "lnot": "¬", "wedge": "∧", "land": "∧", "vee": "∨", "lor": "∨",
    "propto": "∝", "perp": "⊥", "angle": "∠", "degree": "°", "ell": "ℓ",
    "therefore": "∴", "because": "∵",
}
MATH_FUNCS = {"sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan", "sinh",
              "cosh", "tanh", "log", "ln", "lg", "exp", "max", "min", "sup", "inf", "det", "dim",
              "ker", "deg", "gcd", "arg", "Var", "Cov", "E", "Pr", "mod"}
BIG_OPS = {"sum": "∑", "prod": "∏", "int": "∫", "iint": "∬", "oint": "∮", "bigcup": "∪",
           "bigcap": "∩", "lim": "lim", "limsup": "lim sup", "liminf": "lim inf"}
MATH_SPACES = {",": 0.25, ":": 0.35, ";": 0.45, " ": 0.45, "quad": 1.4, "qquad": 2.8, "!": -0.2}
SPACED = set("=<>+−±∓×÷·≤≥≠≈≡~∈∉⊂⊆∪∩→←⇒⇔↦∝∧∨∴∵")
TALL = set("bdfhkltABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()[]{}|/∑∏∫∂δθλ")
SUPMAP = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱᶜᵃᵇᵈᵉᶠᵍʰʲᵏˡᵐᵒᵖʳˢᵗᵘᵛʷˣʸᶻᵀ",
                  "0123456789+-=()nicabdefghjklmoprstuvwxyzT"))
SUBMAP = dict(zip("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼᵣᵤᵥ", "0123456789+-=()aeoxhklmnpstijruv"))


def unicode_scripts_to_math(text):
    """'Aᶜ' -> 'A$^{c}$', 'x₁' -> 'x$_{1}$' (outside existing $...$)."""
    parts = re.split(r"(\$[^$]*\$)", text)
    for i, p in enumerate(parts):
        if p.startswith("$"):
            continue
        p = re.sub("[" + "".join(SUPMAP) + "]+", lambda m: "$^{" + "".join(SUPMAP[c] for c in m.group()) + "}$", p)
        p = re.sub("[" + "".join(SUBMAP) + "]+", lambda m: "$_{" + "".join(SUBMAP[c] for c in m.group()) + "}$", p)
        parts[i] = p
    return "".join(parts)


def math_tokens(src):
    return [t for t in re.findall(r"\\[A-Za-z]+|\\.|[{}^_\[\]]|\s+|.", src)]


class MathParser:
    def __init__(self, src):
        self.t = math_tokens(src)
        self.i = 0

    def peek(self, skip_space=True):
        while skip_space and self.i < len(self.t) and self.t[self.i].isspace():
            self.i += 1
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expr(self, stop=None):
        nodes = []
        while True:
            tok = self.peek()
            if tok is None or tok == stop or (stop == "\\right" and tok == "\\right"):
                return ("group", nodes)
            if tok == "}" and stop != "}":
                self.take()
                continue
            nodes.append(self.scripted())

    def raw_arg(self):
        """Text inside {...}, spaces kept."""
        if self.peek() != "{":
            return self.take() or ""
        self.take()
        depth, out = 1, []
        while self.i < len(self.t):
            tok = self.t[self.i]
            self.i += 1
            if tok == "{":
                depth += 1
            elif tok == "}":
                depth -= 1
                if depth == 0:
                    break
            out.append(tok[1:] if tok.startswith("\\") and len(tok) == 2 else tok)
        return "".join(out)

    def arg(self):
        tok = self.peek()
        if tok == "{":
            self.take()
            g = self.expr("}")
            self.take()
            return g
        return self.atom()

    def scripted(self):
        base = self.atom()
        sup = sub = None
        while self.peek() in ("^", "_"):
            if self.take() == "^":
                sup = self.arg()
            else:
                sub = self.arg()
        if base[0] == "bigop":
            return ("bigop", base[1], sub, sup)
        if sup is not None or sub is not None:
            return ("script", base, sup, sub)
        return base

    def atom(self):
        tok = self.take()
        if tok is None:
            return ("group", [])
        if tok == "{":
            g = self.expr("}")
            self.take()
            return g
        if tok in ("^", "_"):  # script with no base
            self.i -= 1
            return ("group", [])
        if not tok.startswith("\\"):
            return ("ch", {"-": "−", "*": "·", "'": "′", "\x03": "$"}.get(tok, tok))
        name = tok[1:]
        if name in MATH_SPACES:
            return ("space", MATH_SPACES[name])
        if name in ("frac", "dfrac", "tfrac", "cfrac"):
            return ("frac", self.arg(), self.arg())
        if name == "binom":
            return ("delim", "(", ("frac", self.arg(), self.arg(), "nobar"), ")")
        if name == "sqrt":
            idx = None
            if self.peek() == "[":
                self.take()
                idx = self.expr("]")
                self.take()
            return ("sqrt", idx, self.arg())
        if name in BIG_OPS:
            return ("bigop", BIG_OPS[name], None, None)
        if name in ("text", "mathrm", "textrm", "operatorname", "textbf", "mathbf", "mbox"):
            return ("text", self.raw_arg())
        if name == "mathbb":
            return ("bb", self.raw_arg().strip()[:1])
        if name in ("vec", "overrightarrow", "bar", "overline", "hat", "widehat", "tilde", "dot", "underline"):
            return ("accent", name, self.arg())
        if name == "left":
            left = self.take()
            body = self.expr("\\right")
            self.take()
            right = self.take()
            fix = lambda d: {"\\{": "{", "\\}": "}", "\\|": "‖", "\\langle": "⟨", "\\rangle": "⟩",
                             "\\lfloor": "⌊", "\\rfloor": "⌋", "\\lceil": "⌈", "\\rceil": "⌉"}.get(d, d)
            return ("delim", fix(left), body, fix(right))
        if name in ("right", "displaystyle", "limits", "nolimits", "big", "Big", "bigg", "Bigg"):
            return ("group", [])
        if name in MATH_FUNCS:
            return ("func", name)
        if name in MATH_SYMBOLS:
            return ("ch", MATH_SYMBOLS[name])
        return ("text", name)


class MBox:
    def __init__(self, w=0.0, a=0.0, d=0.0, items=None):
        self.w, self.a, self.d = w, a, d
        self.items = items or []

    def place(self, other, dx, dy):
        for it in other.items:
            if it[0] == "pen":
                self.items.append(("pen", [(x + dx, y + dy) for x, y in it[1]], it[2]))
            else:
                self.items.append((it[0], it[1], it[2] + dx, it[3] + dy, it[4]))


def hcat(boxes):
    out = MBox()
    for b in boxes:
        out.place(b, out.w, 0)
        out.w += b.w
        out.a, out.d = max(out.a, b.a), max(out.d, b.d)
    return out


class MathLayout:
    def __init__(self, metrics, display=False):
        self.cm = metrics  # (char, xh) -> (advance, ascent, descent)
        self.display = display
        self.root_xh = None

    def char(self, c, xh, level):
        if c in DRAWN:
            w, a, d = DRAWN[c] * xh, SYM_ASC.get(c, 1.05) * xh, SYM_DESC.get(c, 0.0) * xh
            box = MBox(w, a, d, [("sym", c, 0, 0, xh)])
        else:
            w, a, d = self.cm(c, xh)
            box = MBox(w, a, d, [("ch", c, 0, 0, xh)])
        if c in SPACED:
            pad = xh * (0.4 if level == 0 else 0.16)
            sp = MBox(pad)
            return hcat([sp, box, MBox(pad)])
        if c in ",;" and level == 0:
            return hcat([box, MBox(xh * 0.35)])
        return box

    def text(self, s, xh, upright_gap=0.0):
        boxes = []
        for c in s:
            boxes.append(MBox(xh * 0.55) if c == " " else self.char(c, xh, 9))
        if upright_gap:
            boxes.append(MBox(xh * upright_gap))
        return hcat(boxes)

    def lay(self, n, xh, level=0):
        if level == 0 and self.root_xh is None:
            self.root_xh = xh
        min_sub = (self.root_xh or xh) * 0.66
        kind = n[0]
        if kind == "group":
            kids, boxes = n[1], []
            for i, c in enumerate(kids):
                nxt = kids[i + 1] if i + 1 < len(kids) else None
                prv = kids[i - 1] if i > 0 else None
                if (c == ("ch", ",") or c == ("ch", ".")) and nxt and nxt[0] == "ch" and nxt[1].isdigit() \
                        and prv and prv[0] == "ch" and prv[1].isdigit():
                    boxes.append(self.char(c[1], xh, 9))  # 50,000 and 3,14 stay tight
                else:
                    boxes.append(self.lay(c, xh, level))
            return hcat(boxes)
        if kind == "ch":
            return self.char(n[1], xh, level)
        if kind == "space":
            return MBox(n[1] * xh)
        if kind == "text":
            return self.text(n[1], xh)
        if kind == "func":
            return self.text(n[1], xh, 0.2)
        if kind == "bb":
            b = self.char(n[1] or "R", xh, level)
            b.items = [("bb", n[1] or "R", 0, 0, xh)]
            return b
        if kind == "script":
            base = self.lay(n[1], xh, level)
            sxh = max(min_sub, xh * (0.76 if level == 0 else 0.84))
            parts = []
            w = 0
            out = MBox(base.w, base.a, base.d)
            out.place(base, 0, 0)
            if n[2] is not None:
                sup = self.lay(n[2], sxh, level + 1)
                y = max(xh * 0.75, base.a - sup.a * 0.45)
                out.place(sup, base.w + xh * 0.06, y)
                out.a = max(out.a, y + sup.a)
                w = max(w, sup.w)
            if n[3] is not None:
                sub = self.lay(n[3], sxh, level + 1)
                y = -max(xh * 0.38, base.d + xh * 0.15)
                out.place(sub, base.w + xh * 0.04, y)
                out.d = max(out.d, -y + sub.d)
                w = max(w, sub.w)
            out.w = base.w + w + xh * 0.12
            return out
        if kind == "frac":
            k = 0.90 if (self.display and level == 0) else 0.78
            fxh = max(min_sub, xh * (k if level == 0 else 0.85))
            num, den = self.lay(n[1], fxh, level + 1), self.lay(n[2], fxh, level + 1)
            w = max(num.w, den.w) + xh * 0.45
            axis, gap = xh * 0.52, xh * (0.28 if self.display else 0.23)
            out = MBox(w + xh * 0.18)
            out.place(num, xh * 0.09 + (w - num.w) / 2, axis + gap + num.d)
            out.place(den, xh * 0.09 + (w - den.w) / 2, axis - gap - den.a)
            if len(n) < 4:
                out.items.append(("pen", [(xh * 0.09, axis), (xh * 0.09 + w, axis)], 0.13))
            out.a = axis + gap + num.d + num.a
            out.d = max(0, -(axis - gap - den.a - den.d))
            return out
        if kind == "sqrt":
            body = self.lay(n[2], xh, level)
            top = max(body.a, xh * 1.05) + xh * 0.22
            bot = body.d + xh * 0.12
            x0 = xh * 0.85
            out = MBox(x0 + body.w + xh * 0.25, top + xh * 0.08, bot)
            out.place(body, x0, 0)
            out.items.append(("pen", [(0, xh * 0.42), (xh * 0.2, xh * 0.55), (xh * 0.45, -bot),
                                      (x0 - xh * 0.1, top), (x0 + body.w + xh * 0.15, top)], 0.13))
            if n[1] is not None:
                idx = self.lay(n[1], max(min_sub, xh * 0.65), level + 2)
                out.place(idx, 0, xh * 0.75)
            return out
        if kind == "bigop":
            sym, lower, upper = n[1], n[2], n[3]
            sxh = max(min_sub, xh * 0.74)
            lo = self.lay(lower, sxh, level + 1) if lower is not None else None
            up = self.lay(upper, sxh, level + 1) if upper is not None else None
            if sym.startswith("lim"):
                op = self.text(sym, xh)
                axis = 0
            else:
                big = 1.44 if self.display else (1.24 if level == 0 else 1.08)
                oxh = xh * big * (1.20 if sym in "∫∬∮" else 1.0)
                if sym in DRAWN:
                    w, a, d = DRAWN[sym] * oxh, SYM_ASC.get(sym, 1.38) * oxh, 0.0
                    item_kind = "sym"
                else:
                    w, a, d = self.cm(sym, oxh)
                    item_kind = "ch"
                axis = xh * 0.52
                y = axis - (a - d) / 2
                op = MBox(w, a + y, max(0, d - y), [(item_kind, sym, 0, y, oxh)])
            out = MBox()
            side = sym in "∫∬∮"
            if side:
                out.place(op, 0, 0)
                out.w, out.a, out.d = op.w, op.a, op.d
                ext = 0
                if up is not None:
                    out.place(up, op.w + xh * 0.02, op.a - up.a * 0.9)
                    ext = max(ext, up.w)
                if lo is not None:
                    dx = xh * 0.25 if sym in "∫∬∮" else -xh * 0.02
                    out.place(lo, op.w - dx, -op.d - lo.a * 0.1)
                    ext = max(ext, lo.w - dx)
                    out.d = max(out.d, op.d + lo.d + lo.a * 0.1)
                out.w = op.w + ext + xh * 0.25
                return out
            w = max(op.w, lo.w if lo else 0, up.w if up else 0)
            out.place(op, (w - op.w) / 2, 0)
            out.a, out.d = op.a, op.d
            gap = xh * 0.20
            if up is not None:
                y = op.a + gap + up.d
                out.place(up, (w - up.w) / 2, y)
                out.a = y + up.a
            if lo is not None:
                y = -(op.d + gap + lo.a)
                out.place(lo, (w - lo.w) / 2, y)
                out.d = -y + lo.d
            out.w = w + xh * 0.30
            return out
        if kind == "accent":
            body = self.lay(n[2], xh, level)
            name = n[1]
            top = max(body.a, xh * 1.05) + xh * 0.2
            out = MBox(body.w, top + xh * 0.3, body.d)
            out.place(body, 0, 0)
            x0, x1 = xh * 0.05, max(body.w - xh * 0.05, xh * 0.5)
            if name in ("vec", "overrightarrow"):
                out.items.append(("pen", [(x0, top), (x1, top)], 0.1))
                out.items.append(("pen", [(x1 - xh * 0.25, top + xh * 0.18), (x1, top), (x1 - xh * 0.25, top - xh * 0.18)], 0.1))
            elif name in ("bar", "overline"):
                out.items.append(("pen", [(x0, top), (x1, top)], 0.1))
            elif name == "underline":
                out.items.append(("pen", [(x0, -body.d - xh * 0.2), (x1, -body.d - xh * 0.2)], 0.1))
            elif name in ("hat", "widehat"):
                m = (x0 + x1) / 2
                out.items.append(("pen", [(m - xh * 0.3, top - xh * 0.05), (m, top + xh * 0.2), (m + xh * 0.3, top - xh * 0.05)], 0.1))
            elif name == "tilde":
                m = (x0 + x1) / 2
                out.items.append(("pen", [(m - xh * 0.35, top), (m - xh * 0.15, top + xh * 0.12),
                                          (m + xh * 0.12, top - xh * 0.02), (m + xh * 0.35, top + xh * 0.1)], 0.1))
            else:  # dot
                m = (x0 + x1) / 2
                out.items.append(("pen", [(m, top), (m + 0.5, top)], 0.16))
            return out
        if kind == "delim":
            body = self.lay(n[2], xh, level)
            a = max(body.a, xh * 1.0) + xh * 0.15
            d = max(body.d, xh * 0.1) + xh * 0.15
            if a + d < xh * 2.15:  # normal size: drawn inline delimiter
                parts = [self.char(n[1], xh, 9)] if n[1] != "." else []
                parts.append(body)
                if n[3] != ".":
                    parts.append(self.char(n[3], xh, 9))
                return hcat(parts)
            w = xh * 0.54
            out = MBox(0, a, d)
            for side, dl in ((0, n[1]), (1, n[3])):
                if dl == ".":
                    if side == 0:
                        continue
                    out.w += 0
                    continue
                x = out.w
                out.items.append(("delim", dl, x, 0, (w, a, d)))
                out.w += w
                if side == 0:
                    out.place(body, out.w, 0)
                    out.w += body.w + xh * 0.05
            return out
        return MBox()

    @staticmethod
    def delim_pts(dl, x, w, a, d, side):
        h = a + d
        mid = (a - d) / 2
        if dl in "([":
            pass
        if dl == "(" or dl == ")":
            s = 1 if dl == "(" else -1
            cx = x + (w * 0.85 if dl == "(" else w * 0.15)
            return [(cx - s * w * 0.7 * math.sin(math.pi * t / 12), -d + h * t / 12) for t in range(13)]
        if dl == "[" or dl == "⌊" or dl == "⌈":
            return [(x + w * 0.75, a), (x + w * 0.25, a), (x + w * 0.25, -d), (x + w * 0.75, -d)]
        if dl == "]":
            return [(x + w * 0.25, a), (x + w * 0.75, a), (x + w * 0.75, -d), (x + w * 0.25, -d)]
        if dl in ("{", "}"):
            s = 1 if dl == "{" else -1
            xa, xb = (x + w * 0.85, x + w * 0.2) if dl == "{" else (x + w * 0.15, x + w * 0.8)
            xm = (xa + xb) / 2
            return [(xa, a), (xm, a - h * 0.08), (xm, mid + h * 0.08), (xb, mid),
                    (xm, mid - h * 0.08), (xm, -d + h * 0.08), (xa, -d)]
        if dl in ("⟨", "⟩"):
            xa, xb = (x + w * 0.8, x + w * 0.2) if dl == "⟨" else (x + w * 0.2, x + w * 0.8)
            return [(xa, a), (xb, mid), (xa, -d)]
        return [(x + w * 0.5, a), (x + w * 0.5, -d)]  # | and ‖


class Page:
    def __init__(self, paper, inks, pen="ballpoint"):
        self.pen = pen  # "ballpoint" (paper: pressure and grain) or "digital" (tablet: solid, even ink)
        self.paper = paper
        self.hl = Image.new("RGB", paper.size, (255, 255, 255))
        self.masks = {}
        self.inks = inks

    def mask(self, ink):
        if ink not in self.masks:
            self.masks[ink] = Image.new("L", self.paper.size, 0)
        return self.masks[ink]

    def stamp(self, ink, m, x, y):
        tgt = self.mask(ink)
        x, y = int(round(x)), int(round(y))
        W, H = tgt.size
        cx0, cy0 = max(0, x), max(0, y)
        cx1, cy1 = min(W, x + m.width), min(H, y + m.height)
        if cx1 <= cx0 or cy1 <= cy0:
            return
        part = m.crop((cx0 - x, cy0 - y, cx1 - x, cy1 - y))
        box = (cx0, cy0, cx1, cy1)
        tgt.paste(ImageChops.lighter(tgt.crop(box), part), box)

    def finish(self):
        out = ImageChops.multiply(self.paper, self.hl.filter(ImageFilter.GaussianBlur(1.2)))
        if self.pen == "digital":  # Apple Pencil look: every stroke fully opaque, crisp high-contrast edges
            for ink, m in self.masks.items():
                col = Image.new("RGB", out.size, INKS.get(ink, INKS["black"]))
                a = np.asarray(m.filter(ImageFilter.GaussianBlur(0.55)), dtype=np.float32) / 255.0
                a = np.clip(a * 2.35 - 0.12, 0, 1)  # keep even thin strokes and subscripts 100% solid & crisp
                out = Image.composite(col, out, Image.fromarray((a * 255).astype(np.uint8)))
            return out
        W, H = out.size
        rng = np.random.default_rng(len(self.masks) * 7919 + W)
        # slow pressure changes (big blobs) and paper grain (pixel noise)
        low = Image.fromarray((rng.random((H // 24 + 2, W // 24 + 2)) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
        low = np.asarray(low, dtype=np.float32) / 255.0
        grain = rng.random((H, W)).astype(np.float32)
        tex = np.clip(0.88 + 0.22 * low, 0, 1) * np.clip(0.92 + 0.08 * grain, 0, 1)  # pressure varies, never washes out
        for ink, m in self.masks.items():
            col = Image.new("RGB", out.size, INKS.get(ink, INKS["black"]))
            a = np.asarray(m.filter(ImageFilter.GaussianBlur(0.5)), dtype=np.float32) / 255.0
            a = np.clip(np.power(a, 0.8) * 1.45, 0, 1) * tex  # firm ballpoint: faint parts of a stroke come up solid
            out = Image.composite(col, out, Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)))
        return out


class Renderer:
    def __init__(self, source, paper="grid", page="a4", size="medium", ink="black",
                 accent="blue", important="red", bullet="arrow", seed=None, mess=1.0, drift=0.0,
                 pen="ballpoint", scratch_rate=0):
        self.src = source
        self.rng = random.Random(seed)
        (self.W, self.H), width_mm = PAGES[page]
        self.mm = self.W / width_mm
        self.paper_kind = paper
        if paper == "seyes":
            self.line_h = 8 * self.mm
            self.xh = 2.6 * self.mm * SIZES[size]
        elif paper == "college":
            self.line_h = 7.1 * self.mm * SIZES[size] ** 0.5
            self.xh = 0.33 * self.line_h * SIZES[size] ** 0.5
        elif paper == "lines":
            self.line_h = 0.0318 * self.W * SIZES[size]
            self.xh = 0.335 * self.line_h
        else:
            self.line_h = 0.0355 * self.W * SIZES[size]
            self.xh = 0.34 * self.line_h
        if paper == "squared":
            self.line_h = 8.5 * self.mm * SIZES[size] ** 0.5
            self.xh = 0.42 * self.line_h * SIZES[size] ** 0.5
        if paper == "lines":
            self.margin_x = 16.5 * self.mm
            self.right = self.W - 10 * self.mm
            self.first_base = 14 * self.mm
            self.bottom_margin = 9 * self.mm
        else:
            self.margin_x = (32 if paper in ("seyes", "college", "squared") else 12) * self.mm
            self.right = self.W - (14 if paper in ("seyes", "college", "squared") else 10) * self.mm
            self.first_base = (30 if paper in ("seyes", "college", "squared") else 13) * self.mm
            self.bottom_margin = (14 if paper in ("seyes", "college", "squared") else 9) * self.mm
        if paper == "seyes":
            self.first_base = round(self.first_base / self.line_h) * self.line_h
        self.ink, self.accent, self.important = ink, accent, important
        self.bullet = bullet
        self.mess = mess
        self.drift = drift  # average downward slope of lines, in degrees
        self.pen = pen
        self.scratch_rate = max(0, int(scratch_rate))
        self._scratch_uid = 0
        self.pages = []
        self._math = {}
        self.new_page()

    # page / line bookkeeping
    def new_page(self):
        paper = make_paper(self.paper_kind, (self.W, self.H), self.line_h, self.first_base,
                           self.margin_x, self.mm, self.rng)
        self.page = Page(paper, INKS, self.pen)
        self.pages.append(self.page)
        self.base = self.first_base
        self.ink_bottom = -1e9
        self.prev_boxes = []
        self.page_lines = 0
        self.page_scratches = 0
        if self.scratch_rate > 0:
            if self.scratch_rate == 2:
                g = self.rng.choice((1, 2, 2))
            else:
                g = self.rng.randint(1, self.scratch_rate) if self.scratch_rate > 1 else 1
            slots = [self.rng.randint(2, 9)]
            if g >= 2:
                slots.append(self.rng.randint(14, 24))
            for extra in range(2, min(g, 5)):
                slots.append(min(33, slots[-1] + self.rng.randint(5, 8)))
            self.scratch_targets = sorted(slots)
        else:
            self.scratch_targets = []

    def snap_base(self):
        if self.paper_kind in ("lines", "college"):
            k = max(0, math.ceil((self.base - self.first_base - 2.0) / self.line_h))
            self.base = self.first_base + k * self.line_h
            if self.base > self.H - self.bottom_margin:
                self.new_page()

    def next_line(self, n=1.0):
        self.base += self.line_h * n
        if self.base > self.H - self.bottom_margin:
            self.new_page()

    def ensure_room(self, n=1.0):
        if self.base + self.line_h * max(0.0, n - 1.0) > self.H - self.bottom_margin:
            self.new_page()

    # drawing primitives
    def j(self, sd):
        return self.rng.gauss(0, sd * self.mess)

    def draw_strokes(self, ink, strokes, width):
        """strokes: list of point lists in page coords."""
        xs = [p[0] for s in strokes for p in s]
        ys = [p[1] for s in strokes for p in s]
        pad = width * 2 + 4
        x0, y0 = min(xs) - pad, min(ys) - pad
        m = Image.new("L", (int(max(xs) - x0 + pad) + 1, int(max(ys) - y0 + pad) + 1), 0)
        d = ImageDraw.Draw(m)
        for s in strokes:
            pen_line(d, [(x - x0, y - y0) for x, y in s], width)
        self.page.stamp(ink, m, x0, y0)

    def arrow(self, x, base, ink, xh):
        w = xh * (1.95 + self.j(0.08))
        y = base - xh * (0.55 + self.j(0.05))
        shaft = self._wb((x, y), (x + w, y + self.j(xh * 0.10)), xh, 0.042, 0.05)
        tx, ty = shaft[-1]
        hd1 = xh * (0.56 + self.j(0.06))
        hd2 = xh * (0.56 + self.j(0.06))
        w1 = self._wb((tx - hd1, ty - hd1 * (0.68 + self.j(0.08))), (tx, ty), xh, 0.032, 0.045)
        w2 = self._wb((tx, ty), (tx - hd2, ty + hd2 * (0.68 + self.j(0.08))), xh, 0.032, 0.045)
        self.draw_strokes(ink, [shaft, w1, w2], max(2.0, xh * 0.14))
        return w + xh * 0.6

    def bullet_mark(self, x, base, ink, xh, level):
        style = self.bullet if level == 0 else ("dash" if self.bullet != "dot" else "dot")
        if style == "dot":
            r = xh * 0.22
            cx, cy = x + xh * 0.3, base - xh * 0.5
            m = Image.new("L", (int(r * 4), int(r * 4)), 0)
            ImageDraw.Draw(m).ellipse((r, r, r * 3 + self.j(1), r * 3 + self.j(1)), fill=255)
            self.page.stamp(ink, m, cx - r * 2, cy - r * 2)
            return xh * 1.2
        if style == "dash":
            y = base - xh * 0.5
            self.draw_strokes(ink, [wobble_points((x + xh * 0.2, y), (x + xh * 1.0, y + self.j(1)), 1, self.rng)], xh * 0.15)
            return xh * 1.3
        # hooked arrow like ↳
        top, bot = base - xh * 1.55, base - xh * 0.4
        hook = wobble_points((x + xh * 0.15, top), (x + xh * 0.22, bot - xh * 0.25), 1, self.rng)
        hook += [(x + xh * 0.32, bot - xh * 0.02), (x + xh * 0.6, bot)]
        tip = (x + xh * 1.45, bot + self.j(1))
        hook += [tip]
        hd = xh * 0.42
        head = [(tip[0] - hd, tip[1] - hd * 0.75), tip, (tip[0] - hd, tip[1] + hd * 0.75)]
        self.draw_strokes(ink, [hook, head], xh * 0.14)
        return xh * 1.9

    def _wb(self, p0, p1, xh, amp_k=0.036, bow_k=0.045):
        """Hand-drawn segment from p0 to p1 with subtle natural arc bow + slow wobble."""
        jm = min(1.5, self.mess / 0.55)
        if jm <= 1e-4:
            return [p0, p1]
        (x0, y0), (x1, y1) = p0, p1
        L = math.hypot(x1 - x0, y1 - y0) or 1.0
        nx, ny = -(y1 - y0) / L, (x1 - x0) / L
        bow = self.j(xh * bow_k)
        base_pts = wobble_points(p0, p1, xh * amp_k * jm, self.rng, n=max(5, int(L / 10)))
        n_pts = len(base_pts) - 1
        return [(px + nx * bow * math.sin(math.pi * idx / n_pts),
                 py + ny * bow * math.sin(math.pi * idx / n_pts))
                for idx, (px, py) in enumerate(base_pts)]

    def draw_delim(self, dl, x, top_y, bot_y, w, ink, xh):
        """Draw organic hand-varied (), [], {}, |, ⟨⟩ with visible angle, arc, and wobble variation."""
        jm = min(1.5, self.mess / 0.55)
        j = self.j
        pw = max(2.0, xh * 0.126)
        top_y = top_y + j(xh * 0.065)
        bot_y = bot_y + j(xh * 0.065)
        h = max(xh * 0.6, bot_y - top_y)
        tilt_dx = h * math.tan(math.radians(j(5.8)))
        h_scale = max(1.0, h / (xh * 1.7))
        if dl in ("(", ")"):
            s = 1 if dl == "(" else -1
            cx_top = x + (w * 0.82 if dl == "(" else w * 0.18) + j(w * 0.09)
            cx_bot = cx_top + tilt_dx + j(w * 0.09)
            depth = w * (0.60 + self.rng.uniform(-0.18, 0.22) * jm) * (1.0 + 0.08 * (h_scale - 1.0))
            asym = self.rng.uniform(-0.22, 0.22) * jm
            ph = self.rng.uniform(0, 6.28)
            pts = []
            N = 16
            for k in range(N + 1):
                t = k / N
                t_skew = max(0.0, min(1.0, t + asym * t * (1 - t)))
                bx = cx_top + (cx_bot - cx_top) * t
                arc = math.sin(math.pi * t_skew) * depth
                wob = math.sin(2.4 * math.pi * t + ph) * (xh * 0.035 * jm * (h_scale ** 0.5))
                pts.append((bx - s * (arc + wob), top_y + h * t))
            self.draw_strokes(ink, [pts], pw)
        elif dl in ("[", "]", "⌊", "⌈"):
            is_left = dl in ("[", "⌊", "⌈")
            sx_top = x + (w * 0.24 if is_left else w * 0.76) + j(w * 0.08)
            sx_bot = sx_top + tilt_dx + j(w * 0.07)
            d_dir = 1 if is_left else -1
            tw_top = w * (0.54 + self.rng.uniform(-0.13, 0.16) * jm)
            tw_bot = w * (0.54 + self.rng.uniform(-0.13, 0.16) * jm)
            tx_top = sx_top + d_dir * tw_top
            tx_bot = sx_bot + d_dir * tw_bot
            ty_top_end = top_y + j(xh * 0.085)
            ty_bot_end = bot_y + j(xh * 0.085)
            spine = self._wb((sx_top, top_y), (sx_bot, bot_y), xh, 0.042 * (h_scale ** 0.6), 0.075 * h_scale)
            strokes = [spine]
            if dl != "⌊":
                strokes.append(self._wb((tx_top, ty_top_end), (sx_top, top_y), xh, 0.036, 0.05))
            if dl != "⌈":
                strokes.append(self._wb((sx_bot, bot_y), (tx_bot, ty_bot_end), xh, 0.036, 0.05))
            self.draw_strokes(ink, strokes, pw)
        elif dl in ("{", "}"):
            xa_t = x + (w * 0.80 if dl == "{" else w * 0.20) + j(w * 0.06)
            xa_b = xa_t + tilt_dx
            xb = x + (w * 0.20 if dl == "{" else w * 0.80) + tilt_dx * 0.5 + j(w * 0.08)
            xm_t = (xa_t + xb) * 0.52 + j(w * 0.05)
            xm_b = (xa_b + xb) * 0.52 + j(w * 0.05)
            mid_y = (top_y + bot_y) * 0.5 + j(h * 0.045)
            s1 = self._wb((xa_t, top_y), (xm_t, mid_y - h * 0.08), xh, 0.034, 0.05 * h_scale) + [(xb, mid_y)]
            s2 = [(xb, mid_y)] + self._wb((xm_b, mid_y + h * 0.08), (xa_b, bot_y), xh, 0.034, 0.05 * h_scale)
            self.draw_strokes(ink, [s1, s2], pw)
        elif dl in ("⟨", "⟩"):
            xa_t = x + (w * 0.78 if dl == "⟨" else w * 0.22)
            xb = x + (w * 0.22 if dl == "⟨" else w * 0.78) + tilt_dx * 0.5 + j(w * 0.06)
            mid_y = (top_y + bot_y) * 0.5 + j(h * 0.04)
            self.draw_strokes(ink, [self._wb((xa_t, top_y), (xb, mid_y), xh, 0.036, 0.05 * h_scale),
                                    self._wb((xb, mid_y), (xa_t + tilt_dx, bot_y), xh, 0.036, 0.05 * h_scale)], pw)
        else:  # | and ‖
            cx_t = x + w * 0.50 + j(w * 0.08)
            cx_b = cx_t + tilt_dx
            self.draw_strokes(ink, [self._wb((cx_t, top_y), (cx_b, bot_y), xh, 0.038 * (h_scale ** 0.5), 0.065 * h_scale)], pw)

    def symbol(self, c, x, base, ink, xh):
        """Pen-drawn maths symbols with natural hand jitter, micro-tilt, and stroke variation."""
        if c in "()[]|{}":
            self.draw_delim(c, x, base - SYM_ASC[c] * xh, base + SYM_DESC[c] * xh, DRAWN[c] * xh, ink, xh)
            return DRAWN[c] * xh
        j, pw = self.j, max(2.0, xh * 0.124)
        jm = min(1.5, self.mess / 0.55)
        wb = lambda a, b, ak=0.036, bk=0.045: self._wb(a, b, xh, ak, bk)
        x0, w = x + xh * 0.14 + j(xh * 0.025), xh * 0.85
        top, bot = base - xh * 1.05 + j(xh * 0.03), base + j(xh * 0.03)
        if c in "∩∪":
            n = 12
            tilt = j(xh * 0.05)
            w_u = w * (1 + j(0.05))
            arc = []
            for i in range(n + 1):
                t = math.pi * i / n
                ax = x0 + w_u / 2 - math.cos(t) * w_u / 2 + j(xh * 0.012)
                if c == "∩":
                    ay = top + w_u / 2 - math.sin(t) * w_u / 2 + tilt * (i / n)
                else:
                    ay = bot - w_u / 2 + math.sin(t) * w_u / 2 + tilt * (i / n)
                arc.append((ax, ay))
            if c == "∩":
                strokes = [wb((x0 + j(xh * 0.03), bot), arc[0], 0.02, 0.02) + arc[1:] + wb(arc[-1], (x0 + w_u + j(xh * 0.03), bot + tilt + j(xh * 0.04)), 0.02, 0.02)[1:]]
            else:
                strokes = [wb((x0 + j(xh * 0.03), top), arc[0], 0.02, 0.02) + arc[1:] + wb(arc[-1], (x0 + w_u + j(xh * 0.03), top + tilt + j(xh * 0.04)), 0.02, 0.02)[1:]]
        elif c == "∅":
            cx, cy, r = x0 + w / 2, base - xh * 0.55 + j(xh * 0.03), xh * (0.48 + j(0.03))
            circ = [(cx + r * math.cos(t) * 0.9 + j(xh * 0.012), cy + r * math.sin(t) + j(xh * 0.012)) for t in
                    [k * 2 * math.pi / 16 for k in range(18)]]
            strokes = [circ, wb((cx - r * 0.72 + j(xh * 0.05), cy + r * 1.28), (cx + r * 0.72 + j(xh * 0.05), cy - r * 1.28))]
        elif c == "∈":
            cy = base - xh * 0.52 + j(xh * 0.03)
            n = 11
            ry = xh * (0.48 + j(0.035))
            arc = [(x0 + w - (w * math.sin(math.pi * i / n)) + j(xh * 0.01), cy - ry * math.cos(math.pi * i / n))
                   for i in range(n + 1)]
            strokes = [arc, wb((x0 + w * 0.05, cy + j(xh * 0.02)), (x0 + w * 0.85, cy + j(xh * 0.05)))]
        elif c == "⇒":
            cy = base - xh * (0.54 + j(0.05))
            L = xh * (1.76 + j(0.10))
            sl = j(xh * 0.14)
            d1 = xh * (0.165 + j(0.035))
            d2 = xh * (0.165 + j(0.035))
            s_top = wb((x0 + j(xh * 0.08), cy - d1 + j(xh * 0.03)), (x0 + L - xh * 0.17 + j(xh * 0.06), cy - d1 + sl + j(xh * 0.055)), 0.052, 0.075)
            s_bot = wb((x0 + j(xh * 0.08), cy + d2 + j(xh * 0.03)), (x0 + L - xh * 0.17 + j(xh * 0.06), cy + d2 + sl + j(xh * 0.055)), 0.052, 0.075)
            tx, ty = x0 + L + j(xh * 0.05), cy + sl + j(xh * 0.045)
            w_up = wb((tx - xh * (0.48 + j(0.07)), ty - xh * (0.43 + j(0.07))), (tx, ty), 0.042, 0.065)
            w_dn = wb((tx, ty), (tx - xh * (0.48 + j(0.07)), ty + xh * (0.43 + j(0.07))), 0.042, 0.065)
            strokes = [s_top, s_bot, w_up, w_dn]
        elif c == "∀":
            t, b2 = base - xh * 1.44 + j(xh * 0.04), base + j(xh * 0.03)
            xm_v = x0 + w * 0.55 + j(xh * 0.04)
            strokes = [wb((x0, t), (xm_v, b2)), wb((xm_v, b2), (x0 + w * 1.08, t + j(xh * 0.05))),
                       wb((x0 + w * 0.2, base - xh * 0.74), (x0 + w * 0.9, base - xh * 0.74 + j(xh * 0.05)))]
        elif c == "∃":
            t = base - xh * 1.44 + j(xh * 0.04)
            rx_e = x0 + w * 0.85 + j(xh * 0.04)
            strokes = [wb((x0, t), (rx_e, t + j(xh * 0.04))), wb((rx_e, t), (rx_e + j(xh * 0.04), bot)),
                       wb((rx_e, bot), (x0, bot + j(xh * 0.04))),
                       wb((x0 + w * 0.16, base - xh * 0.72), (rx_e, base - xh * 0.72 + j(xh * 0.04)))]
        elif c in "⊂⊆∉":
            cy = base - xh * 0.55 + (xh * 0.12 if c == "⊆" else 0) + j(xh * 0.03)
            r = xh * (0.44 + j(0.03))
            arc = [(x0 + w - (w * math.sin(math.pi * i / 10)) + j(xh * 0.012), cy - r * math.cos(math.pi * i / 10)) for i in range(11)]
            strokes = [arc]
            if c == "∉":
                strokes.append(wb((x0 + w * 0.05, cy), (x0 + w * 0.85, cy + j(xh * 0.04))))
                strokes.append(wb((x0 + w * 0.25, cy + r * 1.3), (x0 + w * 0.75 + j(xh * 0.05), cy - r * 1.3)))
            if c == "⊆":
                strokes.append(wb((x0 + w * 0.08, base + xh * 0.12), (x0 + w, base + xh * 0.12 + j(xh * 0.05))))
        elif c == "≡":
            sl = j(xh * 0.06)
            strokes = [wb((x0 + j(xh * 0.03), base - xh * k), (x0 + w + j(xh * 0.03), base - xh * k + sl + j(xh * 0.04)))
                       for k in (0.25, 0.55, 0.85)]
        elif c in "→↦":
            cy = base - xh * (0.54 + j(0.04))
            L = xh * (1.58 + j(0.07))
            sl = j(xh * 0.09)
            s0 = x0 + (xh * 0.2 if c == "↦" else 0)
            tx, ty = s0 + L, cy + sl
            strokes = [wb((s0, cy), (tx, ty), 0.04, 0.055),
                       wb((tx - xh * (0.44 + j(0.05)), ty - xh * (0.37 + j(0.05))), (tx, ty), 0.032, 0.045),
                       wb((tx, ty), (tx - xh * (0.44 + j(0.05)), ty + xh * (0.37 + j(0.05))), 0.032, 0.045)]
            if c == "↦":
                strokes.append(wb((s0, cy - xh * 0.35), (s0 + j(xh * 0.04), cy + xh * 0.35)))
        elif c == "⇔":
            cy = base - xh * (0.54 + j(0.04))
            L = xh * (2.18 + j(0.08))
            sl = j(xh * 0.09)
            d1, d2 = xh * (0.165 + j(0.02)), xh * (0.165 + j(0.02))
            tx, ty = x0 + L, cy + sl
            lx0, ly0 = x0, cy
            strokes = [
                wb((x0 + xh * 0.16, cy - d1), (tx - xh * 0.16, ty - d1 + j(xh * 0.04))),
                wb((x0 + xh * 0.16, cy + d2), (tx - xh * 0.16, ty + d2 + j(xh * 0.04))),
                wb((tx - xh * (0.45 + j(0.05)), ty - xh * (0.41 + j(0.05))), (tx, ty), 0.03, 0.04),
                wb((tx, ty), (tx - xh * (0.45 + j(0.05)), ty + xh * (0.41 + j(0.05))), 0.03, 0.04),
                wb((lx0 + xh * (0.45 + j(0.05)), ly0 - xh * (0.41 + j(0.05))), (lx0, ly0), 0.03, 0.04),
                wb((lx0, ly0), (lx0 + xh * (0.45 + j(0.05)), ly0 + xh * (0.41 + j(0.05))), 0.03, 0.04),
            ]
        elif c == "∘":
            cx, cy, r = x0 + xh * 0.25, base - xh * 0.55 + j(xh * 0.03), xh * (0.20 + j(0.02))
            strokes = [[(cx + r * math.cos(k * math.pi / 6) + j(xh * 0.01), cy + r * math.sin(k * math.pi / 6) + j(xh * 0.01)) for k in range(13)]]
        elif c == "∇":
            t = base - xh * 1.4
            strokes = [wb((x0, t), (x0 + w * 1.1, t + j(xh * 0.04))),
                       wb((x0 + w * 1.1, t), (x0 + w * 0.55, base)),
                       wb((x0 + w * 0.55, base), (x0, t))]
        elif c == "⋯":
            cy = base - xh * 0.50
            strokes = [[(x0 + xh * k + j(xh * 0.03), cy + j(xh * 0.04)),
                        (x0 + xh * k + xh * 0.04 + j(xh * 0.03), cy + j(xh * 0.04))] for k in (0.1, 0.6, 1.1)]
            pw = max(2.4, xh * 0.18)
        elif c == "/":
            dx_sl = xh * (0.48 + self.rng.uniform(-0.22, 0.28) * jm)
            bx_s = x + xh * 0.06 + j(xh * 0.04)
            by_s = base + xh * (0.16 + j(0.06))
            tx_s = bx_s + dx_sl + j(xh * 0.04)
            ty_s = base - xh * (1.30 + j(0.07))
            strokes = [wb((tx_s, ty_s), (bx_s, by_s), 0.048, 0.085)]
        elif c in ("−", "-"):
            cy = base - xh * (0.52 + j(0.035))
            w_bar = xh * ((0.68 if c == "−" else 0.48) + j(0.04))
            strokes = [wb((x0 + xh * 0.04, cy), (x0 + xh * 0.04 + w_bar, cy + j(xh * 0.06)), 0.034, 0.045)]
        elif c == "+":
            cy = base - xh * (0.52 + j(0.035))
            cx = x0 + xh * (0.36 + j(0.035))
            strokes = [
                wb((x0 + xh * 0.04, cy), (x0 + xh * 0.68 + j(xh * 0.04), cy + j(xh * 0.06)), 0.032, 0.04),
                wb((cx + j(xh * 0.03), base - xh * (0.86 + j(0.04))), (cx + j(xh * 0.04), base - xh * (0.18 + j(0.04))), 0.032, 0.04),
            ]
        elif c in ("<", ">"):
            cy = base - xh * (0.52 + j(0.04))
            lx, rx = x0 + xh * 0.06 + j(xh * 0.03), x0 + xh * 0.72 + j(xh * 0.04)
            open_u = xh * (0.30 + j(0.045))
            open_d = xh * (0.30 + j(0.045))
            sl = j(xh * 0.06)
            if c == "<":
                vx, vy = lx, cy + j(xh * 0.03)
                strokes = [wb((rx + j(xh * 0.04), cy - open_u + sl), (vx, vy), 0.032, 0.045),
                           wb((vx, vy), (rx + j(xh * 0.04), cy + open_d + sl), 0.032, 0.045)]
            else:
                vx, vy = rx, cy + j(xh * 0.03)
                strokes = [wb((lx + j(xh * 0.04), cy - open_u), (vx, vy + sl), 0.032, 0.045),
                           wb((vx, vy + sl), (lx + j(xh * 0.04), cy + open_d), 0.032, 0.045)]
        elif c == "∞":
            cy = base - xh * (0.50 + j(0.03))
            rx, ry = xh * (0.52 + j(0.035)), xh * (0.25 + j(0.025))
            sl = j(0.10)
            cx = x0 + rx
            pts = []
            for k in range(25):
                t = k * 2 * math.pi / 24
                px_i = rx * math.cos(t) / (1 + math.sin(t) ** 2)
                py_i = ry * 1.45 * math.sin(t) * math.cos(t) / (1 + math.sin(t) ** 2)
                pts.append((cx + px_i + j(xh * 0.01), cy + py_i + px_i * sl + j(xh * 0.01)))
            strokes = [pts]
        elif c in ("=", "≠"):
            sl = j(xh * 0.055)
            k1, k2 = 0.28 + j(0.025), 0.70 + j(0.025)
            strokes = [
                wb((x0 + j(xh * 0.03), base - xh * k1), (x0 + xh * (0.72 + j(0.04)), base - xh * k1 + sl + j(xh * 0.035)), 0.032, 0.04),
                wb((x0 + j(xh * 0.03), base - xh * k2), (x0 + xh * (0.72 + j(0.04)), base - xh * k2 + sl + j(xh * 0.035)), 0.032, 0.04),
            ]
            if c == "≠":
                strokes.append(wb((x0 + xh * (0.16 + j(0.05)), base - xh * 0.06), (x0 + xh * (0.58 + j(0.05)), base - xh * 0.96), 0.034, 0.045))
        elif c == "≈":
            strokes = []
            sl_base = j(xh * 0.12)
            for k in (0.32, 0.70):
                cy = base - xh * (k + j(0.045))
                sx_w = x0 + j(xh * 0.065)
                wl = xh * (0.76 + j(0.08))
                amp = xh * (0.112 + self.rng.uniform(-0.035, 0.045) * jm)
                ph = self.rng.uniform(-0.48, 0.48) * jm
                sl = sl_base + j(xh * 0.075)
                asym = self.rng.uniform(0.72, 1.30) if jm > 0 else 1.0
                pts = []
                for t_i in range(13):
                    u = t_i / 12
                    s_val = math.sin(2 * math.pi * u + ph)
                    if s_val < 0:
                        s_val *= asym
                    pts.append((sx_w + wl * u, cy - s_val * amp + sl * u + j(xh * 0.022)))
                strokes.append(pts)
        elif c in ("±", "∓"):
            cy = base - xh * ((0.66 if c == "±" else 0.36) + j(0.03))
            by2 = base - xh * ((0.19 if c == "±" else 0.85) + j(0.03))
            cx = x0 + xh * (0.38 + j(0.035))
            strokes = [
                wb((x0 + xh * 0.04, cy), (x0 + xh * 0.72, cy + j(xh * 0.05))),
                wb((cx, base - xh * 0.96), (cx + j(xh * 0.04), base - xh * 0.32)),
                wb((x0 + xh * 0.05 + j(xh * 0.03), by2), (x0 + xh * 0.72 + j(xh * 0.03), by2 + j(xh * 0.055))),
            ]
        elif c == "×":
            strokes = [
                wb((x0 + xh * 0.08 + j(xh * 0.04), base - xh * (0.86 + j(0.04))), (x0 + xh * 0.68 + j(xh * 0.04), base - xh * (0.18 + j(0.04))), 0.032, 0.045),
                wb((x0 + xh * 0.68 + j(xh * 0.04), base - xh * (0.86 + j(0.04))), (x0 + xh * 0.08 + j(xh * 0.04), base - xh * (0.18 + j(0.04))), 0.032, 0.045),
            ]
        elif c in ("≤", "≥"):
            cy = base - xh * (0.63 + j(0.045))
            lx, rx = x0 + xh * 0.05 + j(xh * 0.045), x0 + xh * 0.73 + j(xh * 0.05)
            sl = j(xh * 0.11)
            open_u = xh * (0.28 + j(0.055))
            open_d = xh * (0.24 + j(0.055))
            if c == "≤":
                vx, vy = lx, cy + j(xh * 0.04)
                arm1 = wb((rx + j(xh * 0.05), cy - open_u + sl * 0.5), (vx, vy), 0.042, 0.065)
                arm2 = wb((vx, vy), (rx + j(xh * 0.05), cy + open_d + sl), 0.042, 0.065)
                by_l = base - xh * (0.17 + j(0.045))
                by_r = by_l + sl + xh * self.rng.uniform(-0.04, 0.11) * jm
            else:
                vx, vy = rx, cy + j(xh * 0.04)
                arm1 = wb((lx + j(xh * 0.05), cy - open_u), (vx, vy + sl * 0.5), 0.042, 0.065)
                arm2 = wb((vx, vy + sl * 0.5), (lx + j(xh * 0.05), cy + open_d + sl), 0.042, 0.065)
                by_l = base - xh * (0.17 + j(0.045))
                by_r = by_l + sl + xh * self.rng.uniform(-0.11, 0.04) * jm
            bar = wb((lx + j(xh * 0.055), by_l), (rx + j(xh * 0.06), by_r), 0.044, 0.065)
            strokes = [arm1, arm2, bar]
        elif c in ("∴", "∵"):
            base_pts = ([(0.40, 0.82), (0.13, 0.24), (0.67, 0.24)] if c == "∴"
                        else [(0.13, 0.82), (0.67, 0.82), (0.40, 0.24)])
            rot = math.radians(j(11.0))
            cs, sn = math.cos(rot), math.sin(rot)
            sx_k, sy_k = 1.0 + j(0.12), 1.0 + j(0.12)
            for px, py in base_pts:
                dx_c, dy_c = (px - 0.40) * sx_k, (py - 0.53) * sy_k
                rx_p = 0.40 + dx_c * cs - dy_c * sn
                ry_p = 0.53 + dx_c * sn + dy_c * cs
                dot_x = x0 + xh * rx_p + j(xh * 0.07)
                dot_y = base - xh * ry_p + j(xh * 0.07)
                fl_len = xh * (0.04 + abs(j(0.04)))
                fl_ang = self.rng.uniform(0, 6.28)
                dot_pw = max(2.4, xh * 0.195 * (1.0 + j(0.11)))
                self.draw_strokes(ink, [[(dot_x, dot_y), (dot_x + fl_len * math.cos(fl_ang) + 0.5, dot_y + fl_len * math.sin(fl_ang) + 0.3)]], dot_pw)
            return DRAWN[c] * xh
        elif c == "~":
            cy = base - xh * (0.52 + j(0.04))
            wl = xh * (0.76 + j(0.06))
            amp = xh * (0.12 + self.rng.uniform(-0.025, 0.035) * jm)
            ph = self.rng.uniform(-0.34, 0.34) * jm
            sl = j(xh * 0.08)
            strokes = [[(x0 + wl * (t / 12), cy - math.sin(2 * math.pi * t / 12 + ph) * amp + sl * (t / 12) + j(xh * 0.015))
                        for t in range(13)]]
        elif c == ".":
            cx, cy = x + xh * 0.20 + j(xh * 0.025), base - xh * 0.06 + j(xh * 0.025)
            strokes = [[(cx, cy), (cx + xh * 0.03 + 0.6, cy + xh * 0.02 + 0.3)]]
            pw = max(2.2, xh * 0.21 * (1 + j(0.08)))
        elif c in ("∑", "Σ"):
            t_top = base - xh * (1.34 + j(0.04))
            b_bot = base + xh * (0.04 + j(0.03))
            sl = j(xh * 0.05)
            xr = x0 + xh * (0.96 + j(0.05))
            xm, ym = x0 + xh * (0.50 + j(0.035)), (t_top + b_bot) * 0.50 + j(xh * 0.035)
            top_bar = [(xr, t_top + sl + xh * 0.10)] + wb((xr, t_top + sl), (x0, t_top), 0.024, 0.03)
            diag1 = wb((x0, t_top), (xm, ym), 0.024, 0.03)
            diag2 = wb((xm, ym), (x0 + j(xh * 0.03), b_bot), 0.024, 0.03)
            bot_bar = wb((x0 + j(xh * 0.03), b_bot), (xr + j(xh * 0.03), b_bot + sl), 0.024, 0.03) + [(xr + j(xh * 0.03), b_bot + sl - xh * 0.08)]
            strokes = [top_bar, diag1, diag2, bot_bar]
            pw = max(2.0, xh * 0.132)
        elif c == "∏":
            t_top, b_bot = base - xh * (1.34 + j(0.04)), base + j(xh * 0.03)
            xr = x0 + xh * (0.86 + j(0.04))
            strokes = [
                wb((x0 - xh * 0.06, t_top), (xr + xh * 0.06, t_top + j(xh * 0.05)), 0.026, 0.035),
                wb((x0 + xh * 0.14, t_top), (x0 + xh * 0.14 + j(xh * 0.04), b_bot), 0.026, 0.035),
                wb((xr - xh * 0.14, t_top), (xr - xh * 0.14 + j(xh * 0.04), b_bot), 0.026, 0.035),
            ]
            pw = max(2.0, xh * 0.12)
        else:  # ←
            cy, L = base - xh * (0.55 + j(0.04)), xh * (1.68 + j(0.07))
            sl = j(xh * 0.08)
            strokes = [wb((x0 + L, cy + sl), (x0, cy), 0.038, 0.05),
                       wb((x0 + xh * (0.48 + j(0.05)), cy - xh * (0.40 + j(0.05))), (x0, cy), 0.03, 0.04),
                       wb((x0, cy), (x0 + xh * (0.48 + j(0.05)), cy + xh * (0.40 + j(0.05))), 0.03, 0.04)]
        self.draw_strokes(ink, strokes, pw)
        return DRAWN[c] * xh

    def math_box(self, src, xh, display=False):
        key = (src, round(xh, 2), display)
        if key not in self._math:
            try:
                tree = MathParser(src).expr()
                self._math[key] = MathLayout(self.src.metrics, display).lay(tree, xh)
            except Exception:  # never crash on odd LaTeX: write it as text
                self._math[key] = MathLayout(self.src.metrics, display).text(src, xh)
        return self._math[key]

    def draw_math(self, box, x, base, ink):
        for it in box.items:
            if it[0] == "pen":
                ox, oy = self.j(self.xh * 0.045), self.j(self.xh * 0.045)
                pts = [(x + px + ox, base - py + oy) for px, py in it[1]]
                if len(pts) == 2:  # fraction bars, overlines: natural hand tilt + curve
                    (ax, ay), (bx2, by2) = pts
                    pts = self._wb((ax - self.j(self.xh * 0.08), ay + self.j(self.xh * 0.035)),
                                   (bx2 + self.j(self.xh * 0.10), by2 + self.j(self.xh * 0.065)),
                                   self.xh, 0.042, 0.045)
                elif len(pts) > 2:  # sqrt radicals, hats, vector arrows: wobble every segment
                    w_pts = [pts[0]]
                    for k_p in range(len(pts) - 1):
                        p_a = w_pts[-1]
                        p_b = (pts[k_p + 1][0] + self.j(self.xh * 0.03), pts[k_p + 1][1] + self.j(self.xh * 0.035))
                        w_pts.extend(self._wb(p_a, p_b, self.xh, 0.030, 0.035)[1:])
                    pts = w_pts
                self.draw_strokes(ink, [pts], max(2.0, self.xh * it[2]))
            elif it[0] == "delim":
                dl, px, py, (dw, da, dd) = it[1], x + it[2], base - it[3], it[4]
                self.draw_delim(dl, px, py - da, py + dd, dw, ink, self.xh)
            elif it[0] == "sym":
                self.symbol(it[1], x + it[2] - it[4] * 0.0, base - it[3], ink, it[4])
            else:
                c, gx = it[1], it[4]
                m, bx, by, adv = self.src.glyph(c, gx * (1 + self.j(0.036)), self.rng)
                m = deform_glyph(m, bx, by, gx, self.mess, self.rng)
                px = x + it[2] + self.j(gx * 0.016)
                py = base - it[3] + self.j(gx * 0.028)
                self.page.stamp(ink, m, px - bx, py - by)
                if it[0] == "bb":  # blackboard bold: second stroke on the stem
                    w, a, _ = self.src.metrics(c, gx)
                    sx = px + w * (0.3 if c in "RNPBDEFHKLM" else 0.33)
                    if c == "Z":
                        pts = [(px + w * 0.72, py - a * 0.95), (px + w * 0.3, py - a * 0.05)]
                    else:
                        pts = [(sx, py - a * (0.9 if c not in "CQ" else 0.75)), (sx, py - a * (0.05 if c not in "CQ" else 0.25))]
                    self.draw_strokes(ink, [pts], gx * 0.1)

    def checkbox(self, x, base, ink, xh, done):
        s = xh * 1.3
        x0, y0 = x + self.j(1), base - s
        pts = [(x0, y0), (x0 + s + self.j(1), y0 + self.j(1)), (x0 + s, y0 + s + self.j(1)),
               (x0 + self.j(1), y0 + s), (x0, y0 - 1)]
        strokes = [pts]
        if done:
            strokes.append([(x0 + s * 0.2, y0 + s * 0.5), (x0 + s * 0.45, y0 + s * 0.85), (x0 + s * 1.15, y0 - s * 0.35)])
        self.draw_strokes(ink, strokes, xh * 0.13)
        return s + xh * 0.6

    # text
    def measure(self, chars, xh):
        if hasattr(self.src, "merge"):
            chars = self.src.merge(chars)
        w = 0
        for c, st in chars:
            if c == "\x01":
                w += xh * 2.2
            elif c == "\x02":
                w += self.math_box(st["math"], xh).w
            elif c in DRAWN:
                w += DRAWN[c] * xh
            elif c == " ":
                w += self.src.space(xh)
            else:
                w += self.src.width(c, xh)
        return w

    def write_chars(self, chars, x, base, xh, ink, line_slope):
        """Draw chars on one line, return list of placed (x0, x1, style) and new x."""
        placed = []
        x0_line = x
        prev_space, word_k, word_dy = True, 1.0, 0.0
        if hasattr(self.src, "merge"):
            chars = self.src.merge(chars)
        wave_ph = self.rng.uniform(0, 6.28)
        for c, st in chars:
            cink = st.get("ink") or ink
            if c == "\x01":
                adv = self.arrow(x, base + (x - x0_line) * line_slope, cink, xh)
                placed.append((x, x + adv, st))
                x += adv
                continue
            if c == "\x02":
                box = self.math_box(st["math"], xh)
                self.draw_math(box, x, base + (x - x0_line) * line_slope, cink)
                placed.append((x, x + box.w, st))
                x += box.w
                continue
            if c in DRAWN:
                adv = self.symbol(c, x, base + (x - x0_line) * line_slope, cink, xh)
                placed.append((x, x + adv, st))
                x += adv
                continue
            if c == " ":
                prev_space = True
                adv = self.src.space(xh) * (1 + self.j(0.22))
                placed.append((x, x + adv, st))
                x += adv
                continue
            if prev_space:
                word_k = 1 + self.j(0.05)
                word_dy = self.j(xh * 0.07)
            prev_space = False
            gx = xh * word_k * (1 + self.j(0.045))
            m, bx, by, adv = self.src.glyph(c, gx, self.rng)
            if st.get("bold"):
                sh = max(1, int(round(gx * 0.07)))
                m2 = Image.new("L", (m.width + sh, m.height), 0)
                m2.paste(m, (0, 0))
                m2 = ImageChops.lighter(m2, ImageChops.offset(m2, sh, 0))
                m = m2
            m = deform_glyph(m, bx, by, gx, self.mess, self.rng, extra_deg=-math.degrees(line_slope))
            if self.pen != "digital" and self.rng.random() < 0.5:
                m = m.point(lambda v, k=self.rng.uniform(0.88, 1.0): int(v * k))
            wave = math.sin((x - x0_line) / (xh * 9) + wave_ph) * xh * 0.09 * self.mess
            yb = base + (x - x0_line) * line_slope + word_dy + wave + self.j(xh * 0.032)
            self.page.stamp(cink, m, x - bx + self.j(xh * 0.018), yb - by)
            if c.isdigit():
                adv = max(adv + xh * 0.06, xh * 0.48)
            adv = adv * (1 + self.j(0.032 if c.isdigit() else 0.042))
            placed.append((x, x + adv, st))
            x += adv
        return placed, x

    def decorate(self, placed, base, xh, ink, line_slope, x_start):
        def spans(key):
            out, cur = [], None
            for x0, x1, st in placed:
                v = st.get(key)
                if v and cur and cur[2] == v and x0 - cur[1] < xh * 1.5:
                    cur[1] = x1
                elif v:
                    cur = [x0, x1, v, st.get("ink") or ink]
                    out.append(cur)
                else:
                    cur = None
            # trim trailing spaces
            return out

        def y_at(x, off):
            return base + (x - x_start) * line_slope + off

        hd = ImageDraw.Draw(self.page.hl)
        for x0, x1, col, _ in spans("hl"):
            top, bot = -xh * 1.25 + self.j(xh * 0.1), xh * 0.3 + self.j(xh * 0.1)
            pts = wobble_points((x0 - xh * 0.25, y_at(x0, top)), (x1 + xh * 0.2, y_at(x1, top)), xh * 0.06, self.rng)
            pts += wobble_points((x1 + xh * 0.3, y_at(x1, bot)), (x0 - xh * 0.2, y_at(x0, bot)), xh * 0.06, self.rng)
            hd.polygon(pts, fill=HIGHLIGHTS.get(col, HIGHLIGHTS["yellow"]))
        for x0, x1, _, cink in spans("ul"):
            self.draw_strokes(cink, [wobble_points((x0, y_at(x0, xh * 0.32)), (x1, y_at(x1, xh * 0.3 + self.j(1.5))),
                                                    xh * 0.06, self.rng)], xh * 0.13)
        for x0, x1, _, cink in spans("strike"):
            self.draw_strokes(cink, [wobble_points((x0 - 2, y_at(x0, -xh * 0.45)), (x1 + 2, y_at(x1, -xh * 0.5)),
                                                    xh * 0.05, self.rng)], xh * 0.13)
        for x0, x1, _, cink in spans("scratch"):
            w_sc = max(xh * 0.55, x1 - x0)
            if self.rng.random() < 0.52:
                # 2-3 quick back-and-forth pen strokes across the mistake
                s1 = wobble_points((x0 - 2, y_at(x0, -xh * 0.68)), (x1 + 3, y_at(x1, -xh * 0.56 + self.j(0.8))), xh * 0.04, self.rng)
                s2 = wobble_points((x1 + 3, y_at(x1, -xh * 0.44)), (x0 - 2, y_at(x0, -xh * 0.34 + self.j(0.8))), xh * 0.04, self.rng)
                strokes = [s1, s2]
                if self.rng.random() < 0.6:
                    strokes.append(wobble_points((x0 - 1, y_at(x0, -xh * 0.24)), (x1 + 2, y_at(x1, -xh * 0.18 + self.j(0.8))), xh * 0.04, self.rng))
                self.draw_strokes(cink, strokes, xh * 0.145)
            else:
                # Tight diagonal zig-zag scribble over the false start
                pts = []
                n_zz = max(5, min(9, int(round(w_sc / (xh * 0.28)))))
                for k in range(n_zz + 1):
                    px = x0 - 1 + (w_sc + 3) * (k / n_zz) + self.j(0.5)
                    py = y_at(px, (-xh * 0.92 if k % 2 == 0 else -xh * 0.08) + self.j(0.5))
                    pts.append((px, py))
                self.draw_strokes(cink, [pts], xh * 0.135)

    def _maybe_inject_scratch(self, words):
        """Occasionally insert a realistic crossed-out 2-3 char false start before a word/formula."""
        if not self.scratch_targets or self.page_lines < self.scratch_targets[0] or not words:
            return words
        cands = []
        for idx in range(len(words)):
            wd = words[idx]
            raw_txt = "".join(c for c, _ in wd).strip()
            # Never put a cross-out before a leading subproblem label like (a), (b), 1.
            if idx == 0 and re.match(r"^(\([a-zA-Z0-9]+\)|[0-9]+[.)]|[a-zA-Z][.)])$", raw_txt):
                continue
            alpha_chars = [c for c, _ in wd if c.isalpha()]
            has_math = any(c == "\x02" for c, _ in wd)
            if idx >= 1 and len(alpha_chars) >= 4:
                cands.append((idx, "word", "".join(alpha_chars)))
            elif has_math:
                cands.append((idx, "math", next(st["math"] for c, st in wd if c == "\x02")))
        if not cands:
            return words
        idx, kind, raw = self.rng.choice(cands)
        self.scratch_targets.pop(0)
        self.page_scratches += 1
        self._scratch_uid += 1
        uid = self._scratch_uid
        if kind == "word":
            if len(raw) >= 5 and self.rng.random() < 0.5:
                slip = raw[0] + raw[2] + raw[1]
            else:
                slip = raw[:self.rng.choice((2, 3))]
            fake = [(ch, {"scratch": uid}) for ch in slip] + [(" ", {})]
        else:
            toks = [t for t in re.findall(r"[A-Za-z0-9]+", raw) if t not in (
                "frac", "sum", "prod", "int", "sqrt", "left", "right", "text", "mathrm",
                "implies", "therefore", "because", "leq", "le", "geq", "ge", "approx", "sim", "bar", "hat"
            )]
            base_tok = toks[0][:2] if toks else self.rng.choice(["2x", "1+", "n1"])
            if len(base_tok) == 1:
                base_tok = base_tok + self.rng.choice(["2", "1", "x"])
            if raw.lstrip().startswith("=") and idx == 0:
                base_tok = "=" + base_tok[:2]
            fake = [(ch, {"scratch": uid}) for ch in base_tok] + [(" ", {})]
        return words[:idx] + [fake] + words[idx:]

    def paragraph(self, chars, x_text, xh, ink, first_prefix=None, underline_all=False, keep_lines=1, allow_scratch=False):
        """Wrap and write chars starting at x_text; prefix(x, base) draws a bullet etc."""
        words, cur = [], []
        for item in chars:
            cur.append(item)
            if item[0] == " ":
                words.append(cur)
                cur = []
        if cur:
            words.append(cur)
        glued = []
        for wd in words:
            core = "".join(c for c, _ in wd).strip()
            if glued and core and all(ch in "»:;!?)]%,." for ch in core):
                glued[-1] = glued[-1] + wd
            elif glued and core.isdigit() and len(core) == 3 and "".join(c for c, _ in glued[-1]).strip().isdigit():
                glued[-1] = glued[-1] + wd  # 10 000
            elif glued and "".join(c for c, _ in glued[-1]).strip() in ("«", "(", "["):
                glued[-1] = glued[-1] + wd
            else:
                glued.append(wd)
        words = self._maybe_inject_scratch(glued) if allow_scratch else glued
        lines, line, w = [], [], 0
        avail = self.right - x_text
        for wd in words:
            ww = self.measure([c for c in wd if c[0] != " "], xh)
            if line and w + ww > avail:
                lines.append(line)
                line, w = [], 0
            line.extend(wd)
            w += self.measure(wd, xh)
        if line:
            lines.append(line)
        for i, ln in enumerate(lines):
            while ln and ln[-1][0] == " ":
                ln = ln[:-1]
            ext_a = max([self.math_box(st["math"], xh).a for c, st in ln if c == "\x02"] or [0])
            ext_d = max([self.math_box(st["math"], xh).d for c, st in ln if c == "\x02"] or [0])
            if self.paper_kind in ("lines", "college"):
                self.snap_base()
                # Estimate x-spans and ascents of items on this line to check true 2D collision with previous line
                est_spans = []
                cx_est = x_text
                for c_it, st_it in ln:
                    if c_it == "\x02":
                        mb = self.math_box(st_it["math"], xh)
                        est_spans.append((cx_est, cx_est + mb.w, mb.a))
                        cx_est += mb.w
                    else:
                        cw = self.measure([(c_it, st_it)], xh)
                        if c_it != " ":
                            est_spans.append((cx_est, cx_est + cw, xh * 1.48))
                        cx_est += cw

                def _hits_prev(base_y):
                    if base_y - max(ext_a, xh * 1.48) < 3.5 * self.mm:
                        return True
                    for ax0, ax1, a_up in est_spans:
                        top_y = base_y - a_up
                        for bx0, bx1, b_bot in self.prev_boxes:
                            if ax0 < bx1 + xh * 0.15 and ax1 > bx0 - xh * 0.15:
                                if top_y < b_bot + xh * 0.03:
                                    return True
                    return False

                guard = 0
                while _hits_prev(self.base) and guard < 6:
                    prev_pages = len(self.pages)
                    self.next_line(1.0)
                    self.snap_base()
                    if len(self.pages) > prev_pages:
                        break
                    guard += 1
                self.ensure_room(keep_lines if i == 0 else 1)
                self.snap_base()
            else:
                up = ext_a - self.line_h * 0.78
                if up > 0:
                    if self.paper_kind == "seyes":
                        self.next_line(math.ceil(up / self.line_h))
                    else:
                        self.next_line((up + xh * 0.12) / self.line_h)
                self.ensure_room(keep_lines if i == 0 else 1)
            slope = math.tan(math.radians(self.drift * self.rng.uniform(0.6, 1.4) + self.j(0.42)))
            x = x_text + self.j(xh * 0.28) + (self.base - self.first_base) * math.tan(math.radians(self.drift * 0.25))
            if i == 0 and first_prefix:
                first_prefix(self.base)
            placed, x_end = self.write_chars(ln, x, self.base, xh, ink, slope)
            if underline_all and placed:
                for k, (a, b, st) in enumerate(placed):
                    placed[k] = (a, b, {**st, "ul": True})
            self.decorate(placed, self.base, xh, ink, slope, x)
            self.page_lines += 1
            self.ink_bottom = max(self.ink_bottom, self.base + max(ext_d, xh * 0.24))
            new_boxes = []
            cx_cur = x
            for c_it, st_it in ln:
                if c_it == "\x02":
                    mb = self.math_box(st_it["math"], xh)
                    yb_it = self.base + ((cx_cur + mb.w * 0.5) - x) * slope + mb.d
                    new_boxes.append((cx_cur, cx_cur + mb.w, yb_it))
                    cx_cur += mb.w
                else:
                    cw = self.measure([(c_it, st_it)], xh)
                    if c_it != " ":
                        yb_it = self.base + (cx_cur - x) * slope + (xh * 0.45 if c_it in "gjpqy" else xh * 0.16)
                        new_boxes.append((cx_cur, cx_cur + cw, yb_it))
                    cx_cur += cw
            self.prev_boxes = new_boxes
            if self.paper_kind not in ("lines", "college"):
                down = ext_d - self.line_h * 0.28
                if down > 0:
                    if self.paper_kind == "seyes":
                        self.next_line(math.ceil(down / self.line_h))
                    else:
                        self.next_line((down + xh * 0.12) / self.line_h)
            if i < len(lines) - 1:
                self.next_line()
                if self.paper_kind in ("lines", "college"):
                    self.snap_base()

    def render(self, blocks):
        xh = self.xh
        indent_unit = self.line_h * 0.75
        first = True
        prev = None
        for b in blocks:
            k = b["kind"]
            if k == "blank":
                if not first and prev != "blank" and self.paper_kind != "lines":
                    self.next_line(1.0 if self.paper_kind in ("seyes", "college") else 0.38)
                prev = "blank"
                continue
            if not first:
                if k in ("h1", "h2") and prev != "blank":
                    self.next_line(1.0 if self.paper_kind in ("lines", "college") else (2.0 if self.paper_kind == "seyes" else 1.25))
                else:
                    self.next_line(1.0)
                if self.paper_kind in ("lines", "college"):
                    self.snap_base()
            prev = k
            first = False
            level = b.get("level", 0)
            x = self.margin_x + level * indent_unit
            st = {}
            if k == "h1":
                if self.base > self.first_base + 1:
                    self.ensure_room(2)
                hx = xh * 1.28
                chars = parse_inline(b["text"], st)
                self.paragraph(chars, x, hx, self.ink, keep_lines=2)
                w = min(self.measure(chars, hx), self.right - x)
                y = self.base + hx * 0.28
                self.draw_strokes(self.ink, [wobble_points((x - hx * 0.05, y), (x + w + hx * 0.25, y + self.j(1.5)),
                                                           hx * 0.04, self.rng)], hx * 0.10)
            elif k == "h2":
                self.ensure_room(2)
                self.paragraph(parse_inline(b["text"], {"ink": self.accent}), x, xh * 1.14, self.accent, keep_lines=2)
            elif k == "h3":
                self.paragraph(parse_inline(b["text"], {}), x, xh * 1.06, self.ink, underline_all=True, keep_lines=2)
            elif k == "rule":
                y = self.base - xh * 0.5
                self.draw_strokes(self.ink, [wobble_points((self.margin_x, y), (self.right, y + self.j(3)),
                                                           xh * 0.08, self.rng)], xh * 0.08)
            elif k == "bullet":

                def pre(base, x=x, level=level):
                    self.bullet_mark(x, base, self.ink, xh, level)

                self.paragraph(parse_inline(b["text"], st), x + xh * (2.3 if (level == 0 and self.bullet == "arrow") else 1.7), xh, self.ink, first_prefix=pre, allow_scratch=True)
            elif k == "number":
                num = parse_inline(b["num"], {})

                def pre(base, x=x, num=num):
                    self.write_chars(num, x, base, xh, self.ink, 0)

                self.paragraph(parse_inline(b["text"], st), x + xh * 2.1, xh, self.ink, first_prefix=pre, allow_scratch=True)
            elif k == "arrow":
                def pre(base, x=x):
                    self.arrow(x, base, self.ink, xh)

                self.paragraph(parse_inline(b["text"], st), x + xh * 2.9, xh, self.ink, first_prefix=pre, allow_scratch=True)
            elif k == "important":
                ink = self.important

                def pre(base, x=x):
                    self.arrow(x, base, ink, xh)

                self.paragraph(parse_inline(b["text"], {"ink": ink}), x + xh * 2.9, xh, ink, first_prefix=pre)
            elif k == "check":
                def pre(base, x=x, done=b["done"]):
                    self.checkbox(x, base, self.ink, xh, done)

                st2 = {}
                self.paragraph(parse_inline(b["text"], st2), x + xh * 2.1, xh, self.ink, first_prefix=pre)
            elif k == "math":
                indent = xh * 1.2
                box = self.math_box(b["text"], xh * 1.02, display=True)
                avail = self.right - x - indent
                if box.w > avail:  # too wide: smaller indent, then scale the formula down to fit
                    indent = xh * 0.5
                    avail = self.right - x - indent
                    k = max(0.55, avail / box.w * 0.98)
                    box = self.math_box(b["text"], xh * 1.02 * k, display=True)
                if self.paper_kind == "seyes":
                    n = max(1, math.ceil((box.a + box.d + xh * 0.6) / self.line_h))
                    self.ensure_room(n)
                    top = self.base - self.line_h * 0.72
                    bottom = self.base + (n - 1) * self.line_h + self.line_h * 0.28
                    yb = (top + bottom) / 2 + (box.a - box.d) / 2
                    self.draw_math(box, x + indent, yb, self.ink)
                    self.page_lines += 1
                    if n > 1:
                        self.next_line(n - 1)
                elif self.paper_kind in ("lines", "college"):
                    self.snap_base()
                    guard = 0
                    while (self.base - box.a < self.ink_bottom + xh * 0.20 or self.base - box.a < 3.5 * self.mm) and guard < 6:
                        prev_pages = len(self.pages)
                        self.next_line(1.0)
                        self.snap_base()
                        if len(self.pages) > prev_pages:
                            break
                        guard += 1
                    if self.base + box.d > self.H - self.bottom_margin:
                        self.new_page()
                        while self.base - box.a < 3.5 * self.mm:
                            self.next_line(1.0)
                    self.draw_math(box, x + indent, self.base, self.ink)
                    self.page_lines += 1
                    self.ink_bottom = max(self.ink_bottom, self.base + max(box.d, xh * 0.24))
                    self.prev_boxes = [(x + indent, x + indent + box.w, self.base + box.d)]
                else:
                    need_h = box.a + box.d + xh * 0.35
                    self.ensure_room(need_h / self.line_h)
                    up_m = max(0.0, box.a - self.line_h * 0.75)
                    if up_m > 0:
                        self.base += up_m + xh * 0.10
                    self.draw_math(box, x + indent, self.base, self.ink)
                    self.page_lines += 1
                    down_m = max(0.0, box.d - self.line_h * 0.25)
                    if down_m > 0:
                        self.base += down_m + xh * 0.10
            elif k == "aside":
                self.paragraph(parse_inline(b["text"], {"ink": self.accent}), x, xh, self.accent)
            else:
                self.paragraph(parse_inline(b["text"], st), x, xh, self.ink, allow_scratch=True)
        return [p.finish() for p in self.pages]


def photoize(page, rng, mm):
    """Make a clean page look like a phone photo of a real notebook sheet."""
    W, H = page.size
    nr = np.random.default_rng(rng.randint(0, 1 << 30))
    a = np.asarray(page, dtype=np.float32)

    def noise(scale):
        h, w = max(2, H // scale + 2), max(2, W // scale + 2)
        n = Image.fromarray((nr.random((h, w)) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
        return np.asarray(n, dtype=np.float32) / 255.0 - 0.5

    # crumpled / curved sheet: height map lit from one side
    hmap = 1.0 * noise(420) + 0.25 * noise(140) + 0.05 * noise(40)
    gy, gx = np.gradient(hmap * 60)
    ang = rng.uniform(0, 6.28)
    shade = 1 + 0.09 * (np.cos(ang) * gx + np.sin(ang) * gy)
    # the sheet curls up near the binding: darker band on the left
    curl = 1 - 0.13 * np.exp(-(np.mgrid[0:H, 0:W][1].astype(np.float32) / (0.06 * W)))
    shade = shade * curl
    # uneven room light: one corner darker, vignette
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    lx, ly = rng.uniform(-0.3, 1.3), rng.uniform(-0.3, 1.3)
    dist = np.hypot(xx / W - lx, yy / H - ly)
    light = 1.06 - 0.32 * dist + 0.05 * noise(400)
    vign = 1 - 0.22 * (np.hypot(xx / W - 0.5, yy / H - 0.5) ** 2) * 2
    a = a * (shade * light * vign)[..., None]
    # phone white balance: slightly warm or slightly blue, a bit grey
    tint = np.array([rng.uniform(0.94, 1.02), rng.uniform(0.95, 1.0), rng.uniform(0.9, 1.04)], dtype=np.float32)
    a = a * tint * 0.93 + 6
    sheet = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    # punch holes on the left: real cut-outs that show the table under the sheet (no bright rim)
    r = 3 * mm
    holes = []
    for fy in (0.12, 0.5, 0.88):
        holes.append((9 * mm + rng.uniform(-2, 2), H * fy + rng.uniform(-8, 8)))
    ss = 4  # draw the cut at 4x and shrink, for a clean anti-aliased edge
    hm = Image.new("L", (W, H), 0)
    for cx, cy in holes:
        x0, y0 = int(cx - r - 4), int(cy - r - 4)
        big = Image.new("L", ((int(2 * r) + 8) * ss,) * 2, 0)
        ImageDraw.Draw(big).ellipse(((cx - r - x0) * ss, (cy - r - y0) * ss,
                                     (cx + r - x0) * ss, (cy + r - y0) * ss), fill=255)
        hm.paste(big.resize((int(2 * r) + 8,) * 2, Image.LANCZOS), (x0, y0))
    # the paper just around the cut is a little darker (thickness of the sheet, slight shadow)
    rim = np.asarray(hm.filter(ImageFilter.GaussianBlur(2.2)), dtype=np.float32) / 255.0
    sa = np.asarray(sheet, dtype=np.float32) * (1 - 0.35 * np.clip(rim * 2, 0, 1))[..., None]
    sheet = Image.fromarray(np.clip(sa, 0, 255).astype(np.uint8))
    sheet_mask = ImageChops.invert(hm)
    # place on a dark background, tilted, with perspective
    pad = int(0.07 * W)
    bgc = np.array([rng.uniform(25, 60)] * 3) + nr.normal(0, 4, 3)
    canvas = np.ones((H + 2 * pad, W + 2 * pad, 3), np.float32) * bgc
    canvas += nr.normal(0, 6, canvas.shape[:2])[..., None] + 18 * noise_like(canvas.shape[:2], nr)[..., None]
    bg = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8))
    shadow = Image.new("L", bg.size, 0)
    ImageDraw.Draw(shadow).rectangle((pad + 10, pad + 14, pad + W + 14, pad + H + 16), fill=140)
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    bg = Image.composite(Image.new("RGB", bg.size, (10, 10, 12)), bg, shadow)
    bg.paste(sheet, (pad, pad), sheet_mask)
    CW, CH = bg.size
    j = lambda k: rng.uniform(-k, k) * W
    src = [(pad, pad), (pad + W, pad), (pad + W, pad + H), (pad, pad + H)]
    dst = [(pad + j(0.035), pad + j(0.03)), (pad + W + j(0.035), pad + j(0.03)),
           (pad + W + j(0.03), pad + H + j(0.03)), (pad + j(0.03), pad + H + j(0.03))]
    photo = bg.transform(bg.size, Image.PERSPECTIVE, _perspective_coeffs(dst, src), Image.BICUBIC,
                         fillcolor=tuple(int(v) for v in bgc))
    photo = photo.rotate(rng.uniform(-2.5, 2.5), resample=Image.BICUBIC, fillcolor=tuple(int(v) for v in bgc))
    # crop a little so the page fills the frame like a phone shot
    cut = int(pad * rng.uniform(0.35, 0.75))
    photo = photo.crop((cut, cut, CW - cut, CH - cut))
    # lens softness, sensor noise, JPEG
    photo = photo.filter(ImageFilter.GaussianBlur(0.7))
    b = np.asarray(photo, dtype=np.float32) + nr.normal(0, 3.5, (photo.height, photo.width, 1))
    photo = Image.fromarray(np.clip(b, 0, 255).astype(np.uint8))
    import io
    buf = io.BytesIO()
    photo.save(buf, "JPEG", quality=int(rng.uniform(62, 78)))
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def noise_like(shape, nr):
    H, W = shape
    n = Image.fromarray((nr.random((H // 40 + 2, W // 40 + 2)) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
    return np.asarray(n, dtype=np.float32) / 255.0 - 0.5


def save_pages(pages, out):
    out = Path(out)
    if out.suffix.lower() == ".pdf":
        # Pillow 12 lazily registers Image.SAVE['JPEG']; PdfImagePlugin requires it initialized first.
        Image.init()
        pages[0].save(out, save_all=True, append_images=pages[1:], resolution=300.0, quality=95, subsampling=0)
    else:
        if len(pages) == 1:
            pages[0].save(out)
        else:
            for i, p in enumerate(pages, 1):
                p.save(out.with_name(f"{out.stem}-{i}{out.suffix}"))
    return out


# --------------------------------------------------------------------------- template + learning

TPL_W, TPL_H = 2480, 3508  # A4 @ 300 dpi
MARK, MARK_IN = 110, 110   # marker size and inset
COLS, ROWS = 8, 10
GRID_X0, GRID_Y0 = 250, 420
CELL_W = (TPL_W - 2 * GRID_X0) // COLS
CELL_H = 290
BASE_Y = 0.66   # baseline position inside a cell
XH_Y = 0.43     # x-height guide inside a cell
CHARSET = (
    list("abcdefghijklmnopqrstuvwxyz") * 2
    + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    + list("0123456789")
    + list(".,;:!?'\"-()/+=%&@$€*#<>[]")
    + list("éèêëàâçôîïùûœÉÈÀÇ")
)
PAGES_NEEDED = math.ceil(len(CHARSET) / (COLS * ROWS))


def tpl_marker_centers():
    c = MARK_IN + MARK / 2
    return [(c, c), (TPL_W - c, c), (TPL_W - c, TPL_H - c), (c, TPL_H - c)]


def tpl_bit_boxes():
    """Small squares at the top centre: [0] always filled (tells which way is up),
    [1..3] encode the page number in binary."""
    s, gap = 60, 40
    x = TPL_W / 2 - (4 * s + 3 * gap) / 2
    y = MARK_IN + MARK / 2 - s / 2
    return [(x + i * (s + gap), y, x + i * (s + gap) + s, y + s) for i in range(4)]


def make_template(out):
    label_font = ImageFont.truetype(str(find_font("patrick")), 34)
    head_font = ImageFont.truetype(str(find_font("patrick")), 46)
    pages = []
    for p in range(PAGES_NEEDED):
        img = Image.new("RGB", (TPL_W, TPL_H), "white")
        d = ImageDraw.Draw(img)
        for cx, cy in tpl_marker_centers():
            d.rectangle((cx - MARK / 2, cy - MARK / 2, cx + MARK / 2, cy + MARK / 2), fill="black")
        for i, box in enumerate(tpl_bit_boxes()):
            if i == 0 or (p + 1) >> (i - 1) & 1:
                d.rectangle(box, fill="black")
            else:
                d.rectangle(box, outline=(200, 200, 200), width=3)
        d.text((GRID_X0, 300), f"handnotes · page {p + 1}/{PAGES_NEEDED} · write each character in its box, "
                               "sitting on the dashed line, with the pen you use every day",
               font=head_font, fill=(150, 150, 150))
        chunk = CHARSET[p * COLS * ROWS:(p + 1) * COLS * ROWS]
        for i, ch in enumerate(chunk):
            r, c = divmod(i, COLS)
            x0, y0 = GRID_X0 + c * CELL_W, GRID_Y0 + r * CELL_H
            d.rectangle((x0, y0, x0 + CELL_W, y0 + CELL_H), outline=(215, 222, 232), width=2)
            yb, yx = y0 + CELL_H * BASE_Y, y0 + CELL_H * XH_Y
            for xx in range(int(x0 + 20), int(x0 + CELL_W - 20), 24):
                d.line((xx, yb, xx + 12, yb), fill=(190, 205, 235), width=3)
                d.line((xx, yx, xx + 6, yx), fill=(225, 230, 240), width=2)
            d.text((x0 + 12, y0 + 6), ch, font=label_font, fill=(196, 202, 214))
        pages.append(img)
    out = Path(out)
    if out.suffix.lower() == ".pdf":
        pages[0].save(out, save_all=True, append_images=pages[1:], resolution=300.0)
    else:
        for i, pg in enumerate(pages, 1):
            pg.save(out.with_name(f"{out.stem}-{i}{out.suffix}"))
    return out


def _gray(img):
    return np.asarray(ImageOps.exif_transpose(img).convert("L"), dtype=np.float32)


def _find_markers(g):
    """Locate the 4 black corner squares in a grayscale photo/scan."""
    H, W = g.shape
    scale = 900 / max(H, W)
    small = np.asarray(Image.fromarray(g.astype(np.uint8)).resize((max(1, int(W * scale)), max(1, int(H * scale)))),
                       dtype=np.float32)
    h, w = small.shape
    bg = np.asarray(Image.fromarray(small.astype(np.uint8)).filter(ImageFilter.MaxFilter(15))
                    .filter(ImageFilter.GaussianBlur(20)), dtype=np.float32)
    dark = ((bg - small) > 70).astype(np.float32)
    ii = np.pad(dark.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    best = [None] * 4
    for frac in (0.022, 0.03, 0.04, 0.052, 0.065):
        s = max(3, int(frac * max(h, w)))
        if s >= min(h, w) // 3:
            continue
        fill = (ii[s:, s:] - ii[:-s, s:] - ii[s:, :-s] + ii[:-s, :-s]) / (s * s)
        # ring around the window should be light (marker is an isolated square)
        r = max(2, s // 3)
        S = s + 2 * r
        outer = (ii[S:, S:] - ii[:-S, S:] - ii[S:, :-S] + ii[:-S, :-S])
        fh, fw = outer.shape
        inner = fill[r:r + fh, r:r + fw] * s * s
        ring = (outer - inner) / (S * S - s * s)
        score = fill[r:r + fh, r:r + fw] - 1.5 * ring
        ys, xs = np.mgrid[0:fh, 0:fw]
        cx, cy = xs + r + s / 2, ys + r + s / 2
        corners = [(0, 0), (w, 0), (w, h), (0, h)]
        for k, (qx, qy) in enumerate(corners):
            quad = ((cx < w / 2) == (qx == 0)) & ((cy < h / 2) == (qy == 0))
            sc = np.where(quad, score - 0.15 * np.hypot(cx - qx, cy - qy) / max(w, h), -9)
            idx = np.unravel_index(np.argmax(sc), sc.shape)
            val = sc[idx]
            if best[k] is None or val > best[k][0]:
                best[k] = (val, cx[idx] / scale, cy[idx] / scale, s / scale)
    if any(b is None or b[0] < 0.45 for b in best):
        raise ValueError("could not find the 4 black corner squares; photograph the whole page, flat, in good light")
    # refine: centroid of dark pixels around each guess at full resolution
    pts = []
    for _, x, y, s in best:
        x0, x1 = int(max(0, x - s)), int(min(W, x + s))
        y0, y1 = int(max(0, y - s)), int(min(H, y + s))
        patch = g[y0:y1, x0:x1]
        thr = (patch.max() + patch.min()) / 2
        yy, xx = np.nonzero(patch < thr)
        pts.append((x0 + xx.mean(), y0 + yy.mean()) if len(xx) else (x, y))
    return pts


def _perspective_coeffs(dst, src):
    """Coefficients for Image.transform(PERSPECTIVE): maps output (dst) -> input (src)."""
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        B += [u, v]
    return np.linalg.solve(np.array(A, float), np.array(B, float)).tolist()


def learn(images, out_dir):
    out = Path(out_dir)
    (out / "glyphs").mkdir(parents=True, exist_ok=True)
    glyphs, seen_pages = [], set()
    for path in images:
        img = Image.open(path)
        img = ImageOps.exif_transpose(img).convert("RGB")
        g = _gray(img)
        found = _find_markers(g)
        page, flat = 0, None
        # the photo may be rotated: try the 4 ways the corners can map, keep the one
        # whose orientation square sits at the top
        for k in range(4):
            src = found[k:] + found[:k]
            coeffs = _perspective_coeffs(tpl_marker_centers(), src)
            cand = img.transform((TPL_W, TPL_H), Image.PERSPECTIVE, coeffs, Image.BICUBIC).convert("L")
            a = np.asarray(cand, dtype=np.float32)
            dark = [a[int(y0) + 12:int(y1) - 12, int(x0) + 12:int(x1) - 12].mean() < 128
                    for (x0, y0, x1, y1) in tpl_bit_boxes()]
            pg = sum(1 << (i - 1) for i in range(1, 4) if dark[i])
            if dark[0] and 1 <= pg <= PAGES_NEEDED:
                page, flat = pg, cand
                break
        if not page:
            raise ValueError(f"{path}: could not read the page number; photograph the whole page, flat")
        seen_pages.add(page)
        # flatten lighting
        bg = np.asarray(flat.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(25)), dtype=np.float32)
        # relative darkness: light printed guides (<20 % darker than the paper) vanish,
        # pen and pencil strokes (>35 %) stay, whatever the lighting
        ink = np.clip(((bg - a) / np.maximum(bg, 1) - 0.27) / 0.25, 0, 1)
        chunk = CHARSET[(page - 1) * COLS * ROWS:page * COLS * ROWS]
        for i, ch in enumerate(chunk):
            r, c = divmod(i, COLS)
            x0, y0 = GRID_X0 + c * CELL_W, GRID_Y0 + r * CELL_H
            ins = 14
            cell = ink[y0 + ins:y0 + CELL_H - ins, x0 + ins:x0 + CELL_W - ins].copy()
            cell[:50, :60] = 0  # printed label
            # drop isolated specks: keep pixels with enough ink around them
            cell[cell < 0.25] = 0
            if (cell > 0.5).sum() < 60:
                continue
            ys, xs = np.nonzero(cell > 0.35)
            cy0, cy1 = max(0, ys.min() - 4), min(cell.shape[0], ys.max() + 5)
            cx0, cx1 = max(0, xs.min() - 4), min(cell.shape[1], xs.max() + 5)
            crop = (cell[cy0:cy1, cx0:cx1] * 255).astype(np.uint8)
            baseline = CELL_H * BASE_Y - ins - cy0
            name = f"glyphs/u{ord(ch):04x}_{page}_{i}.png"
            Image.fromarray(crop).save(out / name)
            glyphs.append({"char": ch, "file": name, "baseline": float(baseline)})
    meta = {"xheight_px": CELL_H * (BASE_Y - XH_Y), "glyphs": glyphs,
            "pages_read": sorted(seen_pages), "pages_total": PAGES_NEEDED}
    (out / "hand.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    chars = sorted({g["char"] for g in glyphs})
    missing = sorted(set(CHARSET) - set(chars))
    return len(glyphs), chars, missing


# --------------------------------------------------------------------------- learning from pages already written
# 1. `segment` cuts every ink blob out of photos of real notes and draws numbered sheets.
# 2. The AI (or a person) looks at the sheets and writes labels.json: {"<page>": {"<id>": "a"}}.
#    A label can be a whole word or a letter pair ("the", "dy") when the writer joins letters.
# 3. `build-hand` turns the labelled pieces into a handwriting folder usable with --hand.

def _ink_map(img):
    """0..1 darkness of the pen relative to the local paper colour (works on blue/black/red ink)."""
    a = np.asarray(ImageOps.exif_transpose(img).convert("RGB"), dtype=np.float32)
    g = a.min(2)
    bg = np.asarray(Image.fromarray(g.astype(np.uint8)).filter(ImageFilter.MaxFilter(15))
                    .filter(ImageFilter.GaussianBlur(25)), dtype=np.float32)
    return (bg - g) / np.maximum(bg, 1)


def _remove_rules(m, L=45, thick=7):
    """Drop pixels of long thin horizontal runs (the printed lines of the notebook)."""
    H, W = m.shape
    c = np.pad(m.astype(np.int32).cumsum(1), ((0, 0), (1, 0)))
    xs = np.arange(W)
    lo, hi = np.clip(xs - L // 2, 0, W), np.clip(xs + L // 2, 0, W)
    run = (c[:, hi] - c[:, lo]) >= (hi - lo) * 0.9
    v = np.pad(m.astype(np.int32).cumsum(0), ((1, 0), (0, 0)))
    ys = np.arange(H)
    vert = v[np.clip(ys + thick + 1, 0, H), :] - v[np.clip(ys - thick, 0, H), :]
    line = m & run & (vert <= thick)
    line = line | np.roll(line, 1, 0) | np.roll(line, -1, 0)
    return m & ~line


def _components(m):
    """Connected blobs, by runs (no scipy). Returns [y0, y1, x0, x1, area, runs]."""
    H, W = m.shape
    parent = []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    prev, allruns = [], []
    for y in range(H):
        d = np.diff(np.concatenate(([0], m[y].view(np.int8), [0])))
        starts, ends = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
        cur, j = [], 0
        for s, e in zip(starts, ends):
            idx = len(parent)
            parent.append(idx)
            while j < len(prev) and prev[j][1] < s:
                j += 1
            k = j
            while k < len(prev) and prev[k][0] <= e:
                if prev[k][1] >= s - 1:
                    a, b = find(idx), find(prev[k][2])
                    if a != b:
                        parent[a] = b
                k += 1
            cur.append((s, e, idx))
            allruns.append((y, int(s), int(e), idx))
        prev = [(s - 1, e, i) for s, e, i in cur]
    comps = {}
    for y, s, e, i in allruns:
        c = comps.setdefault(find(i), [H, 0, W, 0, 0, []])
        c[0], c[1] = min(c[0], y), max(c[1], y)
        c[2], c[3] = min(c[2], s), max(c[3], e - 1)
        c[4] += e - s
        c[5].append((y, s, e))
    return list(comps.values())


def segment(images, work):
    """Cut ink pieces out of photos of real notes; write numbered sheets for labelling."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(find_font("patrick")), 22)
    sheets = []
    for pnum, path in enumerate(images, 1):
        rel = _ink_map(Image.open(path))
        m = _remove_rules(rel > 0.24)
        md = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
        alpha = np.clip((rel - 0.2) / 0.3, 0, 1)
        items = []
        for c in _components(md):
            y0, y1, x0, x1, area = c[:5]
            if area < 60 or x1 - x0 >= 200 or y1 - y0 >= 160:
                continue
            sel = np.zeros((y1 - y0 + 1, x1 - x0 + 1), bool)
            for (y, s, e) in c[5]:
                sel[y - y0, s - x0:e - x0] = True
            items.append(dict(y0=y0, y1=y1, x0=x0, x1=x1, cy=(y0 + y1) / 2,
                              a=alpha[y0:y1 + 1, x0:x1 + 1] * sel * m[y0:y1 + 1, x0:x1 + 1]))
        items.sort(key=lambda d: d["cy"])
        hs = sorted(d["y1"] - d["y0"] for d in items) or [30]
        medh = hs[len(hs) // 2]
        lines = []
        for d in items:
            if lines and abs(d["cy"] - lines[-1]["cy"]) < medh * 0.9:
                L = lines[-1]
                L["it"].append(d)
                L["cy"] = float(np.mean([e["cy"] for e in L["it"]]))
            else:
                lines.append({"cy": d["cy"], "it": [d]})
        idir = work / f"items{pnum}"
        idir.mkdir(exist_ok=True)
        meta, n = [], 0
        for li, L in enumerate(lines):
            L["it"].sort(key=lambda d: d["x0"])
            for d in L["it"]:
                Image.fromarray((d["a"] * 255).astype(np.uint8)).save(idir / f"{n}.png")
                meta.append(dict(id=n, line=li, y0=int(d["y0"]), x0=int(d["x0"]),
                                 h=int(d["y1"] - d["y0"] + 1), w=int(d["x1"] - d["x0"] + 1)))
                n += 1
        (idir / "meta.json").write_text(json.dumps(meta))
        # numbered sheets, 12 x 14 pieces each
        cell, cols, rows = 150, 12, 14
        for sh in range((n + cols * rows - 1) // (cols * rows)):
            S = Image.new("RGB", (cols * cell, rows * cell), "white")
            D = ImageDraw.Draw(S)
            for k in range(sh * cols * rows, min(n, (sh + 1) * cols * rows)):
                r, c = divmod(k - sh * cols * rows, cols)
                im = Image.open(idir / f"{k}.png")
                sc = min(1.4, (cell - 30) / max(im.width, im.height))
                im2 = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))))
                S.paste(Image.new("RGB", im2.size, (20, 30, 120)), (c * cell + 5, r * cell + 5), im2)
                D.text((c * cell + 5, r * cell + cell - 26), str(k), fill="red", font=font)
                D.rectangle((c * cell, r * cell, (c + 1) * cell - 1, (r + 1) * cell - 1), outline=(225, 225, 225))
            sp = work / f"sheet-page{pnum}-{sh + 1}.png"
            S.save(sp)
            sheets.append(sp)
    (work / "pages.json").write_text(json.dumps([str(p) for p in images]))
    return sheets


_XLET = set("acemnorsuvwxzσπ")
_ASC = set("bdfhkltABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789Σ√∈")
_DESC = set("gjpqyμ")
_PAREN = set("()[]{}|")
_OPS = set("+-=<>≤≥×")
_OPSIZE = {"=": 0.6, "-": 0.15, "+": 1.0, "<": 1.0, ">": 1.0, "≤": 1.15, "≥": 1.15, "×": 0.8}


def _cls(ch):
    if len(ch) > 1:
        return "word"
    for name, s in (("x", _XLET), ("asc", _ASC), ("desc", _DESC), ("paren", _PAREN), ("op", _OPS)):
        if ch in s:
            return name
    return "int" if ch == "∫" else "other"


def build_hand(work, labels_path, out_dir, target=50.0):
    """Labelled pieces -> handwriting folder (same format as `learn`)."""
    import statistics as st
    work, out = Path(work), Path(out_dir)
    labels = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    (out / "glyphs").mkdir(parents=True, exist_ok=True)
    recs = []
    for page, lab in labels.items():
        meta = {m["id"]: m for m in json.loads((work / f"items{page}" / "meta.json").read_text())}
        xs = [meta[int(i)]["h"] for i, c in lab.items() if _cls(c) == "x"]
        ds = [meta[int(i)]["h"] for i, c in lab.items() if len(c) == 1 and c.isdigit()]
        est = ([st.median(xs)] if len(xs) >= 3 else []) + ([0.58 * st.median(ds)] if ds else [])
        if not est:
            hs = [meta[int(i)]["h"] for i in lab]
            est = [0.55 * st.median(hs)]
        xh = sum(est) / len(est)  # this page's x-height in pixels
        for i, c in lab.items():
            if c:
                m = meta[int(i)]
                recs.append(dict(page=page, id=i, ch=c, h=m["h"], xh=xh))
    med = {}
    for k in ("x", "asc", "desc", "paren", "op", "int", "other"):
        v = [r["h"] / r["xh"] for r in recs if _cls(r["ch"]) == k]
        if v:
            med[k] = st.median(v)
    per = {}
    for r in recs:
        per.setdefault(r["ch"], []).append(r["h"] / r["xh"])
    per = {c: st.median(v) for c, v in per.items() if len(v) >= 3}
    glyphs = []
    for r in recs:
        c, k = r["ch"], _cls(r["ch"])
        ratio = r["h"] / r["xh"]
        ref = _OPSIZE.get(c) or per.get(c, med.get(k))
        if ref and k != "word":  # keep natural variation, cut the outliers
            ratio = ref * min(1.12, max(0.88, ratio / ref))
        s = ratio * target / r["h"]
        img = Image.open(work / f"items{r['page']}" / f"{r['id']}.png")
        img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
        a = np.asarray(img, dtype=np.float32)
        hi = np.percentile(a[a > 20], 80) if (a > 20).sum() > 10 else 255
        img = Image.fromarray(np.clip(a * (255.0 / max(hi, 50)), 0, 255).astype(np.uint8))  # full ink
        H = img.height
        if k == "desc" or (k == "word" and any(ch in _DESC for ch in c)):
            base = H - 0.6 * target
        elif k == "paren":
            base = H - 0.3 * target
        elif k == "op":
            base = H / 2 + 0.45 * target
        elif k == "int":
            base = H * 0.55 + 0.2 * target
        else:
            base = H
        name = f"glyphs/p{r['page']}_{r['id']}.png"
        img.save(out / name)
        glyphs.append({"char": c, "file": name, "baseline": float(base),
                       "_ink": float((np.asarray(img, dtype=np.float32) / 255).sum())})
    # drop badly cut samples: far less ink than the other samples of the same letter
    inks = {}
    for g in glyphs:
        inks.setdefault(g["char"], []).append(g["_ink"])
    glyphs = [{k: v for k, v in g.items() if k != "_ink"} for g in glyphs
              if not (len(inks[g["char"]]) >= 2 and g["_ink"] < 0.55 * st.median(inks[g["char"]]))]
    # letters never written on the pages: built from the writer's own strokes
    by = {}
    for g in glyphs:
        by.setdefault(g["char"], []).append(g)

    def load(g):
        return Image.open(out / g["file"])

    def add(ch, img, base, tag):
        name = f"glyphs/syn_{ord(ch):04x}_{tag}.png"
        img.save(out / name)
        glyphs.append({"char": ch, "file": name, "baseline": float(base), "synthetic": True})

    def twice(im, step):
        w = int(im.width * step)
        A = Image.new("L", (w + im.width, im.height), 0)
        A.paste(im, (0, 0))
        B = Image.new("L", A.size, 0)
        B.paste(im, (w, 0))
        return ImageChops.lighter(A, B)

    for n, g in enumerate(by.get("n", [])):
        im = load(g)
        if "u" not in by:
            add("u", im.rotate(180, expand=True), im.height, n)
        if "r" not in by:
            add("r", im.crop((0, 0, max(2, int(im.width * 0.58)), im.height)), im.height, n)
        if "m" not in by:
            mm = twice(im, 0.78)
            add("m", mm.resize((int(mm.width * 0.82), im.height)), im.height, n)
    for n, g in enumerate(by.get("v", [])):
        if "w" not in by:
            add("w", twice(load(g), 0.7), g["baseline"], n)
    for n, g in enumerate(by.get("X", [])):  # x: the writer's own X at x-height
        if "x" not in by:
            im = load(g)
            k = target * 1.0 / max(1, im.height)
            add("x", im.resize((max(1, int(im.width * k)), int(target))), target, n)
    for n, g in enumerate(by.get("9", [])):  # g: the writer's 9, its loop sitting on the line, tail below
        if "g" not in by:
            im = load(g)
            k = target * 1.75 / max(1, im.height)
            im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))))
            add("g", im, target * 1.0, n)
    for src_c, dst_c, fn in (("p", "q", ImageOps.mirror), ("0", "O", None), ("l", "I", None)):
        for n, g in enumerate(by.get(src_c, [])):
            if dst_c not in by:
                add(dst_c, fn(load(g)) if fn else load(g), g["baseline"], n)
    (out / "hand.json").write_text(json.dumps({"xheight_px": target, "glyphs": glyphs,
                                               "source": "photos of notes already written"},
                                              ensure_ascii=False, indent=1), encoding="utf-8")
    return glyphs


# --------------------------------------------------------------------------- CLI

DEFAULT_HAND = HERE.parent / "hands" / "my-hand"
FALLBACK_DEFAULT_HAND = HERE.parent / "hands" / "default"
STYLES = {  # what each look means when the user does not override it
    "notebook": dict(paper="squared", ink="blue", photo=True),   # phone photo of a real notebook page
    "ipad": dict(paper="lines", ink="black", photo=False),       # clean lined tablet page exported as PDF/PNG
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="notes markup -> handwritten PDF/PNG")
    r.add_argument("input", help="notes markup file (.md/.txt), or - for stdin")
    r.add_argument("-o", "--out", default="notes.pdf")
    r.add_argument("--style", default="ipad", choices=list(STYLES),
                   help="ipad: clean lined tablet page (default) · notebook: photo of a real notebook")
    r.add_argument("--paper", choices=["squared", "lines", "college", "seyes", "grid", "dots", "blank"],
                   help="default: lines for ipad, squared for notebook")
    r.add_argument("--page", default="a4", choices=list(PAGES))
    r.add_argument("--hand", default="default",
                   help="handwriting folder (from build-hand or learn); 'default' = hands/my-hand if present else hands/default; 'none' = use --font")
    r.add_argument("--font", help="use a handwriting font instead of a hand: caveat kalam patrick gochi indie playpen, or .ttf")
    r.add_argument("--ink", choices=list(INKS), help="default: black for ipad, blue for notebook")
    r.add_argument("--accent", default="black", choices=list(INKS))
    r.add_argument("--important", default="black", choices=list(INKS))
    r.add_argument("--bullet", default="arrow", choices=["arrow", "dot", "dash"])
    r.add_argument("--size", default="medium", choices=list(SIZES))
    r.add_argument("--mess", type=float, default=None, help="0.5 neat ... 1.5 rushed (default: 0.58 ipad with jitter, 1.35 notebook)")
    r.add_argument("--jitter", action=argparse.BooleanOptionalAction, default=True,
                   help="enable natural random jitter / baseline micro-drift (default: --jitter; use --no-jitter to turn off)")
    r.add_argument("--scratch", action=argparse.BooleanOptionalAction, default=True,
                   help="add 1-2 subtle crossed-out mistakes per page (default: --scratch; use --no-scratch to turn off)")
    r.add_argument("--scratch-rate", type=int, default=2,
                   help="max crossed-out mistakes per page when --scratch is enabled (default: 2)")
    r.add_argument("--seed", type=int)

    sg = sub.add_parser("segment", help="cut letters out of photos of notes already written; makes sheets to label")
    sg.add_argument("images", nargs="+")
    sg.add_argument("-o", "--out", default="hand-work")

    bh = sub.add_parser("build-hand", help="labelled pieces (labels.json) -> handwriting folder")
    bh.add_argument("work", help="folder made by segment")
    bh.add_argument("labels", help='labels.json: {"1": {"12": "a", "40": "the"}, "2": {...}}')
    bh.add_argument("-o", "--out", default="my-hand")

    t = sub.add_parser("template", help="sheet to fill by hand so the tool learns your handwriting")
    t.add_argument("-o", "--out", default="handwriting-template.pdf")

    l = sub.add_parser("learn", help="read photos/scans of the filled template")
    l.add_argument("images", nargs="+")
    l.add_argument("-o", "--out", default="my-hand")

    a = ap.parse_args(argv)
    if a.cmd == "render":
        text = sys.stdin.read() if a.input == "-" else Path(a.input).read_text(encoding="utf-8-sig")
        text = text.lstrip("\ufeff")
        style = STYLES[a.style]
        a.mess_set = a.mess is not None
        if a.mess is None:
            a.mess = 1.0
        paper = a.paper or style["paper"]
        ink = a.ink or style["ink"]
        photo = style["photo"]
        src = FontSource(find_font(a.font or "caveat"))
        for name in ("playpen", "patrick", "kalam", "caveat", "indie", "gochi"):
            fp = find_font(name)
            if Path(fp) != Path(src.path):
                src.fallbacks.append(FontSource(fp))
        src.fallbacks += [FontSource(p) for p in SYSTEM_FALLBACKS if Path(p).is_file()][:1]
        hand = None if (a.font and a.hand == "default") or a.hand == "none" else a.hand
        if hand == "default":
            if (DEFAULT_HAND / "hand.json").is_file():
                hand = DEFAULT_HAND
            elif (FALLBACK_DEFAULT_HAND / "hand.json").is_file():
                hand = FALLBACK_DEFAULT_HAND
            else:
                hand = None
        if hand:
            src = HandSource(hand, src)
            if not photo:
                src = PencilHandSource(src)  # iPad engine: separate stroke pipeline
        if not a.jitter:
            eff_mess = a.mess if a.mess_set else 0.0
            eff_drift = 0.0
        else:
            eff_mess = max(a.mess, 1.35) if photo else (a.mess if a.mess_set else 0.58)
            eff_drift = 1.3 if photo else 0.12
        rd = Renderer(src, paper=paper, page=a.page, size=a.size, ink=ink, accent=a.accent,
                      important=a.important, bullet=a.bullet, seed=a.seed,
                      mess=eff_mess,
                      drift=eff_drift,
                      pen="ballpoint" if photo else "digital",
                      scratch_rate=(a.scratch_rate if a.scratch else 0))
        pages = rd.render(parse_blocks(text))
        if photo:
            pages = [photoize(pg, rd.rng, rd.mm) for pg in pages]
        out = save_pages(pages, a.out)
        print(f"wrote {out} ({len(pages)} page{'s' if len(pages) > 1 else ''})")
    elif a.cmd == "segment":
        sheets = segment(a.images, a.out)
        print(f"{len(sheets)} sheets to label in {a.out}:")
        for sp in sheets:
            print("  ", sp)
    elif a.cmd == "build-hand":
        gl = build_hand(a.work, a.labels, a.out)
        chars = sorted({g["char"] for g in gl})
        print(f"{len(gl)} pieces, {len(chars)} characters/words -> {a.out}")
        print("have:", " ".join(chars))
        miss = [c for c in "abcdefghijklmnopqrstuvwxyz0123456789" if c not in chars]
        if miss:
            print("missing (a font stands in, accents are drawn on the plain letter):", " ".join(miss))
    elif a.cmd == "template":
        out = make_template(a.out)
        print(f"wrote {out} ({PAGES_NEEDED} pages, {len(CHARSET)} boxes)")
    elif a.cmd == "learn":
        n, chars, missing = learn(a.images, a.out)
        print(f"learned {n} glyph samples for {len(chars)} characters -> {a.out}")
        if missing:
            print("missing (a font will stand in): " + " ".join(missing))


if __name__ == "__main__":
    main()
