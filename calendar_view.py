"""Draws a Monday-Friday weekly calendar for the chosen classes as simple HTML.

- in-person classes: solid border; online (set times): dashed border + globe tag;
  partially online: dotted border + "maybe on campus" tag
- classes with a problem get a thick colored border and a label on the block itself;
  clicking one jumps to that problem in the "Schedule check" list (anchor #issue-N)
- classes that overlap in time are drawn side by side so none is hidden
- commute blocks (hatched) are drawn between in-person classes at different campuses
- classes with no set meeting time go in a row under the calendar
- the full-size calendar scales with the window height (so it fits on screen without scrolling);
  everything inside the grid is positioned in percentages of the day
"""
import html

import pandas as pd

import scheduler as sch

COLORS = [
    ("#D6E6FF", "#1F5FBF"),
    ("#DDF3DD", "#2E7D32"),
    ("#FFE6C9", "#B26A00"),
    ("#EBDDFF", "#6A3DB8"),
    ("#FFDCE3", "#B4234A"),
    ("#D4F0F0", "#157A7A"),
    ("#F4EFC0", "#8A7A00"),
]
RED, GOLD, BLUE, GRAY = "#D32F2F", "#D9A400", "#1F6FD1", "#6B7280"
WEEKDAYS = ["M", "T", "W", "Th", "F"]
TIER_COLOR = {"conflict": RED, "risky": GOLD, "heads_up": BLUE}
TIER_TEXT = {"conflict": "#fff", "risky": "#1B2430", "heads_up": "#fff"}

NOTE_COLOR = {"conflict": "#FFB3B3", "risky": "#FFD966", "heads_up": "#9CCBFF"}  # readable on navy


def _tip(title: str, lines: list[str], note: str | None = None, note_color: str | None = None,
         hint: str | None = None) -> str:
    """Inner HTML of the instant hover box (styled by the .rr-tip rules in app.py)."""
    body = f"<div class='rr-tt'>{html.escape(title)}</div>" + "".join(f"<div>{html.escape(x)}</div>" for x in lines)
    if note:
        body += f"<div style='margin-top:6px;font-weight:600;color:{note_color or '#DDE6F2'}'>{html.escape(note)}</div>"
    if hint:
        body += f"<div class='rr-th'>{html.escape(hint)}</div>"
    return body


def _short(text: str, n: int = 150) -> str:
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "… (see Schedule check)"


def tip_pos(day: str, top_pct: float) -> str:
    """Where the hover box opens so it stays inside the calendar: left/centre/right by day, above for late classes."""
    i = WEEKDAYS.index(day)
    return ("rr-tl" if i <= 1 else "rr-tr" if i >= 3 else "rr-tc") + (" rr-up" if top_pct > 55 else "")


# Height of the full-size grid: follows the window height, with sensible limits.
FULL_HEIGHT = "clamp(360px, calc(100vh - 540px), 740px)"


def hour_bounds(meets_list: list[pd.DataFrame]) -> tuple[int, int]:
    """Shared start/end hours so several calendars (Compare view) line up with each other.
    Tight around the classes (no empty early morning or late evening), at least 6 hours tall."""
    starts, ends = [], []
    for meets in meets_list:
        for m in sch.expand(meets) if len(meets) else []:
            if m["day"] in WEEKDAYS:
                starts.append(m["start"])
                ends.append(m["end"])
    if not starts:
        return 8, 14
    start_h, end_h = min(starts) // 60, -(-max(ends) // 60)
    if end_h - start_h < 6:
        end_h = start_h + 6
    return start_h, end_h


def _worst_tier_per_offering(issues: list[dict]) -> dict[str, tuple[str, int]]:
    """oid -> (worst tier, index in `issues` of the first issue with that tier)."""
    worst: dict[str, tuple[str, int]] = {}
    for idx, i in enumerate(issues):
        for oid in i["oids"]:
            if sch.TIER_RANK[i["tier"]] > sch.TIER_RANK.get(worst.get(oid, ("", 0))[0], 0):
                worst[oid] = (i["tier"], idx)
    return worst


def _assign_lanes(blocks: list[dict]) -> None:
    """Gives overlapping blocks a 'lane' and a lane count so they can sit side by side."""
    blocks.sort(key=lambda b: (b["start"], b["end"]))
    cluster: list[dict] = []
    cluster_end = -1

    def flush(cl: list[dict]) -> None:
        lanes: list[int] = []  # end time of each lane
        for b in cl:
            for i, end in enumerate(lanes):
                if end <= b["start"]:
                    lanes[i], b["lane"] = b["end"], i
                    break
            else:
                lanes.append(b["end"])
                b["lane"] = len(lanes) - 1
        for b in cl:
            b["lanes"] = len(lanes)

    for b in blocks:
        if cluster and b["start"] >= cluster_end:
            flush(cluster)
            cluster, cluster_end = [], -1
        cluster.append(b)
        cluster_end = max(cluster_end, b["end"])
    if cluster:
        flush(cluster)


def legend_html() -> str:
    """One-line key that sits above the calendar."""
    def item(swatch: str, text: str) -> str:
        return (f"<span style='display:inline-flex;align-items:center;gap:6px;margin-right:16px'>"
                f"{swatch}<span>{text}</span></span>")

    box = "display:inline-block;width:20px;height:13px;border-radius:4px;background:#EEF3F9;box-sizing:border-box;"
    return (
        "<div style='font-family:sans-serif;font-size:13px;color:#33465C;line-height:1.9'>"
        "<b style='margin-right:10px;color:#0B2A4A'>Key</b>"
        + item(f"<span style='{box}border:3px solid {RED}'></span>", "Conflict")
        + item(f"<span style='{box}border:3px solid {GOLD}'></span>", "Risky")
        + item(f"<span style='display:inline-block;background:{BLUE};color:#fff;border-radius:4px;padding:0 5px;"
               f"font-size:11px;font-weight:700'>ℹ️</span>", "Heads-up")
        + item(f"<span style='{box}border:1.5px dashed {GRAY};background:repeating-linear-gradient(45deg,"
               f"{GRAY}33 0,{GRAY}33 4px,#fff 4px,#fff 8px)'></span>", "Commute")
        + item(f"<span style='{box}border:1.5px dashed #1F5FBF'></span>", "Online, set times")
        + item(f"<span style='{box}border:2px dotted #1F5FBF'></span>", "Partly online")
        + "<span style='color:#17476F;font-weight:600'>💡 Hover a class for details</span></div>"
    )


def render_week(
    meets: pd.DataFrame,
    issues: list[dict],
    travel: pd.DataFrame,
    transport,
    compact: bool = False,
    hours: tuple[int, int] | None = None,
) -> str:
    gutter = 34 if compact else 48
    font = 10 if compact else 12
    worst = _worst_tier_per_offering(issues)

    ms = sch.expand(meets)
    course_order = list(dict.fromkeys(m["course_code"] for m in ms))
    timed = [m for m in ms if m["day"] in WEEKDAYS]
    weekend = sorted({f"{m['course_code']} ({sch.DAY_NAMES[m['day']]})" for m in ms if m["day"] and m["day"] not in WEEKDAYS})
    timed_oids = {m["oid"] for m in ms if m["day"]}
    no_time = list(dict.fromkeys(
        (m["oid"], m["course_code"], m["campus"], m["kind"]) for m in ms if m["oid"] not in timed_oids
    ))
    for d in WEEKDAYS:
        _assign_lanes([m for m in timed if m["day"] == d])

    header = "".join(
        f"<div style='flex:1;min-width:0;text-align:center;font-weight:700;padding:4px 0;"
        f"font-size:{font + 1}px;color:#0B2A4A'>{sch.DAY_NAMES[d]}</div>"
        for d in WEEKDAYS
    )
    out = [
        "<div style='border:1px solid #DDE3EC;border-radius:14px;padding:2px 8px 8px;background:#fff;"
        "font-family:sans-serif;box-shadow:0 3px 14px rgba(16,24,40,.08)'>",
        f"<div style='display:flex'><div style='width:{gutter}px;flex:none'></div>{header}</div>",
    ]

    # ---- timed grid ----
    if timed:
        start_h, end_h = hours or hour_bounds([meets])
        n_hours = end_h - start_h
        span = n_hours * 60  # minutes shown
        height = f"{n_hours * 44}px" if compact else FULL_HEIGHT

        def pct(minute: float) -> float:
            return (minute - start_h * 60) * 100 / span

        hour_labels = "".join(
            f"<div style='position:absolute;top:{pct(h * 60):.3f}%;right:6px;transform:translateY(-50%);"
            f"font-size:{font - 1}px;color:#5b6676'>{sch.fmt_minutes(h * 60).replace(':00', '')}</div>"
            for h in range(start_h, end_h + 1)
        )

        # commute blocks: consecutive in-person classes on the same day at different campuses
        commutes: dict[str, list[str]] = {d: [] for d in WEEKDAYS}
        for d in WEEKDAYS:
            seq = sorted([m for m in timed if m["day"] == d and m["loc"] in ("in_person", "maybe")], key=lambda m: m["start"])
            for first, second in zip(seq, seq[1:]):
                if first["campus"] == second["campus"] or second["start"] < first["end"] or first["oid"] == second["oid"]:
                    continue
                mode = sch.mode_for(transport, d)
                trip = sch.travel_minutes(travel, first["campus"], second["campus"], mode)
                if trip is None:
                    continue
                typical, bad = trip
                gap = second["start"] - first["end"]
                need = bad + sch.EXTRA_BUFFER[mode]
                color = RED if gap < typical else GOLD if gap < need else GRAY
                icon = "🚗" if mode == "Car" else "🚌"
                verdict = ("Not enough time" if gap < typical else "Tight" if gap < need else "Enough time")
                tip = _tip(
                    f"{icon} {first['campus']} to {second['campus']} by {mode.lower()}",
                    [f"About {typical} min on a good day, up to {bad} min on a bad day",
                     f"Time between classes: {gap} min"],
                    note=verdict, note_color={RED: NOTE_COLOR['conflict'], GOLD: NOTE_COLOR['risky']}.get(color, "#DDE6F2"),
                )
                commutes[d].append(
                    f"<div class='rr-tw {tip_pos(d, pct(first['end']))}' style='position:absolute;left:3px;right:3px;"
                    f"top:{pct(first['end']):.3f}%;height:{typical * 100 / span:.3f}%;min-height:14px;z-index:1'>"
                    f"<div class='rr-cm' style='width:100%;height:100%;border:1.5px dashed {color};border-radius:5px;"
                    f"box-sizing:border-box;color:{color};font-size:{font - 1}px;font-weight:700;padding:0 4px;"
                    f"line-height:1.1;background:repeating-linear-gradient(45deg,{color}33 0,{color}33 5px,"
                    f"#ffffffcc 5px,#ffffffcc 10px)'><span>{icon}</span><span class='rr-cmt'> ~{typical} min</span></div>"
                    f"<div class='rr-tip'>{tip}</div></div>"
                )

        cols = []
        for d in WEEKDAYS:
            cells = []
            for m in timed:
                if m["day"] != d:
                    continue
                bg, fg = COLORS[course_order.index(m["course_code"]) % len(COLORS)]
                tier, issue_idx = worst.get(m["oid"], (None, None))
                if tier == "conflict":
                    border = f"4px solid {RED}"
                elif tier == "risky":
                    border = f"4px solid {GOLD}"
                elif m["loc"] == "online":
                    border = f"1.5px dashed {fg}"
                elif m["loc"] == "maybe":
                    border = f"2px dotted {fg}"
                else:
                    border = f"1px solid {fg}"

                title = m["course_code"] + (f" {m['component']}" if m["multi"] else "")
                clock = (f"{sch.fmt_minutes(m['start']).replace(' ', '')[:-2]}–"
                         f"{sch.fmt_minutes(m['end']).replace(' ', '')}")
                where = {"in_person": m["campus"], "online": "🌐 Online", "maybe": f"{m['campus']} · 🌐?"}[m["loc"]]
                # narrow blocks (classes sharing a column, or the small Compare calendars): the name may
                # wrap, the time drops AM/PM, and the problem label becomes a small icon
                split = m["lanes"] > 1 or compact
                if split:
                    clock = f"{sch.fmt_minutes(m['start'])[:-3]}–{sch.fmt_minutes(m['end'])[:-3]}"

                # Lines inside a block appear only if the block is tall enough to show them whole
                # (the CSS .rr-l2 / .rr-l3 / .rr-bd rules); the hover box always has everything.
                badge, tier_icon = "", ""
                if tier:
                    icon_b, tier_name = sch.TIER_LABELS[tier]
                    tier_icon = f"<span class='rr-ic'>{icon_b}</span>"
                    badge = (
                        f"<div class='rr-bd'><span style='background:{TIER_COLOR[tier]};color:{TIER_TEXT[tier]};"
                        f"border-radius:4px;padding:0 5px;font-weight:700'>{html.escape(f'{icon_b} {tier_name}')}"
                        f"</span></div>"
                    )
                where_long = ("online, no travel" if m["loc"] == "online" else
                              "on campus" if m["loc"] == "in_person" else "partly online, may be on campus")
                tip = _tip(
                    f"{title} · class {m['class_number']}",
                    [f"{sch.DAY_NAMES[d]} {sch.fmt_minutes(m['start'])} to {sch.fmt_minutes(m['end'])}",
                     f"{m['professor']} · {m['mode_name']}", f"{m['campus']} ({where_long})"],
                    note=f"{sch.TIER_LABELS[tier][1]}: {_short(issues[issue_idx]['text'])}" if tier else None,
                    note_color=NOTE_COLOR.get(tier),
                    hint="Click to jump to this problem" if tier and not compact else None,
                )
                n = m["lanes"]
                block = (
                    f"<div class='rr-tw {tip_pos(d, pct(m['start']))}' style='position:absolute;"
                    f"left:calc({m['lane']} * 100% / {n} + 3px);width:calc(100% / {n} - 6px);"
                    f"top:{pct(m['start']):.3f}%;height:calc({(m['end'] - m['start']) * 100 / span:.3f}% - 2px);z-index:2'>"
                    f"<div class='rr-blk{' rr-split' if split else ''}{' rr-blk-link' if tier and not compact else ''}' "
                    f"style='width:100%;height:100%;background:{bg};color:{fg};border:{border};border-radius:7px;"
                    f"padding:1px 5px;font-size:{font - 1 if not compact else font}px;box-sizing:border-box;line-height:1.25'>"
                    f"<div class='rr-t'><b>{html.escape(title)}</b> {tier_icon}</div>"
                    f"<div class='rr-l2'>{clock}</div><div class='rr-l3'>{html.escape(where)}</div>{badge}</div>"
                    f"<div class='rr-tip'>{tip}</div></div>"
                )
                if tier and not compact:  # click to jump to the matching message under "Schedule check"
                    block = f"<a href='#issue-{issue_idx}' style='display:contents;text-decoration:none'>{block}</a>"
                cells.append(block)
            cols.append(
                f"<div style='flex:1;min-width:0;position:relative;height:{height};"
                f"border-left:1px solid #DDE3EC;background-image:linear-gradient(to bottom,#EEF1F6 1px,"
                f"transparent 1px);background-size:100% calc(100% / {n_hours})'>"
                f"{''.join(cells)}{''.join(commutes[d])}</div>"
            )

        out.append(
            f"<div style='display:flex;margin-top:8px'><div style='width:{gutter}px;flex:none;position:relative;"
            f"height:{height}'>{hour_labels}</div>{''.join(cols)}</div>"
        )
    elif not no_time:
        out.append("<div style='padding:12px;color:#5b6676'>Nothing to show yet.</div>")

    # ---- "no set time" row (online, no meeting times), under the grid so calendars line up ----
    if no_time:
        pills = ""
        for _oid, code, campus, kind in no_time:
            ci = course_order.index(code) % len(COLORS)
            what = "🌐 Online · no set time" if kind in ("async", "sync") else "🕘 No set time listed"
            pills += (
                f"<div style='background:{COLORS[ci][0]};color:{COLORS[ci][1]};border:1.5px dashed "
                f"{COLORS[ci][1]};border-radius:8px;padding:3px 10px;margin-top:4px;font-size:{font}px;"
                f"font-weight:600'>{html.escape(what)}: {html.escape(code)} · {html.escape(campus)}</div>"
            )
        out.append(
            f"<div style='display:flex;margin-top:6px'>"
            f"<div style='width:{gutter}px;flex:none'></div><div style='flex:1;min-width:0'>{pills}</div></div>"
        )

    out.append("</div>")
    if weekend:
        out.append(
            "<div style='margin-top:6px;font-size:13px;color:#5b6676;font-family:sans-serif'>"
            f"📌 Weekend meetings not shown on this Mon–Fri calendar: {html.escape(', '.join(weekend))}</div>"
        )
    return "".join(out)
