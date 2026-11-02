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
FEATURED = ["skill-forge", "GameBox-Release", "monitor-kvm-switch", "script-store"]

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
        description
        stargazerCount
        forkCount
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


def render_activity(weeks: list[dict], total: int) -> str:
    w, h = 860, 205
    cell, gap = 12, 3
    levels = ["#1f2335", "#0e4429", "#006d32", "#26a641", "#39d353"]
    body = [heading("近一年贡献", w, f"共 {fmt(total)} 次")]

    x0, y0 = 24, 62
    for wi, week in enumerate(weeks):
        for di, day in enumerate(week["contributionDays"]):
            count = day["contributionCount"]
            level = 0 if count == 0 else 1 if count < 3 else 2 if count < 6 else 3 if count < 10 else 4
            body.append(
                f'<rect x="{x0 + wi * (cell + gap)}" y="{y0 + di * (cell + gap)}" '
                f'width="{cell}" height="{cell}" rx="2" fill="{levels[level]}"/>'
            )

    legend_y = y0 + 7 * (cell + gap) + 14
    body.append(
        f'<text x="{x0}" y="{legend_y}" font-size="11" fill="{MUTED}">少</text>'
    )
    for i, color in enumerate(levels):
        body.append(
            f'<rect x="{x0 + 22 + i * 16}" y="{legend_y - 9}" width="12" height="12" '
            f'rx="2" fill="{color}"/>'
        )
    body.append(
        f'<text x="{x0 + 22 + len(levels) * 16}" y="{legend_y}" font-size="11" '
        f'fill="{MUTED}">多</text>'
    )
    return shell(w, h, "".join(body))


STAR_PATH = (
    "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279"
    "l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 "
    "0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327"
    ".668A.75.75 0 0 1 8 .25Z"
)
FORK_PATH = (
    "M5 5.372v.878c0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75v-.878a2.25 2.25 0 "
    "1 1 1.5 0v.878a2.25 2.25 0 0 1-2.25 2.25h-1.5v2.128a2.251 2.251 0 1 1-1.5 0"
    "V8.5h-1.5A2.25 2.25 0 0 1 3.5 6.25v-.878a2.25 2.25 0 1 1 1.5 0ZM5 3.25a.75"
    ".75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Zm6.75.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 "
    "0 1.5Zm-3 8.75a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z"
)


def render_repo(repo: dict) -> str:
    w, h = 420, 96
    lang = repo.get("primaryLanguage") or {}
    desc = repo.get("description") or "暂无描述"

    body = [
        f'<text x="20" y="32" font-size="15" font-weight="700" fill="{ACCENT}">'
        f'{esc(clip(repo["name"], w - 40, 15, True))}</text>',
        f'<text x="20" y="56" font-size="11" fill="{MUTED}">'
        f"{esc(clip(desc, w - 40, 11))}</text>",
    ]

    foot_y = h - 18
    if lang.get("name"):
        body.append(
            f'<circle cx="25" cy="{foot_y - 4}" r="4" fill="{lang.get("color") or MUTED}"/>'
        )
        body.append(
            f'<text x="35" y="{foot_y}" font-size="11" fill="{MUTED}">'
            f'{esc(clip(lang["name"], 150, 11))}</text>'
        )

    # 右下角：star / fork 计数，从右往左排
    cursor = w - 20
    for path, value in (
        (FORK_PATH, repo["forkCount"]),
        (STAR_PATH, repo["stargazerCount"]),
    ):
        label = str(value)
        body.append(
            f'<text x="{cursor}" y="{foot_y}" font-size="11" fill="{MUTED}" '
            f'text-anchor="end">{label}</text>'
        )
        cursor -= text_w(label, 11) + 5
        body.append(
            f'<g transform="translate({cursor - 12:.1f},{foot_y - 12}) scale(0.75)" '
            f'fill="{MUTED}"><path d="{path}"/></g>'
        )
        cursor -= 12 + 14

    return shell(w, h, "".join(body))


# ---------- 主流程 ----------

def main() -> None:
    token = get_token()
    user = fetch(token)

    repos = user["repositories"]["nodes"]
    by_name = {repo["name"]: repo for repo in repos}

    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    contrib = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    current, longest = streaks(weeks)
    stars = sum(repo["stargazerCount"] for repo in repos)

    if not ASSETS.exists():
        ASSETS.mkdir(parents=True)
    outputs = {
        "stats.svg": render_stats(user, stars, current, longest, contrib),
        "recent.svg": render_recent([r for r in repos if r["name"] != LOGIN]),
        "activity.svg": render_activity(weeks, contrib),
    }
    for name in FEATURED:
        repo = by_name.get(name)
        if repo is None:
            print(f"跳过 {name}：仓库不存在或已转为私有")
            continue
        outputs[f"repo-{name.lower()}.svg"] = render_repo(repo)

    for filename, content in outputs.items():
        (ASSETS / filename).write_text(content, encoding="utf-8")
        print(f"写入 assets/{filename}（{len(content)} 字节）")


if __name__ == "__main__":
    main()
