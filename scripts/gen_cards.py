#!/usr/bin/env python3
"""生成 GitHub 个人主页用的静态 SVG 卡片。

数据来自 GitHub GraphQL API，产物写入 assets/，README 用相对路径引用。
不依赖任何第三方图片服务，避免公共实例限流导致主页裂图。
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

LOGIN = os.environ.get("GH_LOGIN", "qiaozhi-4")

# Tokyo Night
BG = "#1a1b27"
BORDER = "#2f334d"
TEXT = "#c0caf5"
MUTED = "#565f89"
ACCENT = "#7aa2f7"

FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',"
    "'Hiragino Sans GB','Microsoft YaHei',sans-serif"
)

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    login
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      nodes {
        name
        stargazerCount
        pushedAt
        primaryLanguage { name color }
      }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount } }
      }
    }
  }
}
"""


# ---------- 取数 ----------

def get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        raise SystemExit("缺少 GITHUB_TOKEN，且 gh CLI 不可用或未登录")


def fetch(token: str) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-card-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise SystemExit(f"GraphQL 报错：{payload['errors']}")
    return payload["data"]["user"]


def streaks(weeks: list[dict]) -> tuple[int, int]:
    """返回 (当前连续天数, 最长连续天数)。今天还没提交不算断签。"""
    days = [d["contributionCount"] for week in weeks for d in week["contributionDays"]]

    longest = run = 0
    for count in days:
        run = run + 1 if count > 0 else 0
        longest = max(longest, run)

    idx = len(days) - 1
    if idx >= 0 and days[idx] == 0:
        idx -= 1
    current = 0
    while idx >= 0 and days[idx] > 0:
        current += 1
        idx -= 1
    return current, longest


# ---------- 排版工具 ----------

# ---------- 排版工具 ----------

NARROW = set("iljItf.,:;'|!()[]")
WIDE = set("mwMW@%")


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def text_w(s: str, size: float, bold: bool = False) -> float:
    total = 0.0
    for ch in s:
        if ord(ch) > 0x2E80:
            total += size
        elif ch in NARROW:
            total += size * 0.33
        elif ch in WIDE:
            total += size * 0.85
        else:
            total += size * 0.56
    return total * (1.05 if bold else 1.0)


def clip(s: str, limit: float, size: float, bold: bool = False) -> str:
    if text_w(s, size, bold) <= limit:
        return s
    out = s
    while out and text_w(out + "…", size, bold) > limit:
        out = out[:-1]
    return out.rstrip() + "…"


def fmt(n: int) -> str:
    return f"{n:,}"


def shell(w: int, h: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{FONT}">'
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="8" '
        f'fill="{BG}" stroke="{BORDER}"/>'
        f"{body}</svg>"
    )


def heading(label: str, w: int, note: str = "") -> str:
    parts = [
        f'<text x="24" y="34" font-size="14" font-weight="700" fill="{ACCENT}">'
        f"{esc(label)}</text>",
        f'<line x1="24" y1="46" x2="{w - 24}" y2="46" stroke="{BORDER}"/>',
    ]
    if note:
        parts.append(
            f'<text x="{w - 24}" y="34" font-size="11" fill="{MUTED}" '
            f'text-anchor="end">{esc(note)}</text>'
        )
    return "".join(parts)


# ---------- 卡片 ----------

def render_banner() -> str:
    w, h = 880, 190
    cx = w / 2
    body = (
        "<defs>"
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{BG}"/>'
        f'<stop offset="1" stop-color="{BORDER}"/>'
        "</linearGradient>"
        "</defs>"
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="12" '
        'fill="url(#bg)" stroke="' + BORDER + '"/>'
        f'<text x="{cx}" y="86" text-anchor="middle" font-size="60" font-weight="700" '
        f'fill="{ACCENT}" letter-spacing="1">George</text>'
        f'<rect x="{cx - 28}" y="104" width="56" height="3" rx="1.5" '
        f'fill="{ACCENT}" opacity="0.55"/>'
        f'<text x="{cx}" y="136" text-anchor="middle" font-size="15" fill="{MUTED}">'
        "Java Backend · Spring Boot · Vue</text>"
        f'<text x="{cx}" y="162" text-anchor="middle" font-size="13" fill="{MUTED}">'
        "热爱编程，把想法写成能跑的服务</text>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{FONT}">{body}</svg>'
    )


def render_stats(user: dict, stars: int, cur: int, longest: int, contrib: int) -> str:
    w, h = 420, 215
    metrics = [
        ("公开仓库", fmt(user["repositories"]["totalCount"])),
        ("获得 Star", fmt(stars)),
        ("关注者", fmt(user["followers"]["totalCount"])),
        ("近一年贡献", fmt(contrib)),
        ("当前连续", f"{cur} 天"),
        ("最长连续", f"{longest} 天"),
    ]
    body = [heading("GitHub 统计", w)]
    col = (w - 48) / 3
    for i, (label, value) in enumerate(metrics):
        x = 24 + col * (i % 3)
        y = 96 if i < 3 else 160
        body.append(
            f'<text x="{x:.0f}" y="{y}" font-size="22" font-weight="700" '
            f'fill="{TEXT}">{esc(value)}</text>'
        )
        body.append(
            f'<text x="{x:.0f}" y="{y + 18}" font-size="11" fill="{MUTED}">'
            f"{esc(label)}</text>"
        )
    return shell(w, h, "".join(body))


def render_recent(repos: list[dict]) -> str:
    w, h = 420, 215
    body = [heading("最近更新", w, f"共 {len(repos)} 个仓库")]
    y = 76
    for repo in repos[:5]:
        color = (repo.get("primaryLanguage") or {}).get("color") or MUTED
        stamp = repo["pushedAt"][:10]
        limit = (w - 24) - 44 - text_w(stamp, 11) - 8
        body.append(f'<circle cx="30" cy="{y - 4}" r="4" fill="{color}"/>')
        body.append(
            f'<text x="44" y="{y}" font-size="12" fill="{TEXT}">'
            f'{esc(clip(repo["name"], limit, 12))}</text>'
        )
        body.append(
            f'<text x="{w - 24}" y="{y}" font-size="11" fill="{MUTED}" '
            f'text-anchor="end">{stamp}</text>'
        )
        y += 28
    return shell(w, h, "".join(body))


# ---------- 主流程 ----------

def main() -> None:
    token = get_token()
    user = fetch(token)

    repos = user["repositories"]["nodes"]

    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    contrib = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    current, longest = streaks(weeks)
    stars = sum(repo["stargazerCount"] for repo in repos)

    if not ASSETS.exists():
        ASSETS.mkdir(parents=True)
    outputs = {
        "banner.svg": render_banner(),
        "stats.svg": render_stats(user, stars, current, longest, contrib),
        "recent.svg": render_recent([r for r in repos if r["name"] != LOGIN]),
    }

    for filename, content in outputs.items():
        (ASSETS / filename).write_text(content, encoding="utf-8")
        print(f"写入 assets/{filename}（{len(content)} 字节）")


if __name__ == "__main__":
    main()
