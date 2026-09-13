"""snk çıktısını diğer kartlarla aynı görünüme sokar: hız, renk, zemin, genişlik.

snk hız ve renk ayarı açmıyor; SVG CSS değişkenleri ve süreye göre yüzde keyframe'lerle
kurulu olduğu için süreleri ölçeklemek ve değişkenleri ezmek yeterli.
Kullanım: python3 tools/snake_card.py dist
"""
import pathlib
import re
import sys

WIDTH, PAD = 1028, 24
SPEED = 0.4  # süre çarpanı: 0.4 = 2.5 kat hızlı
THEMES = {
    # zemin kartlarla aynı; koyu temada boş hücre zeminle aynı renkteydi, bir ton açıldı
    "dark": {"bg": "#161b22", "--cs": "#ffa657", "--ce": "#21262d", "--c0": "#21262d"},
    "light": {"bg": "#f6f8fa", "--cs": "#953800"},
}


def card(svg, theme):
    t = THEMES[theme]
    svg = re.sub(r"(\d+)ms", lambda m: f"{round(int(m.group(1)) * SPEED)}ms", svg)
    for var, color in t.items():
        if var.startswith("--"):
            svg = re.sub(rf"{var}:[^;}}]+", f"{var}:{color}", svg)
    x, y, w, h = map(float, re.search(r'viewBox="([^"]+)"', svg).group(1).split())
    height = round(h * (WIDTH - 2 * PAD) / w + 2 * PAD)
    inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
    return (
        f'<svg viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{WIDTH}" height="{height}" rx="15" fill="{t["bg"]}"/>'
        f'<svg x="{PAD}" y="{PAD}" width="{WIDTH - 2 * PAD}" height="{height - 2 * PAD}" '
        f'viewBox="{x:g} {y:g} {w:g} {h:g}">{inner}</svg></svg>'
    )


if __name__ == "__main__":
    for p in pathlib.Path(sys.argv[1]).glob("*.svg"):
        p.write_text(card(p.read_text(), "dark" if "dark" in p.name else "light"))
        print("kart:", p.name)
