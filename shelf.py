"""App Store rafı (apps_*.svg) ve son yayınlar (recent_*.svg).

Veri herkese açık kaynaklardan gelir, anahtar gerekmez: iTunes Lookup API
(geliştirici kimliği) ve illustrarch RSS. Kaynak düşerse cache/ içindeki son iyi veri çizilir.
"""
import base64
import json
import math
import re
import sys
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

ROOT = Path(__file__).parent
ARTIST_ID = 1677311418
FEED_URL = "https://illustrarch.com/feed"
UA = "Mozilla/5.0 (compatible; bdurandev-profile/1.0; +https://github.com/bdurandev)"
WIDTH = 1028
PAD = 25
FONT = "ConsolasFallback,Consolas,Menlo,'DejaVu Sans Mono',monospace"
NAME_MAX = 14  # 12px yazıda ~100px, hücre ~109px

# mağaza başlığında marka adının yeri değişiyor; kural tutmayanlar ve uzunlar elle (≤14 kr)
SHORT = {
    "Bubble Diagram Maker": "Bubble Diagram",
    "Business Card Generator QR": "Business Card",
    "Closet & Outfit Organizer": "Closet",
    "Ecommerce Shipping Calculator": "Shipping Calc",
    "Expy Profit Calculator": "Expy",
    "Garage: Diecast & Hot Wheels": "Diecast Garage",
    "Habit Tracker Kit": "Habit Kit",
    "Intermittent Fasting Kit": "Fasting Kit",
    "LoveLog Days Together": "LoveLog",
    "Motivana Daily Quotes": "Motivana",
    "NFC Reader Scanner Tool": "NFC Reader",
    "Pastin Clipboard Manager": "Pastin",
    "Pomoly Focused Working": "Pomoly",
    "QR & Barcode Tool - All In One": "QR & Barcode",
    "Side Hustle Income Tracker": "Side Hustle",
    "Simplio Daily Routines": "Daily Routines",
    "Simplio Invoice Generator": "Invoice Maker",
    "Simplio Meal Reminder": "Meal Reminder",
    "Simplio Notepad - Quick Notes": "Notepad",
    "Simplio RSS Reader": "RSS Reader",
    "Simplio Shopping List Planner": "Shopping List",
    "Subly Tracker: Subscriptions": "Subly",
    "Turkiye Fuar Takvimi": "Fuar Takvimi",
    "Who Is Domain Checker": "Who Is",
}


# --- veri -----------------------------------------------------------------

def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load(name, fetch, offline=False):
    path = ROOT / "cache" / name
    if not offline:
        try:
            data = fetch()
        except Exception as e:
            print(f"{name}: kaynak okunamadı ({e}); önbellek çiziliyor", file=sys.stderr)
        else:
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
            return data
    return json.loads(path.read_text())


def short_name(title):
    """Çizim anında hesaplanır: SHORT değişince önbelleği yenilemek gerekmesin."""
    if title in SHORT:
        return SHORT[title]
    parts = [p.strip() for p in re.split(r":| - | – ", title) if p.strip()]
    return min(parts, key=lambda p: (len(p.split()), len(p)))


def fetch_apps():
    seen = {}
    for country in ("us", "tr"):
        url = f"https://itunes.apple.com/lookup?id={ARTIST_ID}&entity=software&limit=200&country={country}"
        for r in json.loads(get(url))["results"]:
            if r.get("wrapperType") == "software":
                seen.setdefault(r["trackId"], r)
    if not seen:
        raise RuntimeError("mağazada uygulama yok")
    apps = []
    for r in seen.values():
        icon = get(r["artworkUrl100"].replace("100x100bb", "120x120bb"))
        mime = "image/png" if icon[:4] == b"\x89PNG" else "image/jpeg"
        apps.append({
            "name": r["trackName"],
            "genre": r["primaryGenreName"],
            "version": r["version"],
            "released": r["currentVersionReleaseDate"][:10],
            "rating": round(r.get("averageUserRating") or 0, 2),
            "ratings": r.get("userRatingCount") or 0,
            "icon": f"{mime};base64," + base64.b64encode(icon).decode(),
        })
    # en iyi puan başta, puansızlar sonda; eşitlikte ada göre ki her gün aynı sıra çıksın
    apps.sort(key=lambda a: (-a["rating"], -a["ratings"], a["name"].lower()))
    return apps


def fetch_feed(limit=6):
    root = ElementTree.fromstring(get(FEED_URL))  # Cloudflare HTML dönerse burada düşer
    items = []
    for it in root.iter("item"):
        items.append({
            "title": it.findtext("title").strip(),
            "date": parsedate_to_datetime(it.findtext("pubDate")).strftime("%Y-%m-%d"),
        })
        if len(items) == limit:
            break
    if not items:
        raise RuntimeError("akış boş")
    return items


def app_stats(apps):
    rated = [a for a in apps if a["ratings"]]
    total = sum(a["ratings"] for a in rated)
    avg = sum(a["rating"] * a["ratings"] for a in rated) / total if total else 0
    return {"apps": len(apps), "rating": avg, "ratings": total}


# --- SVG ------------------------------------------------------------------

def fit(text, n):
    return text if len(text) <= n else text[: n - 1] + "…"


def tspans(parts):
    return "".join(
        f'<tspan class="{c}">{escape(t)}</tspan>' if c else escape(t) for t, c in parts)


def svg_open(h, c, size):
    return [
        "<?xml version='1.0' encoding='UTF-8'?>",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}px" height="{h}px" '
        f'font-family="{FONT}" font-size="{size}px">',
        "<style>",
        f".key {{fill: {c['key']};}} .value {{fill: {c['value']};}} .add {{fill: {c['add']};}}"
        f" .cc {{fill: {c['cc']};}} .muted {{fill: {c['muted']};}}",
        "text, tspan {white-space: pre;}",
        "</style>",
        f'<rect width="{WIDTH}px" height="{h}px" fill="{c["bg"]}" rx="15"/>',
    ]


def prompt(cmd):
    return [("bahattin@duran", "key"), (":", None), ("~", "value"), ("$ " + cmd, None)]


COLS, ICON, CELL_H, TOP = 9, 64, 122, 66


def render_apps(apps, themes):
    s = app_stats(apps)
    rows = math.ceil(len(apps) / COLS)
    h = TOP + rows * CELL_H + 6
    cell_w = (WIDTH - 2 * PAD) / COLS
    summary = f'{s["apps"]} apps · {s["rating"]:.1f}/5 avg · {s["ratings"]} ratings'
    for theme, c in themes.items():
        out = svg_open(h, c, 16)
        out.append(f'<defs><clipPath id="icon"><rect width="{ICON}" height="{ICON}" rx="14"/></clipPath></defs>')
        out.append(f'<text x="{PAD}" y="40" fill="{c["text"]}">{tspans(prompt("ls ~/AppStore"))}</text>')
        out.append(f'<text x="{WIDTH - PAD}" y="40" text-anchor="end" class="muted">{escape(summary)}</text>')
        for i, a in enumerate(apps):
            cx = PAD + (i % COLS) * cell_w + cell_w / 2
            y = TOP + (i // COLS) * CELL_H
            out.append(
                f'<g transform="translate({cx - ICON / 2:.1f},{y})">'
                f'<image width="{ICON}" height="{ICON}" clip-path="url(#icon)" href="data:{a["icon"]}"/>'
                f'<rect width="{ICON}" height="{ICON}" rx="14" fill="none" stroke="{c["cc"]}" stroke-opacity="0.4"/></g>')
            out.append(f'<text x="{cx:.1f}" y="{y + ICON + 20}" text-anchor="middle" font-size="12px" '
                       f'fill="{c["text"]}">{escape(fit(short_name(a["name"]), NAME_MAX))}</text>')
            if a["ratings"]:
                meta, cls = f'★ {a["rating"]:.1f} ({a["ratings"]})', "key"
            else:
                meta, cls = f'v{a["version"]}', "muted"
            out.append(f'<text x="{cx:.1f}" y="{y + ICON + 36}" text-anchor="middle" font-size="11px" '
                       f'class="{cls}">{escape(meta)}</text>')
        out += ["</svg>", ""]
        (ROOT / f"apps_{theme}.svg").write_text("\n".join(out))


def render_recent(apps, feed, themes, n=6):
    col = 54  # karakter; 14px yazıda ~8.4px, sütun ~480px
    releases = sorted(apps, key=lambda a: (a["released"], a["name"]), reverse=True)[:n]
    left = []
    for a in releases:
        ver = "v" + a["version"]
        name = fit(short_name(a["name"]), col - 7 - len(ver) - 3)
        dots = col - 7 - len(name) - len(ver) - 2
        left.append([(a["released"][5:] + "  ", "muted"), (name, "value"), (" " + "." * dots + " ", "cc"), (ver, "key")])
    right = [[(p["date"][5:] + "  ", "muted"), (fit(p["title"], col - 7), "value")] for p in feed[:n]]

    h = 70 + 22 * (n - 1) + 30
    x2 = WIDTH // 2 + 10
    for theme, c in themes.items():
        out = svg_open(h, c, 14)
        out.append(f'<line x1="{WIDTH // 2}" y1="22" x2="{WIDTH // 2}" y2="{h - 22}" stroke="{c["cc"]}" stroke-opacity="0.4"/>')
        out.append(f'<text x="{PAD}" y="40" fill="{c["text"]}">{tspans(prompt("tail ~/AppStore/releases"))}</text>')
        out.append(f'<text x="{x2}" y="40" fill="{c["text"]}">{tspans(prompt("tail illustrarch.com/feed"))}</text>')
        for x, lines in ((PAD, left), (x2, right)):
            out.append(f'<text x="{x}" y="70" fill="{c["text"]}">')
            for i, parts in enumerate(lines):
                out.append(f'<tspan x="{x}" y="{70 + i * 22}">{tspans(parts)}</tspan>')
            out.append("</text>")
        out += ["</svg>", ""]
        (ROOT / f"recent_{theme}.svg").write_text("\n".join(out))
