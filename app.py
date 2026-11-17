import base64
import html as html_lib
from datetime import time, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

import scheduler as sch
from ai_summary import chat_reply, summarize_reviews
from calendar_view import hour_bounds, legend_html, render_week
from data_loader import (
    load_campuses, load_catalog, load_meta, load_professors, load_reviews, load_travel,
)
from review_view import render_reviews

# Set this to False once data/ contains your real, hand-collected data.
USING_SAMPLE_DATA = True

# The official Spring 2027 class search. Students paste a class number into its search bar
# to see live seat counts. (We can't link straight to one class, so the number is shown too.)
LIVE_SEARCH_URL = "https://crc.losrios.edu/academics/search-class-schedules?strm=1273,Spring%202027&link=true"

APP_NAME = "RiverRoute"
TAGLINE = "Your professors. Your time. Your route."
# Palette (taken from the logo): navy, orange for the main action, blues for everything else
NAVY, NAVY_2, ORANGE = "#0B2A4A", "#17476F", "#F26B21"
BLUE, SKY = "#2F88E0", "#8ED0FF"
PLAN_NAMES = ["Plan A", "Plan B", "Plan C", "Plan D"]
WEEKDAYS = ["M", "T", "W", "Th", "F"]
FULL_DAY = (time(6, 0), time(22, 0))
SORT_OPTIONS = {
    "Highest rated first": ("rmp_rating", False),
    "Lowest rated first": ("rmp_rating", True),
    "Easiest first (lowest difficulty)": ("rmp_difficulty", True),
    "Hardest first": ("rmp_difficulty", False),
    "Highest 'would take again'": ("would_take_again_pct", False),
    "Most ratings": ("num_ratings", False),
}
TIER_STYLE = {  # tier -> (accent color, name, one-line meaning, light background)
    "conflict": ("#D32F2F", "⛔ Conflicts", "Can't work: overlap, impossible trip, or class and waitlist both full.", "#FDECEC"),
    "risky": ("#D9A400", "⚠️ Risky", "Might fail: tight trip, full class (waitlist), or details we can't confirm.", "#FFF6D9"),
    "heads_up": ("#1F6FD1", "ℹ️ Heads-ups", "Good to know: few seats left, same course twice, short break.", "#E8F1FD"),
}
SEAT_COLORS = {  # seat level -> (background, text)
    "open": ("#E3F4E8", "#176B35"), "few": ("#E3F4E8", "#176B35"),
    "waitlist": ("#FFF1C9", "#7A5B00"), "full": ("#FCE4E4", "#A8231B"), "unknown": ("#EEF1F6", "#4A5A6E"),
}
STATUS_LEVELS = {  # Status filter option -> seat levels it matches
    "Open seats": {"open", "few"},
    "Full · waitlist open": {"waitlist"},
    "Full · waitlist full": {"full"},
}

PRIORITIES = [  # "What matters most to me" choices (only Rio's advice uses them)
    "Best-rated professors", "Easier classes (lower difficulty)", "Fewest days on campus",
    "Shortest commutes and fewest campuses", "No early mornings", "No late evenings",
    "Classes with open seats",
]

ASSETS = Path(__file__).parent / "assets"


def data_uri(name: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode((ASSETS / name).read_bytes()).decode()


LOGO_URI, RIO_URI = data_uri("logo.svg"), data_uri("rio.svg")
RIO_AVATAR = str(ASSETS / "rio.png")

st.set_page_config(
    page_title=f"{APP_NAME} · Los Rios class planner", page_icon=str(ASSETS / "logo.png"),
    layout="wide", initial_sidebar_state="collapsed",
)

ss = st.session_state
ss.setdefault("page", "find")  # "find" or "schedule"
ss.setdefault("ai_open", False)

# ---------- Look & feel ----------
fab_icon_css = "" if ss.ai_open else (
    f".st-key-ai_fab button p::before {{content: ''; display: inline-block; width: 26px; height: 26px; "
    f"margin-right: 8px; vertical-align: middle; background: url('{RIO_URI}') center / contain no-repeat;}}"
)
hide_page = "sched" if ss.page == "find" else "find"
st.markdown(
    f"""
    <style>
      html {{font-size: 17px;}}
      header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] {{display: none !important;}}
      .block-container {{padding-top: 6.4rem; max-width: 1380px;}}
      h1, h2, h3, h4, h5 {{letter-spacing: -0.01em; color: {NAVY};}}
      a {{color: {BLUE};}}
      .block-container div[data-testid="stVerticalBlock"] {{gap: .8rem;}}
      .stButton > button {{min-height: 2.7rem; border-radius: 10px;}}

      /* Only one page is visible; the other stays loaded (so its settings are remembered) */
      .st-key-page_{hide_page},
      div[data-testid="stLayoutWrapper"]:has(> div.st-key-page_{hide_page}) {{display: none !important;}}

      /* ---- Fixed top bar ---- */
      .st-key-topbar {{position: fixed; top: 0; left: 0; right: 0; height: 96px; z-index: 1000;
                       padding: 0 max(36px, calc((100vw - 1380px) / 2 + 5rem)); display: flex; flex-direction: column; justify-content: center;
                       background: linear-gradient(90deg, {NAVY} 0%, {NAVY_2} 100%);
                       border-bottom: 3px solid {SKY}; box-shadow: 0 4px 16px rgba(0,0,0,.18);}}
      .st-key-topbar > div {{width: 100%;}}
      .st-key-topbar div[data-testid="stHorizontalBlock"] {{flex-wrap: nowrap; align-items: center; gap: .6rem;}}
      .st-key-topbar button {{background: transparent; border: 1px solid rgba(255,255,255,.38); color: #fff;
                              border-radius: 999px; font-weight: 600; min-height: 2.35rem; white-space: nowrap;}}
      .st-key-topbar button p {{color: inherit; font-size: .95rem;}}
      .st-key-topbar button:hover {{background: rgba({int(SKY[1:3], 16)},{int(SKY[3:5], 16)},{int(SKY[5:7], 16)},.22);
                                     border-color: {SKY}; color: #fff;}}
      .st-key-topbar button[data-testid="stBaseButton-primary"] {{background: #fff; border-color: #fff; color: {NAVY};}}
      .st-key-topbar .st-key-nav_ai button[data-testid^="stBaseButton"] {{background: {ORANGE}; border-color: {ORANGE}; color: #fff;}}
      .st-key-topbar .st-key-nav_ai button[data-testid^="stBaseButton"]:hover {{background: #FF7D36;}}

      /* ---- Selected chips and tabs use the logo's blue (orange is kept for "do this" buttons) ---- */
      button[data-variant="segmented_control"][data-selected="true"] {{background: {BLUE} !important;
                                                                       border-color: {BLUE} !important; color: #fff !important;}}
      button[data-variant="segmented_control"][data-selected="true"] p {{color: #fff !important;}}
      button[data-variant="segmented_control"]:hover {{border-color: {BLUE};}}
      span[data-baseweb="tag"] {{background-color: {BLUE} !important;}}

      div[data-testid="stMetric"] {{background: #FFFFFF; border-radius: 14px; padding: 12px 18px;
                                    border-left: 5px solid {BLUE}; box-shadow: 0 2px 10px rgba(16,24,40,.08);}}

      /* Course sections and class cards: soft gray fade, rounded corners, space between */
      div[data-testid="stExpander"] {{border: 1px solid #DCE2EA; border-radius: 16px; background: #FFFFFF;
                                      box-shadow: 0 3px 14px rgba(16,24,40,.08); margin-bottom: 16px;}}
      div[data-testid="stExpander"] summary {{padding: 1.35rem 1.5rem; font-size: 1.3rem; color: {NAVY};
                                              background: #EEF3F9; border-radius: 16px;}}
      div[data-testid="stExpander"] summary p {{font-size: 1.3rem;}}
      [class*="st-key-card-"] {{background: #FFFFFF; border: 1px solid #CBD3DF; border-radius: 14px;
                                box-shadow: 0 5px 20px rgba(16,24,40,.18); padding: .9rem 1rem 1rem 1.3rem;
                                margin: .5rem 0 1rem; border-left: 6px solid {NAVY};}}

      /* Tall "Add to plan" panel on the right edge of the class rows of each card */
      div[data-testid="stHorizontalBlock"]:has(> div[data-testid="stColumn"] [class*="st-key-side-"]) {{
          align-items: stretch !important;}}
      div[data-testid="stColumn"]:has([class*="st-key-side-"]) {{display: flex !important; flex-direction: column;}}
      div[data-testid="stColumn"]:has([class*="st-key-side-"]) div[data-testid="stLayoutWrapper"],
      div[data-testid="stColumn"]:has([class*="st-key-side-"]) div[data-testid="stVerticalBlock"],
      div[data-testid="stColumn"]:has([class*="st-key-side-"]) div[data-testid="stElementContainer"],
      div[data-testid="stColumn"]:has([class*="st-key-side-"]) .stButton {{
          flex: 1 1 auto; display: flex; flex-direction: column; width: 100%;}}
      [class*="st-key-side-"] {{position: relative; min-height: 7rem;}}
      [class*="st-key-side-"] button {{position: absolute; top: 0; left: 0; right: 0; bottom: 0;
                                       width: 100%; height: 100% !important; min-height: 0;
                                       border-radius: 12px; font-size: 1.1rem; font-weight: 700;
                                       white-space: normal;}}
      /* the same button turns green once the class is in the plan */
      [class*="st-key-side-"] button[data-testid="stBaseButton-secondary"] {{
          background: #1E8E5A !important; border-color: #1E8E5A !important; color: #FFFFFF !important;}}
      [class*="st-key-side-"] button[data-testid="stBaseButton-secondary"] p {{color: #FFFFFF !important;}}

      /* "What students say" bar under each card */
      [class*="st-key-rvbar-"] button {{justify-content: flex-start; text-align: left; width: 100%;
                                        background: #EFF5FC; border: 1px solid #CFE0F3; color: {NAVY};
                                        font-weight: 600; border-radius: 10px; min-height: 2.6rem;}}
      [class*="st-key-rvbar-"] button div[data-testid="stMarkdownContainer"] {{width: 100%; text-align: left;}}
      [class*="st-key-rvbar-"] button:hover {{background: #E0EEFC; border-color: {BLUE};}}
      [class*="st-key-rvbody-"] {{border-left: 3px solid {SKY}; padding-left: 1rem; margin-top: .4rem;}}

      /* Plan bar stays under the top bar while you scroll */
      div[data-testid="stLayoutWrapper"]:has(> div.st-key-planbar) {{
          position: sticky; top: 96px; z-index: 990; background: #F3F5F8;}}
      .st-key-planbar {{padding: 6px 0 8px; border-bottom: 1px solid #DCE2EA;}}

      /* Clickable problem boxes and clickable calendar classes */
      a.rr-chip, div.rr-chip {{display: flex; align-items: center; gap: 12px; background: #fff; border-radius: 14px;
                               padding: 8px 14px; border-left: 6px solid var(--c); text-decoration: none;
                               box-shadow: 0 2px 10px rgba(16,24,40,.08); font-family: sans-serif; height: 100%;
                               box-sizing: border-box; transition: background .15s, box-shadow .15s, transform .15s;}}
      a.rr-chip:hover {{background: color-mix(in srgb, var(--c) 11%, white); transform: translateY(-1px);
                        box-shadow: 0 5px 16px rgba(16,24,40,.16);}}
      .rr-chip .num {{font-size: 30px; font-weight: 800; line-height: 1; color: {NAVY};}}
      .rr-chip .ttl {{font-size: 14px; font-weight: 700; color: var(--c);}}
      .rr-chip .go {{margin-left: auto; font-size: 12px; font-weight: 700; color: var(--c); white-space: nowrap; opacity: .75;}}
      a.rr-chip:hover .go {{opacity: 1; text-decoration: underline;}}
      /* Calendar blocks: each line shows only when the block is tall enough to show it whole */
      .rr-blk {{container-type: size; overflow: hidden;}}
      .rr-blk .rr-t, .rr-blk .rr-l2, .rr-blk .rr-l3 {{overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}}
      .rr-blk .rr-l2, .rr-blk .rr-l3, .rr-blk .rr-bd {{display: none;}}
      .rr-blk .rr-ic {{font-size: .95em;}}
      /* Instant hover box for calendar classes and commute blocks (replaces the slow browser tooltip) */
      .rr-tw:hover {{z-index: 60 !important;}}
      .rr-tip {{display: none; position: absolute; top: calc(100% + 6px); width: max-content; max-width: 250px;
                background: {NAVY}; color: #fff; border: 1px solid {SKY}; border-radius: 10px; padding: 8px 12px;
                font-size: 12.5px; line-height: 1.45; box-shadow: 0 8px 24px rgba(0,0,0,.30); pointer-events: none;
                text-align: left; font-weight: 400; z-index: 70;}}
      .rr-tw:hover .rr-tip {{display: block;}}
      .rr-tl .rr-tip {{left: 0;}}
      .rr-tr .rr-tip {{right: 0;}}
      .rr-tc .rr-tip {{left: 50%; transform: translateX(-50%);}}
      .rr-up .rr-tip {{top: auto; bottom: calc(100% + 6px);}}
      .rr-tip .rr-tt {{font-weight: 700; color: {SKY}; margin-bottom: 2px;}}
      .rr-tip .rr-th {{margin-top: 6px; font-size: 11.5px; color: #BFD6EE;}}
      /* commute blocks: icon only when short, the minutes too once there is room */
      .rr-cm {{container-type: size; overflow: hidden; white-space: nowrap; display: flex; align-items: center;}}
      .rr-cm .rr-cmt {{display: none;}}
      @container (min-height: 15px) {{ .rr-cm .rr-cmt {{display: inline;}} }}
      /* narrow class blocks: name may wrap, the problem label is just an icon (the hover box explains it) */
      .rr-blk.rr-split .rr-bd {{display: none !important;}}
      .rr-blk.rr-split {{font-size: 10px !important;}}
      .rr-blk .rr-bd span {{white-space: nowrap;}}
      .rr-blk.rr-split .rr-t {{white-space: normal; line-height: 1.1;}}  /* narrow blocks: let the name wrap */
      @container (min-height: 28px) {{ .rr-blk:not(.rr-split) .rr-l2 {{display: block;}} }}
      @container (min-height: 42px) {{ .rr-blk:not(.rr-split) .rr-l3 {{display: block;}} }}
      @container (min-height: 60px) {{ .rr-blk:not(.rr-split) .rr-bd {{display: block; margin-top: 2px;}}
                                       .rr-blk:not(.rr-split) .rr-ic {{display: none;}} }}
      @container (min-height: 38px) {{ .rr-blk.rr-split .rr-l2 {{display: block;}} }}
      @container (min-height: 52px) {{ .rr-blk.rr-split .rr-l3 {{display: block;}} }}
      .rr-blk-link {{cursor: pointer; transition: filter .15s, box-shadow .15s;}}
      .rr-blk-link:hover {{filter: brightness(.94); box-shadow: 0 3px 10px rgba(0,0,0,.28);}}
      .rr-issue:target {{animation: rr-flash 1.6s ease-out;}}
      @keyframes rr-flash {{0% {{box-shadow: 0 0 0 4px {BLUE};}} 100% {{box-shadow: 0 0 0 4px transparent;}}}}

      /* Floating "Ask Rio" button and chat panel (bottom right) */
      .st-key-ai_fab {{position: fixed; bottom: 22px; right: 22px; z-index: 1002; width: auto !important;}}
      .st-key-ai_fab button {{border-radius: 999px; padding: .45rem 1.3rem .45rem 1rem; font-weight: 700;
                              box-shadow: 0 6px 18px rgba(242,107,33,.40);}}
      {fab_icon_css}
      .st-key-ai_panel {{position: fixed; bottom: 80px; right: 22px; width: min(400px, 92vw);
                         z-index: 1001; background: #FFFFFF; border: 1px solid #DDE3EC; border-radius: 16px;
                         padding: 12px 14px; box-shadow: 0 12px 34px rgba(0,0,0,.20);}}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Load data ----------
reviews = load_reviews()
campuses = load_campuses()
travel = load_travel()
meta = load_meta()
seats_as_of = meta.get("seats_as_of", "unknown")
campus_names = dict(zip(campuses["campus"], campuses["name"]))

meets = load_catalog()  # one row per class meeting
offers = sch.build_offers(meets, load_professors())  # one row per card (LEC + LAB together)

# ---------- Remembered state (survives button clicks) ----------
ss.setdefault("plans", {"Plan A": []})  # plan name -> list of offering ids
ss.setdefault("active_plan", "Plan A")
ss.setdefault("summaries", {})  # professor -> AI summary (saves free AI quota)
ss.setdefault("chat", [])  # list of {"role", "content"}
ss.setdefault("fver", 0)  # bumping this resets every filter to its default
ss.setdefault("open_rv", [])  # offerings whose "What students say" bar is open
ss.setdefault("prio_rank", [])  # "What matters most to me", in the order the student clicked them (1 = most important)
if ss.active_plan not in ss.plans:
    ss.active_plan = sorted(ss.plans)[0]


def fk(name: str) -> str:
    return f"fl_{name}_{ss.fver}"


# ---------- Button actions ----------
def go(page: str):
    if ss.page != page:
        ss.scroll_top = True  # start the new page at its top
    ss.page = page


def toggle_offer(oid: str):
    """Add the class card to the active plan, or remove it if it's already there."""
    plan = ss.plans[ss.active_plan]
    if oid in plan:
        plan.remove(oid)
    else:
        plan.append(oid)


def toggle_prio(pref: str):
    """Rank a priority next (1, 2, 3...) or remove it; the ones after it move up."""
    if pref in ss.prio_rank:
        ss.prio_rank.remove(pref)
    else:
        ss.prio_rank.append(pref)


def toggle_rv(key: str):
    if key in ss.open_rv:
        ss.open_rv.remove(key)
    else:
        ss.open_rv.append(key)


def new_plan(copy_current: bool):
    free = [n for n in PLAN_NAMES if n not in ss.plans]
    if free:
        ss.plans[free[0]] = list(ss.plans[ss.active_plan]) if copy_current else []
        ss.active_plan = free[0]


def delete_plan():
    if len(ss.plans) > 1:
        del ss.plans[ss.active_plan]
        ss.active_plan = sorted(ss.plans)[0]


def clear_plan():
    ss.plans[ss.active_plan] = []


def pick_plan():
    chosen = ss.get("plan_picker")
    if chosen in ss.plans:  # clicking the selected chip again would give None; ignore that
        ss.active_plan = chosen


def set_ai(is_open: bool):
    ss.ai_open = is_open


def ask_ai(text: str):
    ss.ai_open = True
    ss.pending_prompt = text


def clear_filters():
    ss.fver += 1


def has_rating(row) -> bool:
    return pd.notna(row["rmp_rating"])


def rating_line(row) -> str:
    if not has_rating(row):
        return "N/A · This professor has no ratings yet"
    return (
        f"⭐ {row['rmp_rating']:.1f} · difficulty {row['rmp_difficulty']:.1f} · "
        f"{int(row['would_take_again_pct'])}% would retake · {int(row['num_ratings'])} ratings"
    )


def short_rating(row) -> str:
    """One short line: rating, difficulty, would retake."""
    if not has_rating(row):
        return "N/A · no ratings yet"
    return (f"⭐ {row['rmp_rating']:.1f} · difficulty {row['rmp_difficulty']:.1f} · "
            f"{int(row['would_take_again_pct'])}% would retake")


def plan_data(name: str):
    """(meetings, offerings) for a plan, offerings in the order they were added."""
    oids = ss.plans[name]
    po = offers[offers["oid"].isin(oids)].copy()
    po["_order"] = po["oid"].map({o: i for i, o in enumerate(oids)})
    return meets[meets["oid"].isin(oids)], po.sort_values("_order")


def seat_chip(level: str, label: str) -> str:
    bg, fg = SEAT_COLORS[level]
    return (f"<span style='display:inline-block;background:{bg};color:{fg};border-radius:999px;padding:3px 11px;"
            f"font-size:14px;font-weight:600;font-family:sans-serif;line-height:1.35'>{html_lib.escape(label)}</span>")


def tier_chip(tier: str, n: int) -> str:
    """A big count box. When there are problems, it is a link that scrolls to them."""
    color, title, meaning, _bg = TIER_STYLE[tier]
    body = f"<div class='num'>{n}</div><div class='ttl'>{title}</div>"
    tip = html_lib.escape(meaning, quote=True)
    if n:
        return (f"<a class='rr-chip' href='#tier-{tier}' style='--c:{color}' title='{tip}'>{body}"
                f"<span class='go'>Show me ↓</span></a>")
    return f"<div class='rr-chip' style='--c:{color}' title='{tip}'>{body}</div>"


def stat_chip(label: str, n) -> str:
    return (f"<div class='rr-chip' style='--c:{NAVY}'><div class='num'>{n}</div>"
            f"<div class='ttl' style='color:{NAVY}'>{label}</div></div>")


def issue_card(idx: int, issue: dict, first_of_tier: bool) -> str:
    color, _t, _m, bg = TIER_STYLE[issue["tier"]]
    anchor = f"<span id='tier-{issue['tier']}' style='scroll-margin-top:185px'></span>" if first_of_tier else ""
    return (
        f"<div id='issue-{idx}' class='rr-issue' style='scroll-margin-top:185px;background:{bg};"
        f"border-left:8px solid {color};border-radius:10px;padding:10px 14px;margin:0 0 4px;color:#12263F;"
        f"font-family:sans-serif;font-size:15px;line-height:1.45'>{anchor}"
        f"<b>{html_lib.escape(sch.issue_title(issue))}</b> — {html_lib.escape(issue['text'])}</div>"
    )


# Transport: "Car", "Transit", or a per-weekday choice when "Varies by day" is selected.
if ss.get("mode_choice", "Car") == "Varies by day":
    transport = {d: ss.get(f"day_mode_{d}") or "Car" for d in WEEKDAYS}
else:
    transport = ss.get("mode_choice", "Car")
active = ss.active_plan
schedule = ss.plans[active]
required = list(ss.get("required_courses", []))  # courses the student says they must take

# =====================================================================
# TOP BAR (fixed, on every page)
# =====================================================================
with st.container(key="topbar"):
    tb = st.columns([5.2, 1.7, 1.8, 1.3], vertical_alignment="center")
    tb[0].html(
        f"<div style='display:flex;align-items:center;gap:16px;font-family:sans-serif'>"
        f"<img src='{LOGO_URI}' width='68' height='68' style='border-radius:15px;flex:none'>"
        f"<div><div style='font-size:32px;font-weight:800;color:#fff;line-height:1.05'>River"
        f"<span style='color:{ORANGE}'>Route</span></div>"
        f"<div style='font-size:15px;color:#BFD6EE;margin-top:3px'>{TAGLINE}</div></div></div>"
    )
    tb[1].button("⭐ Find professors", key="nav_find", on_click=go, args=("find",), width="stretch",
                 type="primary" if ss.page == "find" else "secondary")
    tb[2].button("📅 Build schedule", key="nav_sched", on_click=go, args=("schedule",), width="stretch",
                 type="primary" if ss.page == "schedule" else "secondary")
    tb[3].button("✨ Ask Rio", key="nav_ai", on_click=set_ai, args=(not ss.ai_open,), width="stretch",
                 type="primary")

if ss.pop("scroll_top", False):
    ss.scroll_count = ss.get("scroll_count", 0) + 1  # a new number makes the script run again
    st.html(
        "<script>/*" + str(ss.scroll_count) + "*/ var m = document.querySelector('[data-testid=\"stMain\"]'); "
        "if (m) { m.scrollTo(0, 0); }</script>",
        unsafe_allow_javascript=True,
    )

if USING_SAMPLE_DATA:
    st.html(
        "<div style='font-family:sans-serif;font-size:13px;color:#7A5B00;background:#FFF6D9;border:1px solid #F0DFA0;"
        "border-radius:8px;padding:3px 12px;display:inline-block'>🧪 <b>Demo mode:</b> fictional professors, ratings, "
        "reviews and seat counts; approximate travel times.</div>"
    )

# ---------- Plan bar (every page) ----------
plan_labels = {}
for name in sorted(ss.plans):
    pm_, po_ = plan_data(name)
    iss_ = sch.check_schedule(pm_, po_, travel, transport) if not po_.empty else []
    n = len(po_)
    health = sch.plan_health(po_, iss_)
    if health == "🟢" and sch.required_status(po_, required)[1]:
        health = "🟡"  # no problems, but still missing a course the student needs
    plan_labels[name] = f"{name} · {n} class{'es' if n != 1 else ''} {health}"

with st.container(key="planbar"):
    pb1, pb2 = st.columns([6, 1.3], vertical_alignment="center")
    with pb1:
        ss.plan_picker = active  # keep the chip in sync with the active plan
        st.segmented_control(
            "Plan", sorted(ss.plans), key="plan_picker", on_change=pick_plan,
            format_func=lambda p: plan_labels[p], label_visibility="collapsed",
        )
    with pb2.popover("⚙️ Manage plans", width="stretch"):
        st.caption(f"Working on **{active}**. New classes you add go here.")
        st.button("＋ New backup plan", on_click=new_plan, args=(False,), disabled=len(ss.plans) >= 4, width="stretch")
        st.button("📋 Duplicate this plan", on_click=new_plan, args=(True,), disabled=len(ss.plans) >= 4, width="stretch")
        st.button("🧹 Clear this plan", on_click=clear_plan, width="stretch")
        st.button("🗑 Delete this plan", on_click=delete_plan, disabled=len(ss.plans) <= 1, width="stretch")
        st.divider()
        st.multiselect(
            "📌 Courses I must take", sorted(offers["course_code"].unique()), key="required_courses",
            placeholder="Pick the courses you need",
            help="Rio and Compare use this: a plan missing a course you need is worse, even if its professors "
                 "are better. A plan with no problems but a missing course gets a yellow dot. Confirm what you "
                 "need with a counselor.",
        )
        st.markdown("**⭐ What matters most to me**")
        st.caption("Click in order of importance: the first one you click is #1. Click again to remove it "
                   "(the ones below move up).")
        for pref in PRIORITIES:
            rank = ss.prio_rank.index(pref) + 1 if pref in ss.prio_rank else None
            st.button(
                f"{rank}  ·  {pref}" if rank else pref, key=f"pref-{pref}", on_click=toggle_prio, args=(pref,),
                type="primary" if rank else "secondary", width="stretch",
            )
        st.caption("ℹ️ Only used for Rio's advice. These aren't part of any plan and don't show up in Compare.")


# =====================================================================
# PAGE 1: FIND PROFESSORS AND CLASSES
# =====================================================================
def selected(name: str, options: list) -> list:
    """Options ticked in a checkbox filter (empty list = 'All')."""
    return [o for o in options if ss.get(fk(f"{name}_o_{o}"), False)]


def check_filter(name: str, all_label: str, options: list, fmt=str) -> None:
    """A checkbox list like the CRC site: 'All ...' is ticked by default; ticking a specific
    option unticks 'All', and unticking everything puts 'All' back."""
    all_key = fk(f"{name}_all")
    ss.setdefault(all_key, True)

    def on_all():
        if ss[all_key]:
            for o in options:
                ss[fk(f"{name}_o_{o}")] = False
        else:  # 'All' can't be switched off by itself
            ss[all_key] = True

    def on_option():
        ss[all_key] = not selected(name, options)

    st.checkbox(all_label, key=all_key, on_change=on_all)
    for o in options:
        st.checkbox(fmt(o), key=fk(f"{name}_o_{o}"), on_change=on_option)


with st.container(key="page_find"):
    # ---- search box with suggestions: pick from the list, or type anything and press Enter ----
    SEARCH: dict[str, tuple[str, str]] = {}
    for r in offers.drop_duplicates("course_code").sort_values("course_code").itertuples():
        SEARCH[f"{r.course_code} · {r.course_name}"] = ("course", r.course_code)
    for p in sorted(p for p in offers["professor"].unique() if p):
        SEARCH[f"Instructor: {p}"] = ("prof", p)
    # (class numbers aren't listed as suggestions; typing one and pressing Enter still finds it)

    typed = st.selectbox(
        "Search classes", list(SEARCH), index=None, key="search_box", accept_new_options=True,
        placeholder="Search by course code or name, instructor, or class number",
    )
    query = typed or ""

    # ---- filter row (like the CRC site) ----
    campus_opts = list(campus_names)
    mode_opts = [sch.MODE_CANON[k] for k in ("in_person", "partial", "sync", "async")]
    status_opts = list(STATUS_LEVELS)
    sel_campus, sel_mode, sel_status = (
        selected("campus", campus_opts), selected("mode", mode_opts), selected("status", status_opts),
    )

    def count_tag(sel):
        return f" ({len(sel)})" if sel else ""

    t_range = ss.get(fk("time"), FULL_DAY)
    when_active = (t_range != FULL_DAY) + (len(ss.get(fk("days"), [])) > 0) + (not ss.get(fk("async"), True))
    min_val = ss.get(fk("min"), 0.0)
    sort_name = ss.get(fk("sort"), list(SORT_OPTIONS)[0])

    f = st.columns([1, 1, 1, 1.1, 1.1, 1.6, 1.1], vertical_alignment="center")
    with f[0].popover(f"Campus{count_tag(sel_campus)}", width="stretch"):
        check_filter("campus", "All campuses", campus_opts, fmt=lambda c: f"{c} - {campus_names[c]}")
    with f[1].popover(f"Mode{count_tag(sel_mode)}", width="stretch"):
        check_filter("mode", "All modes", mode_opts)
    with f[2].popover(f"Status{count_tag(sel_status)}", width="stretch"):
        check_filter("status", "All statuses", status_opts)
    with f[3].popover(f"When{f' ({when_active})' if when_active else ''}", width="stretch"):
        st.slider(
            "Classes must fall between", min_value=FULL_DAY[0], max_value=FULL_DAY[1], value=FULL_DAY,
            step=timedelta(minutes=30), format="h:mm a", key=fk("time"),
        )
        st.multiselect(
            "Only days I can attend", WEEKDAYS, key=fk("days"), placeholder="Any day",
            format_func=lambda d: sch.DAY_NAMES[d],
        )
        st.checkbox("Include classes with no set meeting time (online)", value=True, key=fk("async"))
    with f[4].popover(f"Rating{f' ({min_val:.1f}+)' if min_val > 0 else ''}", width="stretch"):
        st.slider("Minimum professor rating", 0.0, 5.0, 0.0, step=0.5, key=fk("min"))
    with f[5].popover("Sort: " + sort_name.split(" (")[0], width="stretch"):
        st.selectbox("Sort professors by", list(SORT_OPTIONS), key=fk("sort"))
    f[6].button("Clear filters", on_click=clear_filters, width="stretch")

    sort_col, sort_ascending = SORT_OPTIONS[ss.get(fk("sort"), list(SORT_OPTIONS)[0])]

    results = offers
    if query.strip():
        kind, value = SEARCH.get(query, ("text", query.strip()))
        if kind == "course":
            results = results[results["course_code"] == value]
        elif kind == "prof":
            results = results[results["professors_text"].str.contains(value, regex=False)]
        else:
            q = value.lower()
            results = results[
                results["course_code"].str.lower().str.contains(q, regex=False)
                | results["course_name"].str.lower().str.contains(q, regex=False)
                | results["professors_text"].str.lower().str.contains(q, regex=False)
                | results["class_numbers"].str.contains(q, regex=False)
            ]
    results = results[results["rmp_rating"].fillna(0) >= min_val]
    if sel_campus:
        results = results[results["campus"].isin(sel_campus)]
    if sel_mode:  # matches if any part of the class (e.g. its lab) has the mode
        results = results[results["modes"].apply(lambda ms: any(m in sel_mode for m in ms))]
    if sel_status:
        keep = set().union(*(STATUS_LEVELS[s] for s in sel_status))
        results = results[results["seat_level"].isin(keep)]
    if when_active and len(results):
        lo, hi = (t.hour * 60 + t.minute for t in t_range)
        days_sel, include_async = ss.get(fk("days"), []), ss.get(fk("async"), True)

        def fits(row) -> bool:
            if not row["slots"]:
                return include_async
            return all(lo <= s and e <= hi and (not days_sel or d in days_sel) for d, s, e in row["slots"])

        results = results[results.apply(fits, axis=1)]

    seat_note = (
        "💺 Seat counts here are **sample numbers for the demo**. In a real version they would be a snapshot "
        "that changes daily; **Check live seats** opens the official search."
        if USING_SAMPLE_DATA else
        f"💺 Seat counts are a snapshot from **{seats_as_of}** and change daily. Use **Check live seats** "
        "for current numbers."
    )
    st.caption(f"➕ Classes you add go into **{active}**.  ·  {seat_note}")

    m1, m2, m3 = st.columns(3)
    m1.metric("Courses", results["course_code"].nunique())
    m2.metric("Class options", len(results))
    m3.metric("Professors", results["professor"].nunique())

    if results.empty:
        st.info("No classes match your search. Try a different code or name, or clear the filters.")

    card_no = 0
    for (code, name), group in results.groupby(["course_code", "course_name"], sort=True):
        group = group.sort_values(sort_col, ascending=sort_ascending, na_position="last")

        with st.expander(f"**{code}** · {name}  ({len(group)} option{'s' if len(group) != 1 else ''})",
                         expanded=bool(query.strip())):
            best = group.sort_values("rmp_rating", ascending=False).iloc[0]
            if has_rating(best):
                st.success(
                    f"🏆 **Top rated:** {best['professors_text']} ({best['campus']}) · "
                    f"{best['rmp_rating']:.1f} ⭐ · {int(best['would_take_again_pct'])}% would take again"
                )

            for o in group.to_dict("records"):
                card_no += 1
                with st.container(key=f"card-{card_no}"):
                    main, side = st.columns([8.4, 1.6], gap="medium")
                    with main:
                        st.markdown(f"#### {o['professors_text']}")
                        st.caption(f"{rating_line(o)}  ·  📍 {campus_names.get(o['campus'], o['campus'])}")
                        for c in o["components"]:
                            cc = st.columns([1.3, 1.9, 2.6, 3.3], vertical_alignment="center")
                            cc[0].markdown(f"**{c['component']}** · `{c['class_number']}`")
                            cc[1].write(c["mode"])
                            if c["professor"] and c["professor"] != o["professor"]:
                                cc[1].caption(f"Instructor: {c['professor']}")
                            cc[2].write("  \n".join(sch.meeting_text(*m) for m in c["meetings"]) or "No set meeting times")
                            cc[3].html(seat_chip(c["seat_level"], c["seat_label"]))
                        st.caption(f"[Check live seats ↗]({LIVE_SEARCH_URL}) (paste the class number into the search bar)")
                    with side.container(key=f"side-{card_no}"):
                        in_plan = o["oid"] in schedule
                        st.button(
                            "✓ Added" if in_plan else "＋ Add to plan", key=f"plan-{o['oid']}",
                            type="secondary" if in_plan else "primary", on_click=toggle_offer, args=(o["oid"],),
                            help="Click to remove it from this plan" if in_plan else f"Adds this class to {active}",
                            width="stretch",
                        )

                    # ---- "What students say": opens this professor's AI summary and reviews ----
                    for prof in dict.fromkeys(c["professor"] for c in o["components"] if c["professor"]):
                        revs = reviews.get(prof, [])
                        rv_key = f"{o['oid']}|{prof}"
                        is_open = rv_key in ss.open_rv
                        if not revs:  # nothing to open: a plain bar instead of a dropdown
                            st.html(
                                f"<div style='background:#F3F5F8;border:1px solid #DCE2EA;border-radius:10px;padding:9px 14px;"
                                f"color:#4A5A6E;font-family:sans-serif;font-size:15px'>💬 <b>{html_lib.escape(prof)}</b> · "
                                f"N/A · This professor has no ratings yet, so there's nothing to summarize. A new "
                                f"professor can turn out great or not, so you may want to ask a counselor or classmates.</div>"
                            )
                            continue
                        with st.container(key=f"rvbar-{card_no}-{prof}".replace(" ", "_")):
                            st.button(
                                f"💬 What students say about {prof}  ·  {len(revs)} review{'s' if len(revs) != 1 else ''}"
                                f"  {'▴' if is_open else '▾'}",
                                key=f"rv-{rv_key}", on_click=toggle_rv, args=(rv_key,), width="stretch",
                            )
                        if is_open:
                            with st.container(key=f"rvbody-{card_no}-{prof}".replace(" ", "_")):
                                if not revs:
                                    st.caption("No reviews for this professor yet.")
                                else:
                                    if st.button("✨ Summarize reviews with Rio", key=f"sum-{rv_key}"):
                                        lines = [
                                            f"Quality {r['quality']}/5, difficulty {r['difficulty']}/5, would take again: "
                                            f"{r['would_take_again']}. {r['review']} (tags: {r['tags'].replace(';', ', ')})"
                                            for r in revs
                                        ]
                                        with st.spinner("Rio is thinking..."):
                                            text, error = summarize_reviews(prof, lines)
                                        if error:
                                            st.warning(error)  # friendly message, only shown this one time
                                        else:
                                            ss.summaries[prof] = text
                                    if prof in ss.summaries:
                                        st.html(
                                            f"<div style='display:flex;gap:14px;align-items:flex-start;background:#EAF3FD;"
                                            f"border-radius:10px;padding:14px 16px;color:#1B4F8A;font-family:sans-serif;"
                                            f"font-size:15.5px;line-height:1.55'>"
                                            f"<img src='{RIO_URI}' width='30' height='30' style='flex:none;margin-top:2px'>"
                                            f"<div>{html_lib.escape(ss.summaries[prof])}</div></div>"
                                        )
                                    rc = st.columns(2)
                                    for i, r in enumerate(revs):
                                        with rc[i % 2]:
                                            st.html(render_reviews([r]))

# =====================================================================
# PAGE 2: BUILD SCHEDULE (calendar, commute checks, compare)
# =====================================================================
with st.container(key="page_sched"):
    t1, tl, t2 = st.columns([1.1, 1.0, 2.2], vertical_alignment="center")
    tl.markdown("**Getting between campuses:**")
    with t1:
        ss.setdefault("view", "Single plan")
        view = st.segmented_control(
            "View", ["Single plan", "Compare plans"], key="view", label_visibility="collapsed",
        ) or "Single plan"
    with t2:
        st.radio(
            "Getting between campuses", ["Car", "Transit", "Varies by day"], horizontal=True, key="mode_choice",
            label_visibility="collapsed",
            help="Used to check travel time between campuses. 'Varies by day' lets you pick for each weekday.",
        )
    if ss.get("mode_choice") == "Varies by day":
        st.caption("How will you travel on each day?")
        for col, d in zip(st.columns(5), WEEKDAYS):
            with col:
                ss.setdefault(f"day_mode_{d}", "Car")
                st.segmented_control(sch.DAY_NAMES[d], ["Car", "Transit"], key=f"day_mode_{d}")

    # ------------------------------------------------------------------
    # Single plan view
    # ------------------------------------------------------------------
    if view == "Single plan":
        pm, po = plan_data(active)

        if po.empty:
            st.info(f"{active} is empty. Go to **Find professors** and click **＋ Add to plan** on a class.")
        else:
            issues = sch.check_schedule(pm, po, travel, transport)
            alternatives = sch.find_alternatives(offers, meets, schedule, travel, transport, issues)
            stats = sch.plan_stats(pm, po, issues)

            k = st.columns([1.1, 1.3, 2, 2, 2])
            k[0].html(stat_chip("Classes", len(po)))
            k[1].html(stat_chip("Campuses", stats["campuses"]))
            k[2].html(tier_chip("conflict", stats["conflicts"]))
            k[3].html(tier_chip("risky", stats["risky"]))
            k[4].html(tier_chip("heads_up", stats["heads_up"]))

            if required:
                have, lack = sch.required_status(po, required)
                ok = not lack
                st.html(
                    f"<div style='font-family:sans-serif;font-size:14.5px;border-radius:10px;padding:7px 14px;"
                    f"background:{'#E3F4E8' if ok else '#FFF6D9'};color:{'#176B35' if ok else '#7A5B00'}'>"
                    f"📌 <b>Courses I must take:</b> {len(have)} of {len(required)} in this plan"
                    + ("  ✅ all covered" if ok else f" · <b>Missing:</b> {html_lib.escape(', '.join(lack))}")
                    + "</div>"
                )

            left, right = st.columns([7.4, 2.6], gap="large")
            with left:
                st.html(legend_html())
                st.html(render_week(pm, issues, travel, transport))

            with right:
                st.markdown("##### Your classes")
                for o in po.to_dict("records"):
                    c = st.columns([4, 1], vertical_alignment="center")
                    c[0].markdown(f"**{o['course_code']}** · {o['professors_text']}")
                    c[0].caption(f"{short_rating(o)}  \n{o['class_numbers']} · {o['campus']} · {o['seat_label']}")
                    c[1].button(
                        "✕", key=f"rm-{o['oid']}", on_click=toggle_offer, args=(o["oid"],),
                        help="Remove from this plan",
                    )

            st.markdown("##### Schedule check")
            if not issues:
                st.success("No conflicts, risks, or heads-ups. 🎉")
            seen_tiers: set[str] = set()
            for idx, i in enumerate(issues):
                st.html(issue_card(idx, i, i["tier"] not in seen_tiers))
                seen_tiers.add(i["tier"])

            if alternatives:
                with st.expander("💡 Options that would fix these problems", expanded=True):
                    for oid, df in alternatives.items():
                        cur = offers[offers["oid"] == oid].iloc[0]
                        st.markdown(f"**Instead of {cur['course_code']} ({cur['class_numbers']}):**")
                        for a in df.to_dict("records"):
                            rl = f"⭐ {a['rmp_rating']:.1f}" if has_rating(a) else "no rating"
                            when = " + ".join(
                                f"{c['component']} " + ("; ".join(sch.meeting_text(*m) for m in c["meetings"]) or "no set times")
                                for c in a["components"]
                            )
                            st.write(
                                f"- {a['class_numbers']} · {a['professors_text']} ({rl}) · {a['campus']} · "
                                f"{a['format_label']} · {when} · {a['seat_label']}"
                            )

    # ------------------------------------------------------------------
    # Compare view
    # ------------------------------------------------------------------
    else:
        if len(ss.plans) < 2:
            st.info("You only have one plan. Open **⚙️ Manage plans** at the top and choose "
                    "**📋 Duplicate** or **＋ New backup plan** to compare.")
        else:
            valid = [p for p in ss.get("cmp_plans", []) if p in ss.plans]
            ss.cmp_plans = valid if len(valid) >= 2 else sorted(ss.plans)[:3]
            chosen = st.multiselect("Plans to compare", sorted(ss.plans), key="cmp_plans", max_selections=3)

            if len(chosen) < 2:
                st.info("Pick at least two plans to compare.")
            else:
                data = {}
                for name in chosen:
                    pm_, po_ = plan_data(name)
                    iss_ = sch.check_schedule(pm_, po_, travel, transport) if not po_.empty else []
                    data[name] = (pm_, po_, iss_, sch.plan_stats(pm_, po_, iss_))
                    if required:
                        data[name][3]["missing_n"] = len(sch.required_status(po_, required)[1])

                def fmt_time(m):
                    return "-" if m is None else sch.fmt_minutes(m)

                def fmt_num(x):
                    return "-" if pd.isna(x) else f"{x:.1f}"

                # (label, stats key, which direction is better, how to show it)
                measures = [
                    ("Classes", "classes", None, str),
                    ("Earliest start", "earliest", None, fmt_time),  # information only (no ✅), so they go first
                    ("Latest end", "latest", None, fmt_time),
                ] + ([("📌 Missing courses", "missing_n", "low", str)] if required else []) + [
                    ("Days on campus per week", "days", "low", str),
                    ("Campuses (in person)", "campuses", "low", str),
                    ("Classes whose professor has ratings", "rated", None, str),
                    ("Average professor rating (rated only)", "avg_rating", "high", fmt_num),
                    ("Average difficulty (rated only)", "avg_difficulty", "low", fmt_num),
                    ("⛔ Conflicts", "conflicts", "low", str),
                    ("⚠️ Risky", "risky", "low", str),
                    ("ℹ️ Heads-ups", "heads_up", "low", str),
                ]
                table = {}
                for label, key, better, show in measures:
                    vals = {p: data[p][3][key] for p in chosen}
                    # round so values that look the same on screen are treated as a tie
                    numeric = {p: round(v, 1) for p, v in vals.items() if v is not None and not pd.isna(v)}
                    winners = set()
                    if better and len(set(numeric.values())) > 1:
                        target = (min if better == "low" else max)(numeric.values())
                        winners = {p for p, v in numeric.items() if v == target}
                    table[label] = {p: show(vals[p]) + (" ✅" if p in winners else "") for p in chosen}
                if required:  # show which courses are missing next to the count
                    for p in chosen:
                        lack = sch.required_status(data[p][1], required)[1]
                        if lack:
                            table["📌 Missing courses"][p] = table["📌 Missing courses"][p].replace(
                                str(len(lack)), f"{len(lack)} ({', '.join(lack)})", 1)
                st.markdown("#### Side by side")
                esc2 = html_lib.escape
                tcell = "padding:9px 14px;border-top:1px solid #E1E6EE;font-size:14.5px;min-width:0"
                tgrid = [
                    f"<div style='display:grid;grid-template-columns:310px repeat({len(chosen)}, minmax(0, 1fr));"
                    f"font-family:sans-serif;color:#12263F;background:#fff;border:1px solid #DCE2EA;border-radius:12px;"
                    f"overflow:hidden;box-shadow:0 2px 10px rgba(16,24,40,.07)'>",
                    f"<div style='{tcell};border-top:0;background:#EEF3F9'></div>",
                ] + [f"<div style='{tcell};border-top:0;background:#EEF3F9;font-weight:700'>{esc2(p)}</div>" for p in chosen]
                for i, (label, cells) in enumerate(table.items()):
                    shade = "background:#FAFBFD;" if i % 2 else ""
                    tgrid.append(f"<div style='{tcell};{shade}color:#4A5A6E'>{esc2(label)}</div>")
                    tgrid += [f"<div style='{tcell};{shade}'>{esc2(cells[p])}</div>" for p in chosen]
                tgrid.append("</div>")
                st.html("".join(tgrid))
                st.caption("✅ marks the best value in each row. Earliest start and latest end are for "
                           "information only, since the best choice depends on you.")

                st.caption("💡 Hover over any class on the calendars below to see its full details.")
                hours = hour_bounds([data[p][0] for p in chosen])
                for col, name in zip(st.columns(len(chosen)), chosen):
                    with col:
                        st.markdown(f"**{name}**")
                        if data[name][1].empty:
                            st.caption("Empty plan")
                        else:
                            st.html(render_week(data[name][0], data[name][2], travel, transport,
                                                compact=True, hours=hours))

                # ---- what's different: one row per course that isn't identical in every plan ----
                st.markdown("#### What's different")
                esc = html_lib.escape
                grid_cols = f"grid-template-columns:110px repeat({len(chosen)}, minmax(0, 1fr))"  # equal widths
                cell_css = "padding:10px 12px;border-top:1px solid #E1E6EE;font-size:14px;line-height:1.45;min-width:0"
                grid = [
                    f"<div style='display:grid;{grid_cols};font-family:sans-serif;color:#12263F;background:#fff;"
                    f"border:1px solid #DCE2EA;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(16,24,40,.07)'>",
                    f"<div style='{cell_css};border-top:0;background:#EEF3F9;font-weight:700'>Course</div>",
                ] + [
                    f"<div style='{cell_css};border-top:0;background:#EEF3F9;font-weight:700'>{esc(p)}</div>"
                    for p in chosen
                ]
                n_diff = 0
                for code in sorted({c for p in chosen for c in data[p][1]["course_code"]}):
                    subs = {p: data[p][1][data[p][1]["course_code"] == code] for p in chosen}
                    if len({frozenset(s["oid"]) for s in subs.values()}) <= 1:
                        continue  # identical in every plan
                    n_diff += 1
                    # the plan whose professor for this course is rated higher gets a check mark
                    avg = {p: round(s["rmp_rating"].mean(), 1) for p, s in subs.items() if s["rmp_rating"].notna().any()}
                    best = {p for p, v in avg.items() if v == max(avg.values())} if len(set(avg.values())) > 1 else set()
                    grid.append(f"<div style='{cell_css};font-weight:700;color:{NAVY}'>{esc(code)}</div>")
                    for p, s in subs.items():
                        if s.empty:
                            grid.append(f"<div style='{cell_css};color:#8A97A8'>— not in this plan</div>")
                            continue
                        parts = []
                        for o in s.to_dict("records"):
                            rate = short_rating(o)
                            parts.append(
                                f"<div><b>{esc(o['class_numbers'])}</b> · {esc(o['professors_text'])}</div>"
                                f"<div style='font-size:13px;color:#4A5A6E'>{esc(o['campus'])} · {esc(rate)}</div>"
                            )
                        tag = (" <span style='color:#1E7B3A;font-weight:700;font-size:13px'>✅ higher rated</span>"
                               if p in best else "")
                        grid.append(f"<div style='{cell_css}'>{''.join(parts)}{tag}</div>")
                grid.append("</div>")
                if n_diff:
                    st.html("".join(grid))
                    st.caption("Only courses that differ between the plans are listed. ✅ marks the plan whose "
                               "professor has the higher rating for that course.")
                else:
                    st.info("These plans contain exactly the same classes.")

                st.button(
                    "💬 Ask Rio which plan I should pick", on_click=ask_ai,
                    args=("Compare my plans and tell me which one I should pick as my main plan, and why.",),
                )

    with st.expander("🚌 Travel time estimates used (approximate)"):
        st.dataframe(
            travel,
            hide_index=True,
            width="stretch",
            column_config={
                "from_campus": "From", "to_campus": "To",
                "car_typical": "Car: typical (min)", "car_worst": "Car: bad day (min)",
                "transit_typical": "Transit: typical (min)", "transit_worst": "Transit: bad day (min)",
            },
        )
        st.caption(
            "Rough estimates, not live traffic or bus data. A connection is flagged risky if it "
            "would fail on a bad day."
        )

# ---------- Footer ----------
st.divider()
with st.expander("ℹ️ Data sources and disclaimers"):
    st.markdown(
        ("- **Class schedule and seats:** this demo uses sample data in `data/classes.csv`, partly modeled on "
           "the public Los Rios class schedule. Seat counts are sample numbers; a real version would use a daily "
           "snapshot, and *Check live seats* opens the official search. "
           if USING_SAMPLE_DATA else
           "- **Class schedule and seats:** public Los Rios class schedule, copied by hand into "
           f"`data/classes.csv` (seat snapshot: {seats_as_of}). Seats change daily; use *Check live seats*. ")
        + f"Waitlists are assumed to hold {sch.WAITLIST_CAPACITY} students.\n"
        "- **Ratings and reviews:** modeled on what [Rate My Professors](https://www.ratemyprofessors.com) "
        "shows. In this demo, professors, ratings, and reviews are fictional sample data.\n"
        "- **Travel times:** approximate estimates in `data/travel_times.csv`.\n"
        "- **AI:** Google Gemini API (review summaries and Rio, the chat guide).\n\n"
        f"The app never contacts Los Rios or RMP while running. {APP_NAME} is not affiliated with Los Rios or "
        "Rate My Professors."
    )

# =====================================================================
# FLOATING "ASK RIO" PANEL (bottom right, on every page)
# =====================================================================
GREETING = (
    f"Hi, I'm Rio! I can answer questions about your plans and professors, and help you find your way around "
    f"{APP_NAME}. What can I help with?"
)

st.button(
    "Close" if ss.ai_open else "Ask Rio", key="ai_fab", type="primary",
    on_click=set_ai, args=(not ss.ai_open,),
)

if ss.ai_open:
    with st.container(key="ai_panel"):
        h1, h2 = st.columns([5, 1], vertical_alignment="center")
        h1.html(
            f"<div style='display:flex;align-items:center;gap:10px;font-family:sans-serif;color:{NAVY}'>"
            f"<img src='{RIO_URI}' width='34' height='34'><div><b style='font-size:17px'>Rio</b>"
            f"<div style='font-size:12px;color:#5b6676'>Your {APP_NAME} guide</div></div></div>"
        )
        h2.button("✕", key="ai_close", on_click=set_ai, args=(False,), help="Close")

        box = st.container(height=380)  # the only scrollbar: it scrolls the messages
        prompt = st.chat_input("Ask Rio about your plans or the site...", key="ai_input", max_chars=500)
        if not prompt:
            prompt = ss.pop("pending_prompt", None)

        with box:
            with st.chat_message("assistant", avatar=RIO_AVATAR):
                st.write(GREETING)
            if not ss.chat and not prompt:
                for text in [
                    "Review my current plan",
                    "Which of my plans is the safest, and why?",
                    f"How do I use {APP_NAME}?",
                ]:
                    st.button(text, key=f"starter-{text}", on_click=ask_ai, args=(text,), width="stretch")
            for m in ss.chat:
                with st.chat_message(m["role"], avatar=RIO_AVATAR if m["role"] == "assistant" else None):
                    if m.get("error"):
                        st.warning(m["content"])
                    else:
                        st.write(m["content"])
            if prompt:
                ss.chat.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.write(prompt)
                with st.chat_message("assistant", avatar=RIO_AVATAR):
                    with st.spinner("Rio is thinking..."):
                        text, error = chat_reply(
                            history=[m for m in ss.chat if not m.get("error")],
                            plans_text=sch.plans_to_text(ss.plans, active, offers, meets, travel, transport, required),
                            catalog_text=sch.catalog_to_text(offers),
                            mode=sch.transport_to_text(transport),
                            seats_as_of=seats_as_of,
                            priorities=list(ss.prio_rank),
                            priorities_text=sch.priorities_to_text(
                                ss.plans, offers, meets, travel, transport, list(ss.prio_rank), required),
                        )
                    if error:
                        st.warning(error)
                        ss.chat.append({"role": "assistant", "content": error, "error": True})
                    else:
                        st.write(text)
                        ss.chat.append({"role": "assistant", "content": text})
                # Streamlit scrolls the chat box to the bottom after a reply; bring the TOP of Rio's answer into
                # view instead, so the student starts reading at the first line.
                ss.scroll_chat = ss.get("scroll_chat", 0) + 1
                st.html(
                    "<script>/*" + str(ss.scroll_chat) + "*/ (function () { var go = function () { "
                    "var msgs = document.querySelectorAll('.st-key-ai_panel [data-testid=\"stChatMessage\"]'); "
                    "var m = msgs[msgs.length - 1]; if (m) { m.scrollIntoView({block: 'start'}); } }; "
                    "[60, 350, 800, 1400].forEach(function (t) { setTimeout(go, t); }); })();</script>",
                    unsafe_allow_javascript=True,
                )

        if ss.chat:
            st.button("Clear chat", key="ai_clear", on_click=lambda: ss.update(chat=[]))
