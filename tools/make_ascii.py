"""Fotoğraf + ön plan maskesinden ASCII portre üretir (ascii.txt).

Kullanım:
  swift tools/mask.swift foto.jpg mask.png
  python3 tools/make_ascii.py foto.jpg mask.png --preview onizleme.png

Parlaklığa göre karakter seçmek yerine her hücrenin şeklini Menlo glif bitmap'leriyle
karşılaştırır: kenarlar / \\ | _ ile, koyu alanlar (saç, gölge) yoğun gliflerle çizilir.
Kutu en/boy oranı ≈ cols*9.6 / rows*20 olmalı (SVG'de 16px yazı, 20px satır).
Yerel araç: numpy gerekir, Actions'ta çalışmaz.
"""
import argparse

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FONT = "/System/Library/Fonts/Menlo.ttc"
CELL_W, CELL_H = 10, 20
# rakamlar ve çoğu büyük harf dışarıda: portre yazı dökümü gibi durmasın
CHARS = list(" .,:;'`\"^~-_=+*!|/\\()[]{}<>ilrjtfcvnxzukmwpqdbhaogyMWNH#%&@$")
BOX = (450, 60, 1040, 758)  # bduran.gg-3037700460-20250502_104704.jpg, baş + maske


def glyph_bank(blur):
    font = ImageFont.truetype(FONT, 16)
    bank = []
    for ch in CHARS:
        im = Image.new("L", (CELL_W, CELL_H), 0)
        ImageDraw.Draw(im).text((0, 1), ch, font=font, fill=255)
        if blur:
            im = im.filter(ImageFilter.GaussianBlur(blur))
        bank.append(np.asarray(im, np.float32).ravel() / 255)
    return np.stack(bank)


def ink_map(photo, mask, box, cols, rows, gamma, edge):
    src = Image.open(photo).convert("RGB")
    size = (cols * CELL_W, rows * CELL_H)
    m = Image.open(mask).convert("L").resize(src.size).crop(box).resize(size, Image.LANCZOS)
    g = src.crop(box).convert("L").resize(size, Image.LANCZOS)
    g = ImageOps.autocontrast(g, cutoff=1, mask=m.point(lambda v: 255 if v > 127 else 0))
    mk = np.asarray(m, np.float32) / 255
    ink = (1 - np.asarray(g, np.float32) / 255) ** gamma  # koyu = mürekkep, orta ton söner
    if edge:
        e = np.asarray(g.filter(ImageFilter.GaussianBlur(1.5)).filter(ImageFilter.FIND_EDGES), np.float32)
        e = np.clip(e / max(np.percentile(e[mk > 0.5], 98), 1), 0, 1)
        ink = np.clip(ink + edge * e, 0, 1)
    return ink * mk, mk


def build(photo, mask, box=BOX, cols=44, rows=25, gamma=1.8, edge=0.6, fade=0.6,
          blur=1.0, tone=2.0, cover=0.4):
    ink, mk = ink_map(photo, mask, box, cols, rows, gamma, edge)
    if blur:
        ink = np.asarray(Image.fromarray((ink * 255).astype(np.uint8))
                         .filter(ImageFilter.GaussianBlur(blur)), np.float32) / 255
    bank = glyph_bank(blur)
    # hücreleri en yoğun glifin kaplama oranına ölçekle: tam siyah = '@' kadar mürekkep
    P = ink.reshape(rows, CELL_H, cols, CELL_W).transpose(0, 2, 1, 3).reshape(rows, cols, -1)
    P = P * bank.mean(1).max()
    if fade is not None:
        start = rows * fade
        for y in range(rows):
            if y > start:
                P[y] *= max(0.0, 1 - (y - start) / (rows - start + 2))
    P = P.reshape(rows * cols, -1)
    dist = ((P ** 2).sum(1)[:, None] - 2 * P @ bank.T + (bank ** 2).sum(1)[None, :])
    dist += tone * P.shape[1] * (P.mean(1)[:, None] - bank.mean(1)[None, :]) ** 2
    chars = np.array(CHARS)[dist.argmin(1)]
    coverage = mk.reshape(rows, CELL_H, cols, CELL_W).mean((1, 3)).ravel()
    chars[coverage < cover] = " "
    return ["".join(r).rstrip() for r in chars.reshape(rows, cols)]


def preview(lines, cols, out):
    font = ImageFont.truetype(FONT, 16)
    im = Image.new("RGB", (int(cols * 9.63) + 30, len(lines) * 20 + 30), "#161b22")
    d = ImageDraw.Draw(im)
    for i, line in enumerate(lines):
        d.text((15, 15 + i * 20), line, font=font, fill="#c9d1d9")
    im.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("photo")
    ap.add_argument("mask")
    ap.add_argument("--box", nargs=4, type=int, default=list(BOX))
    ap.add_argument("--cols", type=int, default=44)
    ap.add_argument("--rows", type=int, default=25)
    ap.add_argument("--gamma", type=float, default=1.8)
    ap.add_argument("--edge", type=float, default=0.6)
    ap.add_argument("--fade", type=float, default=0.6)
    ap.add_argument("--out", default="ascii.txt")
    ap.add_argument("--preview")
    a = ap.parse_args()
    lines = build(a.photo, a.mask, tuple(a.box), a.cols, a.rows, a.gamma, a.edge, a.fade)
    with open(a.out, "w") as f:
        f.write("\n".join(lines) + "\n")
    if a.preview:
        preview(lines, a.cols, a.preview)
