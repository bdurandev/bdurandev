"""Profil kartını (dark_mode.svg / light_mode.svg) ve yan kartları üretir.

GitHub GraphQL API'den depo, commit ve satır sayılarını çeker; App Store verisini
shelf.py'den alır; ascii.txt ile birlikte SVG'lere yazar. Satır sayıları depo başına
HEAD oid'iyle cache/stats.json'da tutulur, sadece değişen depolar yeniden sayılır.

ACCESS_TOKEN: fine-grained PAT, All repositories, Contents + Metadata read-only.
Yoksa GitHub sayıları önbellekten çizilir; App Store ve akış yine güncellenir.
"""
import json
import os
import sys
import time
import urllib.request
from hashlib import sha256
from pathlib import Path
from xml.sax.saxutils import escape

import shelf

ROOT = Path(__file__).parent
CACHE = ROOT / "cache" / "stats.json"
PROFILE_REPO = "bdurandev/bdurandev"  # kendi bot commit'leri sayılmasın

WIDTH = 58  # sağ sütun, karakter
STAT_LEFT = 34

INFO = [
    ("title", "bahattin@duran"),
    ("kv", "OS", "macOS 26, iOS 26"),
    ("kv", "Uptime", "29 years"),
    ("kv", "Host", "Make It From Zero"),
    ("kv", "Kernel", "Vibecoder, iOS & Web Developer"),
    ("kv", "IDE", "Xcode 26, Claude Code"),
    ("blank",),
    ("kv", "Languages.Programming", "Swift, Python, PHP, JavaScript"),
    ("kv", "Languages.Computer", "HTML, CSS, SQL, Liquid, YAML"),
    ("kv", "Languages.Real", "Turkish, English"),
    ("blank",),
    ("kv", "Stack.iOS", "SwiftUI, HealthKit, WidgetKit, RevenueCat"),
    ("kv", "Stack.Web", "WordPress, Shopify, Next.js, Astro"),
    ("kv", "Stack.Cloud", "Cloudflare, Supabase, GitHub Actions"),
    ("kv", "Hobbies", "Airsoft, Architecture, Automation"),
    ("blank",),
    ("section", "Contact"),
    ("kv", "Web.Studio", "mk0.net"),
    ("kv", "Web.Architecture", "illustrarch.com"),
    ("kv", "Web.Airsoft", "bearairsoft.com"),
    ("blank",),
    ("section", "GitHub Stats"),
    ("stats",),
]

THEMES = {
    "dark": dict(bg="#161b22", text="#c9d1d9", key="#ffa657", value="#a5d6ff",
                 add="#3fb950", dele="#f85149", cc="#616e7f", muted="#8b949e"),
    "light": dict(bg="#f6f8fa", text="#24292f", key="#953800", value="#0a3069",
                  add="#1a7f37", dele="#cf222e", cc="#c2cfde", muted="#57606a"),
}


# --- GitHub ---------------------------------------------------------------

def gql(query, variables=None, tries=4):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    for attempt in range(tries):
        req = urllib.request.Request(
            "https://api.github.com/graphql", data=body,
            headers={"Authorization": "bearer " + os.environ["ACCESS_TOKEN"],
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
        except Exception as e:  # 502/timeout: büyük commit geçmişlerinde olur
            err = e
        else:
            if "errors" not in data:
                return data["data"]
            err = data["errors"]
        if attempt < tries - 1:
            time.sleep(2 ** attempt * 3)
    raise RuntimeError(f"GraphQL başarısız: {err}")


REPOS_Q = """
query($cursor: String) {
  viewer {
    login
    followers { totalCount }
    repositoriesContributedTo(includeUserRepositories: true,
      contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) { totalCount }
    repositories(ownerAffiliations: OWNER, first: 100, after: $cursor) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner isFork stargazerCount
        defaultBranchRef { target { ... on Commit { oid history { totalCount } } } }
      }
    }
  }
}"""

HISTORY_Q = """
query($owner: String!, $name: String!, $cursor: String, $size: Int!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
      history(first: $size, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { additions deletions }
      }
    } } }
  }
}"""

# additions/deletions istemeden bir commit ilerlemek için
SKIP_Q = """
query($owner: String!, $name: String!, $cursor: String, $size: Int!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
      history(first: $size, after: $cursor) { pageInfo { hasNextPage endCursor } }
    } } }
  }
}"""


def count_lines(name_with_owner):
    """Büyük (görselli/üretilmiş) commit'lerde GitHub 502 döner: sayfayı küçült,
    tek commit bile okunamıyorsa onu atla ve say."""
    owner, name = name_with_owner.split("/")
    add = dele = skipped = 0
    cursor, size = None, 100
    while True:
        args = {"owner": owner, "name": name, "cursor": cursor, "size": size}
        try:
            d = gql(HISTORY_Q, args, tries=2 if size > 1 else 3)
        except RuntimeError:
            if size > 1:
                size = max(1, size // 4)
                continue
            d = gql(SKIP_Q, args)
            h = d["repository"]["defaultBranchRef"]["target"]["history"]
            skipped += 1
        else:
            h = d["repository"]["defaultBranchRef"]["target"]["history"]
            for n in h["nodes"]:
                add += n["additions"] or 0
                dele += n["deletions"] or 0
            size = min(100, size * 2)
        if not h["pageInfo"]["hasNextPage"]:
            return add, dele, skipped
        cursor = h["pageInfo"]["endCursor"]


def save(data):
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


def fetch():
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    cache.setdefault("loc", {})
    repos, cursor = [], None
    while True:
        v = gql(REPOS_Q, {"cursor": cursor})["viewer"]
        page = v["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    loc, commits, stars = {}, 0, 0
    for r in repos:
        stars += r["stargazerCount"]
        name = r["nameWithOwner"]
        head = r["defaultBranchRef"] and r["defaultBranchRef"]["target"]
        if r["isFork"] or not head or name == PROFILE_REPO:
            continue
        commits += head["history"]["totalCount"]
        # depo adları gizli: önbellek ve Actions kaydı herkese açık, sadece özet yazılır
        key = sha256(name.encode()).hexdigest()
        old = cache["loc"].get(key)
        if old and old["oid"] == head["oid"]:
            loc[key] = old
            continue
        print("sayılıyor:", key[:12], file=sys.stderr, flush=True)
        a, d, skipped = count_lines(name)
        loc[key] = cache["loc"][key] = {"oid": head["oid"], "add": a, "del": d, "skipped": skipped}
        if skipped:
            print(f"  {skipped} commit okunamadı, atlandı", file=sys.stderr, flush=True)
        save(cache)  # yarıda kesilirse sayılan depolar kaybolmasın

    stats = {
        "repos": page["totalCount"],
        "contributed": v["repositoriesContributedTo"]["totalCount"],
        "stars": stars,
        "followers": v["followers"]["totalCount"],
        "commits": commits,
        "add": sum(x["add"] for x in loc.values()),
        "del": sum(x["del"] for x in loc.values()),
        "loc": loc,  # silinen depolar düşer
    }
    save(stats)
    return stats


# --- SVG ------------------------------------------------------------------
# Her satır (metin, sınıf) parçalarından oluşur; hizalama karakter sayısıyla yapılır.

def n(x):
    return f"{x:,}"


def kv(key, value, width, lead=". "):
    value = value if isinstance(value, list) else [(value, "value")]
    vlen = sum(len(t) for t, _ in value)
    dots = max(1, width - len(lead) - len(key) - 1 - 2 - vlen)
    return [(lead, "cc"), (key, "key"), (":", None), (" " + "." * dots + " ", "cc"), *value]


def rule(label):
    head = [(label, None)] if label.startswith("bahattin") else [("- " + label, None)]
    used = sum(len(t) for t, _ in head) + 1
    return head + [(" " + "-" * (WIDTH - used), "cc")]


def stats_lines(s):
    right = WIDTH - STAT_LEFT - 3
    repos = [(n(s["repos"]), "value"), (" {", None), ("Contributed", "key"),
             (": ", None), (n(s["contributed"]), "value"), ("}", None)]
    # yıldız/takipçi 0: yerine App Store'daki gerçek karşılık
    rating = [(f"{s['rating']:.1f}/5", "value"), (f" ({n(s['ratings'])})", None)] if s["ratings"] else "-"
    total = n(s["add"] - s["del"])
    loc_val = [(total, "value"), (" ( ", None), (n(s["add"]) + "++", "add"),
               (", ", None), (n(s["del"]) + "--", "dele"), (" )", None)]
    vlen = sum(len(t) for t, _ in loc_val)
    label = "Lines of Code on GitHub" if WIDTH - 2 - 24 - 2 - vlen >= 3 else "Lines of Code"
    return [
        kv("Repos", repos, STAT_LEFT) + [(" | ", "cc")] + kv("Apps", n(s["apps"]), right, lead=""),
        kv("Commits", n(s["commits"]), STAT_LEFT) + [(" | ", "cc")] + kv("Rating", rating, right, lead=""),
        kv(label, loc_val, WIDTH),
    ]


def info_lines(stats):
    out = []
    for item in INFO:
        kind = item[0]
        if kind in ("title", "section"):
            out.append(rule(item[1]))
        elif kind == "kv":
            out.append(kv(item[1], item[2], WIDTH))
        elif kind == "blank":
            out.append([(". ", "cc")])
        elif kind == "stats":
            out.extend(stats_lines(stats))
    return out


def tspans(parts):
    return "".join(
        f'<tspan class="{c}">{escape(t)}</tspan>' if c else escape(t) for t, c in parts)


def render(stats):
    ascii_lines = (ROOT / "ascii.txt").read_text().rstrip("\n").split("\n")
    info = info_lines(stats)
    rows = max(len(ascii_lines), len(info))
    cols = max(len(l) for l in ascii_lines)
    char_w = 9.6  # 0.6em; Menlo/DejaVu en geniş durum
    x2 = int(15 + cols * char_w + 20)
    w = int(x2 + WIDTH * char_w + 15)
    h = 20 * rows + 25
    for theme, c in THEMES.items():
        body = [
            "<?xml version='1.0' encoding='UTF-8'?>",
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}px" height="{h}px" '
            f'font-family="ConsolasFallback,Consolas,Menlo,\'DejaVu Sans Mono\',monospace" font-size="16px">',
            "<style>",
            "@font-face { src: local('Consolas'), local('Consolas Bold'); font-family: 'ConsolasFallback';"
            " font-display: swap; size-adjust: 109%; }",
            f".key {{fill: {c['key']};}} .value {{fill: {c['value']};}} .add {{fill: {c['add']};}}"
            f" .dele {{fill: {c['dele']};}} .cc {{fill: {c['cc']};}}",
            "text, tspan {white-space: pre;}",
            "</style>",
            f'<rect width="{w}px" height="{h}px" fill="{c["bg"]}" rx="15"/>',
            f'<text x="15" y="30" fill="{c["text"]}">',
        ]
        for i, line in enumerate(ascii_lines):
            body.append(f'<tspan x="15" y="{30 + i * 20}">{escape(line)}</tspan>')
        body.append("</text>")
        body.append(f'<text x="{x2}" y="30" fill="{c["text"]}">')
        for i, parts in enumerate(info):
            body.append(f'<tspan x="{x2}" y="{30 + i * 20}">{tspans(parts)}</tspan>')
        body += ["</text>", "</svg>", ""]
        (ROOT / f"{theme}_mode.svg").write_text("\n".join(body))


if __name__ == "__main__":
    offline = "--render-only" in sys.argv
    if os.environ.get("ACCESS_TOKEN") and not offline:
        stats = fetch()
    else:
        if not offline:
            print("ACCESS_TOKEN yok: GitHub sayıları önbellekten çiziliyor", file=sys.stderr)
        stats = json.loads(CACHE.read_text())
    apps = shelf.load("apps.json", shelf.fetch_apps, offline)
    feed = shelf.load("feed.json", shelf.fetch_feed, offline)
    stats.update(shelf.app_stats(apps))
    render(stats)
    shelf.render_apps(apps, THEMES)
    shelf.render_recent(apps, feed, THEMES)
    print(json.dumps({k: v for k, v in stats.items() if k != "loc"}))
