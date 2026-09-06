#!/usr/bin/env python3
"""Generate assets/contributions.svg from Eren9523's real GitHub contribution calendar.

Uses the GitHub GraphQL API. Auth (first match wins):
  1. GH_TOKEN / GITHUB_TOKEN (Actions provides GITHUB_TOKEN)
  2. `gh auth token` if gh CLI is available

No PAT secret is required for the owner's public contribution calendar when
the workflow runs with the default GITHUB_TOKEN in this profile repository.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USERNAME = "Eren9523"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "contributions.svg"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        months { name firstDay }
        weeks {
          contributionDays {
            date
            contributionCount
            color
          }
        }
      }
    }
  }
}
"""

# GitHub-like greens (light → dark), plus empty
LEVEL_COLORS = {
    0: "#ebedf0",
    1: "#9be9a8",
    2: "#40c463",
    3: "#30a14e",
    4: "#216e39",
}


def token() -> str:
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    try:
        out = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
        if out:
            return out
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    raise SystemExit("No GitHub token found (GH_TOKEN / GITHUB_TOKEN / gh auth token).")


def fetch_calendar(tok: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": USERNAME}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
            "User-Agent": "eren9523-profile-contributions",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"GraphQL HTTP {e.code}: {e.read().decode()[:400]}") from e
    if payload.get("errors"):
        raise SystemExit(f"GraphQL errors: {payload['errors']}")
    user = payload.get("data", {}).get("user")
    if not user:
        raise SystemExit("User Eren9523 not found via GraphQL.")
    return user["contributionsCollection"]["contributionCalendar"]


def level_for(count: int, max_count: int) -> int:
    if count <= 0:
        return 0
    if max_count <= 1:
        return 1
    # quartile buckets against observed max
    q = count / max_count
    if q <= 0.25:
        return 1
    if q <= 0.5:
        return 2
    if q <= 0.75:
        return 3
    return 4


def render(cal: dict) -> str:
    weeks = cal["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    total = cal["totalContributions"]
    max_count = max((d["contributionCount"] for d in days), default=0)

    cell = 11
    gap = 3
    left = 36
    # Leave room above the heatmap so the title and month labels do not collide.
    # Title ~y=22, month labels ~y=50, heatmap starts at top.
    top = 58
    width = left + len(weeks) * (cell + gap) + 16
    height = top + 7 * (cell + gap) + 70  # ~226–240 depending on weeks

    # month labels: first week that contains the 1st of a month (approx via firstDay)
    month_labels = []
    seen = set()
    for wi, week in enumerate(weeks):
        for day in week["contributionDays"]:
            dt = datetime.strptime(day["date"], "%Y-%m-%d")
            key = (dt.year, dt.month)
            if dt.day <= 7 and key not in seen:
                seen.add(key)
                month_labels.append((wi, dt.strftime("%b")))
                break

    dow = ["", "Mon", "", "Wed", "", "Fri", ""]
    rects = []
    for wi, week in enumerate(weeks):
        for di, day in enumerate(week["contributionDays"]):
            lv = level_for(day["contributionCount"], max_count)
            # Prefer GitHub-provided color when present & valid; else bucket color
            color = day.get("color") or LEVEL_COLORS[lv]
            if not color.startswith("#"):
                color = LEVEL_COLORS[lv]
            x = left + wi * (cell + gap)
            y = top + di * (cell + gap)
            title = f"{day['date']}: {day['contributionCount']} contribution(s)"
            rects.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" ry="2" '
                f'fill="{color}"><title>{title}</title></rect>'
            )

    months_svg = []
    for wi, label in month_labels:
        x = left + wi * (cell + gap)
        months_svg.append(
            f'<text x="{x}" y="{top - 8}" font-size="11" fill="#57606a" '
            f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">{label}</text>'
        )

    dow_svg = []
    for di, label in enumerate(dow):
        if not label:
            continue
        y = top + di * (cell + gap) + cell - 1
        dow_svg.append(
            f'<text x="4" y="{y}" font-size="10" fill="#57606a" '
            f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">{label}</text>'
        )

    legend = []
    lx = width - 16 - 5 * (cell + gap) - 70
    ly = height - 28
    legend.append(
        f'<text x="{lx}" y="{ly + cell - 1}" font-size="11" fill="#57606a" '
        f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">Less</text>'
    )
    for i in range(5):
        legend.append(
            f'<rect x="{lx + 36 + i * (cell + gap)}" y="{ly}" width="{cell}" height="{cell}" '
            f'rx="2" ry="2" fill="{LEVEL_COLORS[i]}"/>'
        )
    legend.append(
        f'<text x="{lx + 36 + 5 * (cell + gap) + 4}" y="{ly + cell - 1}" font-size="11" fill="#57606a" '
        f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">More</text>'
    )

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img"
  aria-label="GitHub contribution graph for {USERNAME}: {total} contributions in the last year">
  <rect width="100%" height="100%" rx="12" ry="12" fill="#ffffff"/>
  <text x="16" y="22" font-size="16" font-weight="600" fill="#1f2328"
    font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">
    {total} contributions in the last year
  </text>
  <text x="{width - 16}" y="22" font-size="11" fill="#8b949e" text-anchor="end"
    font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">@{USERNAME} · updated {generated}</text>
  {''.join(months_svg)}
  {''.join(dow_svg)}
  {''.join(rects)}
  {''.join(legend)}
</svg>
'''


def main() -> int:
    tok = token()
    cal = fetch_calendar(tok)
    svg = render(cal)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes, total={cal['totalContributions']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
