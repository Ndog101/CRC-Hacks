"""Draws student reviews as cards: quality and difficulty scores, course, date, details, text, tags.

The structure follows the kind of information students expect from a review site, but the
styling is our own. All reviews in the demo are fictional sample data.
"""
import html
from datetime import date

# score -> (background, text color)
def _quality_colors(q: float) -> tuple[str, str]:
    if q >= 4:
        return "#CFF3DD", "#14683F"
    if q >= 3:
        return "#FFF0C4", "#7A5600"
    return "#FFD6D6", "#9B2222"


def _pretty_date(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
        return d.strftime("%b %d, %Y").replace(" 0", " ")
    except ValueError:
        return iso


def render_reviews(reviews: list[dict]) -> str:
    cards = []
    for r in reviews:
        try:
            q, diff = float(r["quality"]), float(r["difficulty"])
        except (ValueError, KeyError):
            continue
        qbg, qfg = _quality_colors(q)
        tags = "".join(
            f"<span style='display:inline-block;background:#EEF1F6;color:#2B3440;border-radius:999px;"
            f"padding:3px 12px;margin:0 6px 6px 0;font-size:12px;font-weight:600'>{html.escape(t.strip())}</span>"
            for t in r.get("tags", "").split(";") if t.strip()
        )

        def kv(label, key):
            return f"{label}: <b>{html.escape(r.get(key, '-') or '-')}</b>"

        details = " &nbsp;·&nbsp; ".join(
            [kv("For credit", "for_credit"), kv("Attendance", "attendance"),
             kv("Would take again", "would_take_again"), kv("Grade", "grade"), kv("Textbook", "textbook")]
        )
        box = lambda label, value, bg, fg: (  # noqa: E731
            f"<div style='text-align:center;margin-bottom:10px'>"
            f"<div style='font-size:10px;font-weight:800;letter-spacing:.06em;color:#2B3440'>{label}</div>"
            f"<div style='background:{bg};color:{fg};font-size:24px;font-weight:800;border-radius:8px;"
            f"padding:6px 0;margin-top:3px'>{value:.1f}</div></div>"
        )
        cards.append(
            "<div style='display:flex;gap:16px;background:#fff;border:1px solid #E3E7EE;border-radius:14px;"
            "padding:14px 16px;margin-bottom:12px;box-shadow:0 2px 10px rgba(16,24,40,.07);font-family:sans-serif;"
            "color:#1B2430'>"
            f"<div style='width:78px;flex:none'>{box('QUALITY', q, qbg, qfg)}{box('DIFFICULTY', diff, '#E9ECF1', '#2B3440')}</div>"
            "<div style='flex:1;min-width:0'>"
            f"<div style='display:flex;justify-content:space-between;gap:8px;font-weight:700;font-size:15px'>"
            f"<span>{html.escape(r.get('course', ''))}</span>"
            f"<span style='font-size:13px;color:#5b6676;font-weight:600'>{html.escape(_pretty_date(r.get('date', '')))}</span></div>"
            f"<div style='font-size:13px;color:#3A4452;margin:6px 0 8px'>{details}</div>"
            f"<div style='font-size:15px;line-height:1.5;margin-bottom:10px'>{html.escape(r.get('review', ''))}</div>"
            f"<div>{tags}</div>"
            "<div style='font-size:11px;color:#8A93A3'>🧪 Sample review (fictional)</div>"
            "</div></div>"
        )
    return "".join(cards) or "<div style='color:#5b6676'>No reviews yet.</div>"
