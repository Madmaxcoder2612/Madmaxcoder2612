"""Draw the profile stats image (assets/stats.svg) from GitHub GraphQL data.

Everything is drawn here as plain SVG. No external image service is used.

Usage:
    gh api graphql -f query="$(cat tools/query.graphql)" -f login=<user> > data.json
    python tools/make_stats.py data.json assets/stats.svg

The numbers come from GitHub's own contribution calendar. The language bar is
a share of bytes in the owner's public, non-fork repositories. It says nothing
about skill or experience.
"""

import json
import sys
from datetime import date, timedelta
from xml.sax.saxutils import escape

LEVEL_COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
LANG_COLORS = ["#5bcdec", "#3fb950", "#d29922", "#388bfd", "#f778ba", "#8b949e"]
FONT = "'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
CELL, GAP = 12, 3
# Notebook files are mostly saved output (images, tables), so their size says
# little about how much code was written.
SKIP_LANGUAGES = {"Jupyter Notebook"}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def load_days(data):
    """Flat list of (date, count, weekday, week_index) from the calendar."""
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = []
    for w, week in enumerate(cal["weeks"]):
        for d in week["contributionDays"]:
            days.append((date.fromisoformat(d["date"]), d["contributionCount"], d["weekday"], w))
    return cal["totalContributions"], days


def streaks(days, today=None):
    """Current and longest run of consecutive days with at least one contribution."""
    counts = {d: c for d, c, _, _ in days}
    if not counts:
        return 0, 0
    today = today or max(counts)
    longest = run = 0
    day = min(counts)
    while day <= max(counts):
        run = run + 1 if counts.get(day, 0) > 0 else 0
        longest = max(longest, run)
        day += timedelta(days=1)
    # The current streak may still be alive if today has no contribution yet.
    day = today if counts.get(today, 0) > 0 else today - timedelta(days=1)
    current = 0
    while counts.get(day, 0) > 0:
        current += 1
        day -= timedelta(days=1)
    return current, longest


def level(count, peak):
    if count <= 0:
        return 0
    if peak <= 4:
        return min(count, 4)
    ratio = count / peak
    return 1 if ratio <= 0.25 else 2 if ratio <= 0.5 else 3 if ratio <= 0.75 else 4


def languages(data, top=5):
    """Share of bytes per language over public, non-fork repositories."""
    sizes = {}
    for repo in data["data"]["user"]["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name in SKIP_LANGUAGES:
                continue
            sizes[name] = sizes.get(name, 0) + edge["size"]
    total = sum(sizes.values()) or 1
    ranked = sorted(sizes.items(), key=lambda kv: -kv[1])
    shown = ranked[:top]
    other = sum(s for _, s in ranked[top:])
    if other:
        shown.append(("Other", other))
    return [(name, size / total) for name, size in shown]


def tile(x, number, label):
    return (
        f'<rect x="{x}" y="58" width="270" height="62" rx="10" fill="#161b22" stroke="#30363d"/>'
        f'<text x="{x + 20}" y="94" font-size="28" font-weight="700" fill="#5bcdec">{number}</text>'
        f'<text x="{x + 20}" y="111" font-size="12" fill="#8b949e">{escape(label)}</text>'
    )


def render(data, today=None):
    total, days = load_days(data)
    current, longest = streaks(days, today)
    peak = max((c for _, c, _, _ in days), default=0)
    updated = max(d for d, _, _, _ in days).isoformat()

    parts = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 376" width="900" height="376" '
        'role="img" aria-labelledby="t">'
        '<title id="t">GitHub contributions in the last year, streaks and top languages</title>'
        '<rect width="900" height="376" rx="16" fill="#0d1117"/>'
        '<rect x="0.5" y="0.5" width="899" height="375" rx="15.5" fill="none" stroke="#30363d"/>'
        f'<g font-family="{FONT}">'
    )
    parts.append('<text x="30" y="38" font-size="15" font-weight="700" fill="#e6edf3">Contributions, last 12 months</text>')
    parts.append(f'<text x="870" y="38" font-size="11" text-anchor="end" fill="#8b949e">updated {updated}</text>')
    parts.append(tile(30, total, "contributions in the last year"))
    parts.append(tile(315, current, "day current streak"))
    parts.append(tile(600, longest, "day longest streak"))

    # heatmap
    x0, y0 = 62, 164
    for label, weekday in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
        parts.append(
            f'<text x="{x0 - 8}" y="{y0 + weekday * (CELL + GAP) + CELL - 2}" font-size="10" '
            f'text-anchor="end" fill="#8b949e">{label}</text>'
        )
    seen_month = None
    for d, count, weekday, week in days:
        cx = x0 + week * (CELL + GAP)
        cy = y0 + weekday * (CELL + GAP)
        if weekday == 0 and d.month != seen_month:
            seen_month = d.month
            parts.append(f'<text x="{cx}" y="{y0 - 8}" font-size="10" fill="#8b949e">{MONTHS[d.month - 1]}</text>')
        parts.append(
            f'<rect x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" rx="2" '
            f'fill="{LEVEL_COLORS[level(count, peak)]}"><title>{d.isoformat()}: {count}</title></rect>'
        )

    # language bar
    langs = languages(data)
    bar_x, bar_w, bar_y = 30, 840, 316
    parts.append(f'<text x="30" y="304" font-size="12" font-weight="700" fill="#e6edf3">Languages in public repos (by code size)</text>')
    parts.append(f'<clipPath id="bar"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">')
    cursor = bar_x
    for i, (name, share) in enumerate(langs):
        w = bar_w * share
        parts.append(f'<rect x="{cursor:.1f}" y="{bar_y}" width="{w:.1f}" height="10" fill="{LANG_COLORS[i % len(LANG_COLORS)]}"/>')
        cursor += w
    parts.append("</g>")
    lx = 30
    for i, (name, share) in enumerate(langs):
        text = f"{name} {share * 100:.0f}%"
        parts.append(f'<circle cx="{lx + 5}" cy="349" r="4.5" fill="{LANG_COLORS[i % len(LANG_COLORS)]}"/>')
        parts.append(f'<text x="{lx + 15}" y="353" font-size="11.5" fill="#c9d1d9">{escape(text)}</text>')
        lx += 15 + len(text) * 6.6 + 18
    parts.append("</g></svg>")
    return "".join(parts)


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        data = json.load(f)
    svg = render(data)
    with open(argv[2], "w", encoding="utf-8") as f:
        f.write(svg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
