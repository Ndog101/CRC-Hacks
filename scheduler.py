"""Schedule logic: reads times/days, finds overlaps, checks travel time and seats.

This file contains NO AI. It is plain, predictable code, so the warnings are always
correct and work even without an API key. The AI only explains the results.

Words used here:
  offering  = one card on the Los Rios site (for example a LEC and its LAB together).
              This is what a student adds to a plan.
  meeting   = one day/time slot of one class (a TTh class has two meetings).
  tier      = how serious a problem is: "conflict" (can't work), "risky" (might fail),
              "heads_up" (good to know).
"""
import re
from datetime import datetime

import pandas as pd

DAY_MAP = {"m": "M", "t": "T", "w": "W", "th": "Th", "f": "F", "sa": "Sa", "su": "Su"}
DAY_ORDER = ["M", "T", "W", "Th", "F", "Sa", "Su"]
DAY_NAMES = {"M": "Mon", "T": "Tue", "W": "Wed", "Th": "Thu", "F": "Fri", "Sa": "Sat", "Su": "Sun"}

# Extra minutes needed on top of the trip itself (parking + walking to class, or
# walking to the stop and waiting for the bus/train).
EXTRA_BUFFER = {"Car": 15, "Transit": 10}
SAME_CAMPUS_MIN_GAP = 10  # fewer minutes than this between classes on one campus = heads-up (short walk)
SAME_CAMPUS_RISKY_GAP = 5  # fewer minutes than this (including back to back) = risky (you'd have to rush)
FEW_SEATS = 5  # this many open seats or fewer counts as "almost full"
WAITLIST_CAPACITY = 20  # a full class holds at most this many people on its waitlist (assumed, change if needed)

# ---- Problem tiers (used everywhere: messages, calendar, plan chips, Compare, AI) ----
TIER_RANK = {"conflict": 3, "risky": 2, "heads_up": 1}
TIER_LABELS = {"conflict": ("⛔", "Conflict"), "risky": ("⚠️", "Risky"), "heads_up": ("ℹ️", "Heads-up")}
# kind -> (tier, short name)
ISSUE_META = {
    "overlap": ("conflict", "Overlap"),
    "impossible": ("conflict", "Can't make the trip"),
    "risky": ("risky", "Tight trip"),
    "maybe": ("risky", "Maybe on campus"),
    "online_trip": ("risky", "Online class during trip"),
    "no_data": ("risky", "No travel estimate"),
    "seats_full": ("conflict", "Class and waitlist full"),
    "seats_waitlist": ("risky", "Full · waitlist only"),
    "seats_few": ("heads_up", "Few seats left"),
    "unrated": ("heads_up", "No ratings yet"),
    "duplicate": ("heads_up", "Same course twice"),
    "close": ("heads_up", "Short break"),
    "rush": ("risky", "Very short break"),
}

# The four "Mode" values used by the Los Rios class search
MODE_CANON = {
    "in_person": "In Person",
    "partial": "Partially Online",
    "sync": "Fully Online - Synchronous",
    "async": "Fully Online - Asynchronous",
}


# ---------- Reading days, times and modes ----------
NAME_MAP = {"mon": "M", "tue": "T", "tues": "T", "wed": "W", "thu": "Th", "thur": "Th", "thurs": "Th",
            "fri": "F", "sat": "Sa", "sun": "Su"}


def parse_days(text) -> list[str]:
    """Reads 'TTh', 'MW', 'Tue/Thu' or 'Mon/Wed/Fri'. Anything we can't read (like 'Online') -> []."""
    raw = str(text or "").strip().lower()
    if not raw:
        return []
    parts = [p for p in re.split(r"[\s/,&]+", raw) if p]
    if parts and all(p in NAME_MAP for p in parts):
        return [NAME_MAP[p] for p in parts]
    s = re.sub(r"[\s/,&]+", "", raw)
    if not s or not re.fullmatch(r"(th|sa|su|m|t|w|f)+", s):
        return []
    return [DAY_MAP[t] for t in re.findall(r"th|sa|su|m|t|w|f", s)]


def days_display(text) -> str:
    """'TTh' -> 'Tue/Thu' (the way the Los Rios site writes it)."""
    days = parse_days(text)
    return "/".join(DAY_NAMES[d] for d in days) if days else str(text)


def time_display(text) -> str:
    """'9:00 AM' -> '9:00 am'."""
    return str(text).strip().lower()


def parse_time(text) -> int | None:
    """'9:00 AM' -> 540 (minutes after midnight). Blank/unreadable -> None."""
    s = str(text or "").strip().upper().replace(".", "")
    if not s:
        return None
    s = re.sub(r"\s*(AM|PM)$", r" \1", s)
    for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
        try:
            t = datetime.strptime(s, fmt)
            return t.hour * 60 + t.minute
        except ValueError:
            continue
    return None


def fmt_minutes(m: int) -> str:
    h, mm = divmod(int(m), 60)
    return f"{h % 12 or 12}:{mm:02d} {'AM' if h < 12 else 'PM'}"


def mode_kind(mode) -> str:
    """Turns the Mode text into one of: 'async', 'sync', 'partial', 'in_person'."""
    m = str(mode).lower()
    if "asynch" in m:  # check this before "synch", which is inside "asynchronous"
        return "async"
    if "synch" in m:
        return "sync"
    if "partial" in m or "hybrid" in m:
        return "partial"
    if "online" in m:
        return "sync"
    return "in_person"


def mode_for(transport, day) -> str:
    """transport is 'Car'/'Transit', or a dict like {'M': 'Car', 'T': 'Transit', ...}."""
    return transport.get(day, "Car") if isinstance(transport, dict) else transport


def expand(meets: pd.DataFrame) -> list[dict]:
    """One dict per (class meeting, day). 'loc' says where you must be:
       in_person = at the campus, online = anywhere, maybe = partially online (unknown days)."""
    comps_per_offering = meets.groupby("oid")["class_number"].nunique().to_dict()
    out = []
    for r in meets.to_dict("records"):
        kind = mode_kind(r["mode"])
        base = {
            "oid": r["oid"], "course_code": r["course_code"], "class_number": r["class_number"],
            "component": r["component"], "campus": r["campus"], "kind": kind,
            "professor": r["professor"] or "Staff", "mode_name": MODE_CANON[kind],
            "loc": {"in_person": "in_person", "partial": "maybe"}.get(kind, "online"),
            "multi": comps_per_offering.get(r["oid"], 1) > 1,
        }
        start, end, days = parse_time(r["start_time"]), parse_time(r["end_time"]), parse_days(r["days"])
        if start is None or end is None or not days:
            out.append({**base, "day": None, "start": None, "end": None})
        else:
            out.extend({**base, "day": d, "start": start, "end": end} for d in days)
    return out


def meeting_text(days, start, end) -> str:
    """'TTh', '9:00 AM', '10:20 AM' -> 'Tue/Thu, 9:00 am to 10:20 am'."""
    return f"{days_display(days)}, {time_display(start)} to {time_display(end)}"


def comp_when(comp: dict) -> str:
    if not comp["meetings"]:
        return "No set meeting times"
    return "\n".join(meeting_text(*m) for m in comp["meetings"])


# ---------- Seats ----------
def _to_int(value, default=None):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def seat_info(row) -> tuple[str, str]:
    """(level, label). level is 'open', 'few' (open but almost full), 'waitlist' (full, but the
    waitlist has room), 'full' (full and the waitlist is full too) or 'unknown'."""
    n = _to_int(row.get("seats_open"))
    if n is None:
        return "unknown", "⚪ Seats unknown"
    wait = _to_int(row.get("waitlist"), 0)
    if n <= 0:
        if wait >= WAITLIST_CAPACITY:
            return "full", f"🔴 Full · waitlist full ({wait}/{WAITLIST_CAPACITY})"
        return "waitlist", f"🟡 Full · waitlist {wait}/{WAITLIST_CAPACITY} · you'd be #{wait + 1}"
    seats = f"{n} open seat{'s' if n != 1 else ''}"
    if n <= FEW_SEATS:
        return "few", f"🟢 {seats} · almost full"
    return "open", f"🟢 {seats}"


# ---------- Building offerings (cards) from meeting rows ----------
def build_offers(meets: pd.DataFrame, profs: pd.DataFrame) -> pd.DataFrame:
    """One row per offering (card): its parts (LEC/LAB), instructors, seats, format, time slots."""
    rows = []
    for oid, g in meets.groupby("oid", sort=False):
        comps = []
        for (cls, comp), cg in g.groupby(["class_number", "component"], sort=False):
            c0 = cg.iloc[0]
            comps.append(
                {
                    "component": comp, "class_number": cls, "professor": c0["professor"],
                    "mode": MODE_CANON[mode_kind(c0["mode"])],
                    "seats_open": c0["seats_open"], "waitlist": c0["waitlist"],
                    "seat_level": seat_info(c0)[0], "seat_label": seat_info(c0)[1],
                    "meetings": [(r.days, r.start_time, r.end_time) for r in cg.itertuples() if r.days],
                }
            )
        seat_counts = [_to_int(c["seats_open"]) for c in comps]
        known = [s for s in seat_counts if s is not None]
        agg = {
            "seats_open": min(known) if known else "",
            "waitlist": max([_to_int(c["waitlist"], 0) for c in comps] or [0]),
        }
        level, label = seat_info(agg)
        formats = list(dict.fromkeys(c["mode"] for c in comps))  # the card's parts may differ
        names = list(dict.fromkeys(c["professor"] for c in comps if c["professor"]))
        rows.append(
            {
                "oid": oid, "course_code": g.iloc[0]["course_code"], "course_name": g.iloc[0]["course_name"],
                "campus": g.iloc[0]["campus"], "professor": names[0] if names else "",
                "professors_text": ", ".join(names) or "Staff",
                "modes": formats, "format_label": " + ".join(formats),
                "components": comps, "class_numbers": " + ".join(f"{c['component']} {c['class_number']}" for c in comps),
                "seats_open": agg["seats_open"], "waitlist": agg["waitlist"],
                "seat_level": level, "seat_label": label,
                "slots": [(m["day"], m["start"], m["end"]) for m in expand(g) if m["day"]],
            }
        )
    return pd.DataFrame(rows).merge(profs, on="professor", how="left")


# ---------- Travel ----------
def travel_minutes(travel: pd.DataFrame, a: str, b: str, mode: str) -> tuple[int, int] | None:
    """(typical, worst_case) minutes between two campuses, or None if we have no data."""
    if a == b:
        return (0, 0)
    prefix = "car" if mode == "Car" else "transit"
    m = travel[
        ((travel["from_campus"] == a) & (travel["to_campus"] == b))
        | ((travel["from_campus"] == b) & (travel["to_campus"] == a))
    ]
    if m.empty:
        return None
    typical, worst = m.iloc[0][f"{prefix}_typical"], m.iloc[0][f"{prefix}_worst"]
    if pd.isna(typical) or pd.isna(worst):
        return None
    return int(typical), int(worst)


# ---------- Checking a schedule ----------
def _label(m: dict) -> str:
    base = m["course_code"] + (f" {m['component']}" if m.get("multi") else "")
    if m["loc"] == "online":
        return f"{base} (online)"
    if m["loc"] == "maybe":
        return f"{base} ({m['campus']}, partly online)"
    return f"{base} ({m['campus']})"


def _days_text(days) -> str:
    seen = []
    for d in days:
        if d not in seen:
            seen.append(d)
    return ", ".join(DAY_NAMES[d] for d in sorted(seen, key=DAY_ORDER.index))


def _issue(kind: str, text: str, oids: list[str]) -> dict:
    return {"kind": kind, "tier": ISSUE_META[kind][0], "text": text, "oids": oids}


def _longest_free(start: int, end: int, blockers: list[tuple[int, int]]) -> int:
    """Longest stretch of minutes inside [start, end] not covered by the blocker intervals."""
    best, cursor = 0, start
    for b_start, b_end in sorted(blockers):
        best = max(best, min(b_start, end) - cursor)
        cursor = max(cursor, b_end)
    return max(best, end - cursor)


def check_schedule(meets: pd.DataFrame, offers: pd.DataFrame, travel: pd.DataFrame, transport="Car") -> list[dict]:
    """Returns problems as {"kind", "tier", "text", "oids"}, most serious first."""
    ms = expand(meets)
    timed = [m for m in ms if m["day"]]
    issues: list[dict] = []
    offer_rows = offers.to_dict("records")

    # Same course added twice (LEC + LAB are one offering, so they never trigger this)
    by_course: dict[str, list[str]] = {}
    for o in offer_rows:
        by_course.setdefault(o["course_code"], []).append(o["oid"])
    for code, oids in by_course.items():
        if len(oids) > 1:
            issues.append(_issue("duplicate", f"You added {len(oids)} different offerings of {code}. You only need one.", oids))

    # Full or almost-full
    for o in offer_rows:
        who = f"{o['course_code']} ({o['class_numbers']})"
        if o["seat_level"] == "full":
            issues.append(_issue(
                "seats_full",
                f"{who} is full and its waitlist is full too ({o['waitlist']}/{WAITLIST_CAPACITY}), so you can't "
                "enroll right now. Seat counts are a snapshot, so check live seats, but plan on another section.",
                [o["oid"]],
            ))
        elif o["seat_level"] == "waitlist":
            issues.append(_issue(
                "seats_waitlist",
                f"{who} is full. {o['waitlist']} of {WAITLIST_CAPACITY} waitlist spots are taken, so you'd be "
                f"#{int(o['waitlist']) + 1} on the waitlist. A waitlist doesn't guarantee a seat, so keep a backup plan.",
                [o["oid"]],
            ))
        elif o["seat_level"] == "few":
            issues.append(_issue("seats_few", f"{who} has only {o['seats_open']} seat(s) left and may fill up.", [o["oid"]]))

    # Professors with no ratings yet: one heads-up for the whole plan (an unknown, not a problem)
    unrated = [o for o in offer_rows if pd.isna(o.get("rmp_rating"))]
    if unrated:
        names = list(dict.fromkeys(o["professors_text"] for o in unrated))
        who_list = ", ".join(names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")
        issues.append(_issue(
            "unrated",
            f"No ratings yet for {who_list}. There's no way to tell how "
            f"{'this class' if len(unrated) == 1 else 'these classes'} will go, so it could turn out great or not.",
            [o["oid"] for o in unrated],
        ))

    # Pairs of meetings on the same day
    found: dict[tuple, list[dict]] = {}
    missing: dict[frozenset, tuple] = {}

    def add(a, b, kind, **details):
        found.setdefault((a["oid"], b["oid"], kind), []).append({"a": a, "b": b, **details})

    for i in range(len(timed)):
        for j in range(i + 1, len(timed)):
            a, b = timed[i], timed[j]
            if a["oid"] == b["oid"] or a["day"] != b["day"]:
                continue
            day = a["day"]
            if a["start"] < b["end"] and b["start"] < a["end"]:
                add(a, b, "overlap", day=day)
                continue
            first, second = (a, b) if a["end"] <= b["start"] else (b, a)
            gap = second["start"] - first["end"]
            if first["loc"] == "online" or second["loc"] == "online":
                continue  # an online class needs no trip
            if first["campus"] == second["campus"]:
                if gap < SAME_CAMPUS_MIN_GAP:
                    add(a, b, "rush" if gap < SAME_CAMPUS_RISKY_GAP else "close",
                        day=day, gap=gap, first=first, second=second)
                continue
            mode = mode_for(transport, day)
            trip = travel_minutes(travel, first["campus"], second["campus"], mode)
            if trip is None:
                missing.setdefault(frozenset((first["campus"], second["campus"])), (first, second))
                continue
            typical, worst = trip
            need = worst + EXTRA_BUFFER[mode]
            det = dict(day=day, gap=gap, typical=typical, worst=worst, need=need, first=first, second=second, mode=mode)
            partly = "maybe" in (first["loc"], second["loc"])
            if gap < typical:
                add(a, b, "maybe" if partly else "impossible", **det)
            elif gap < need:
                add(a, b, "maybe" if partly else "risky", **det)
            else:
                # The trip fits, but an online class might meet while you are travelling.
                blockers = [
                    (m["start"], m["end"]) for m in timed
                    if m["loc"] == "online" and m["day"] == day and m["start"] < second["start"] and m["end"] > first["end"]
                ]
                if blockers and _longest_free(first["end"], second["start"], blockers) < typical:
                    blocker = next(m for m in timed if m["loc"] == "online" and m["day"] == day
                                   and m["start"] < second["start"] and m["end"] > first["end"])
                    add(a, b, "online_trip", blocker=blocker, **det)

    for (oa, ob, kind), dets in found.items():
        d0 = dets[0]
        days = _days_text([d["day"] for d in dets])
        extras = "parking and walking" if d0.get("mode") == "Car" else "walking and waiting"
        if kind == "overlap":
            text = f"{_label(d0['a'])} and {_label(d0['b'])} overlap on {days}."
        elif kind == "close":
            text = (f"Only {d0['gap']} min between {_label(d0['first'])} and {_label(d0['second'])} on {days}. "
                    "That's a short walk, so it will be a bit tight.")
        elif kind == "rush":
            how = "Back to back" if d0["gap"] == 0 else f"Only {d0['gap']} min"
            text = (f"{how} between {_label(d0['first'])} and {_label(d0['second'])} on {days}. You'd have to "
                    "rush and might be late, even on the same campus.")
        else:
            f_, s_ = _label(d0["first"]), _label(d0["second"])
            c1, c2, md = d0["first"]["campus"], d0["second"]["campus"], d0["mode"].lower()
            if kind == "impossible":
                text = (f"Not enough travel time on {days}: {f_} ends and {s_} starts {d0['gap']} min later, "
                        f"but {c1} to {c2} takes about {d0['typical']} min by {md} even on a good day (plus {extras}).")
            elif kind == "risky":
                text = (f"Only {d0['gap']} min from {f_} to {s_} on {days}. The trip is about {d0['typical']} min on a "
                        f"good day but up to {d0['worst']} min in traffic or if you miss a connection, plus {extras}. "
                        f"You'd want ~{d0['need']} min to be safe.")
            elif kind == "maybe":
                text = (f"{f_} and {s_} are {d0['gap']} min apart on {days} at different campuses (the trip is "
                        f"{d0['typical']}-{d0['worst']} min by {md}). One of them is partially online and the schedule "
                        "doesn't say which days are on campus, so ask the instructor before counting on this.")
            else:  # online_trip
                text = (f"On {days}, {_label(d0['blocker'])} meets while you'd be travelling from {f_} to {s_}. "
                        "You would have to join from the road or a stop, or leave one class early.")
        issues.append(_issue(kind, text, [oa, ob]))

    for pair, (first, second) in missing.items():
        c1, c2 = sorted(pair)
        issues.append(_issue("no_data", f"No travel-time estimate for {c1} to {c2}, so the trip between "
                             f"{_label(first)} and {_label(second)} can't be checked.", [first["oid"], second["oid"]]))

    issues.sort(key=lambda x: -TIER_RANK[x["tier"]])
    return issues


def issue_title(issue: dict) -> str:
    icon, tier_label = TIER_LABELS[issue["tier"]]
    return f"{icon} {tier_label} · {ISSUE_META[issue['kind']][1]}"


def find_alternatives(offers_all, meets_all, plan_oids, travel, transport, issues) -> dict:
    """For each offering involved in a problem, find other offerings of the same course that
    would fit the rest of the plan with no problems (including seats). Best-rated first."""
    problem_oids = {o for i in issues if i["kind"] not in ("duplicate", "unrated") for o in i["oids"]}
    out: dict[str, pd.DataFrame] = {}
    for oid in problem_oids:
        current = offers_all[offers_all["oid"] == oid].iloc[0]
        base = [o for o in plan_oids if o != oid]
        good = []
        for _, cand in offers_all[
            (offers_all["course_code"] == current["course_code"]) & (offers_all["oid"] != oid)
        ].iterrows():
            if cand["oid"] in plan_oids:
                continue
            ids = base + [cand["oid"]]
            probs = check_schedule(meets_all[meets_all["oid"].isin(ids)], offers_all[offers_all["oid"].isin(ids)],
                                   travel, transport)
            if not any(cand["oid"] in p["oids"] for p in probs if p["kind"] != "unrated"):
                good.append(cand)
        if good:
            out[oid] = pd.DataFrame(good).sort_values("rmp_rating", ascending=False, na_position="last").head(3)
    return out


# ---------- Numbers for comparing plans ----------
def plan_stats(meets: pd.DataFrame, offers: pd.DataFrame, issues: list[dict]) -> dict:
    ms = [m for m in expand(meets)] if len(meets) else []
    on_campus = [m for m in ms if m["day"] and m["loc"] in ("in_person", "maybe")]
    times = [m for m in ms if m["day"]]
    count = lambda tier: sum(1 for i in issues if i["tier"] == tier)  # noqa: E731
    return {
        "classes": len(offers),
        "days": len({m["day"] for m in on_campus}),
        "campuses": len({m["campus"] for m in on_campus}),
        "earliest": min((m["start"] for m in times), default=None),
        "latest": max((m["end"] for m in times), default=None),
        "avg_rating": offers["rmp_rating"].mean() if len(offers) else float("nan"),
        "avg_difficulty": offers["rmp_difficulty"].mean() if len(offers) else float("nan"),
        "rated": int(offers["rmp_rating"].notna().sum()) if len(offers) else 0,  # classes whose professor has ratings
        "conflicts": count("conflict"),
        "risky": count("risky"),
        "heads_up": count("heads_up"),
    }


def required_status(offers: pd.DataFrame, required: list[str]) -> tuple[list[str], list[str]]:
    """(covered, missing) course codes from the student's 'must take' list for one plan."""
    have = set(offers["course_code"]) if len(offers) else set()
    return [c for c in required if c in have], [c for c in required if c not in have]


def plan_health(offers: pd.DataFrame, issues: list[dict]) -> str:
    """One emoji for the plan bar: empty, fine, risky, or has a conflict."""
    if offers.empty:
        return "⚪"
    tiers = {i["tier"] for i in issues}
    if "conflict" in tiers:
        return "🔴"
    if "risky" in tiers:
        return "🟡"
    return "🟢"


# ---------- Turning data into plain text (for the AI prompt) ----------
def offer_to_text(o: dict) -> str:
    rating = "NO RATINGS YET: professor quality is unknown, not good or bad" if pd.isna(o["rmp_rating"]) else (
        f"primary instructor RMP rating {o['rmp_rating']:.1f}/5, difficulty {o['rmp_difficulty']:.1f}/5, "
        f"{int(o['would_take_again_pct'])}% would take again"
    )
    lines = [f"- {o['course_code']} {o['course_name']} at {o['campus']} [{rating}], overall seats: "
             f"{o['seat_label'][2:].strip()}"]
    for c in o["components"]:
        when = "; ".join(meeting_text(*m) for m in c["meetings"]) or "no set meeting times"
        lines.append(f"    * {c['component']} class {c['class_number']}: {c['mode']}, instructor "
                     f"{c['professor'] or 'Staff'}, {when}, seats {c['seat_label'][2:].strip()}")
    return "\n".join(lines)


def schedule_to_text(offers: pd.DataFrame) -> str:
    return "\n".join(offer_to_text(o) for o in offers.to_dict("records"))


def issues_to_text(issues: list[dict]) -> str:
    if not issues:
        return "None found."
    return "\n".join(f"- [{i['tier'].upper()} / {ISSUE_META[i['kind']][1]}] {i['text']}" for i in issues)


def alternatives_to_text(alts: dict, offers_all: pd.DataFrame) -> str:
    if not alts:
        return "None needed or none available."
    lines = []
    for oid, df in alts.items():
        cur = offers_all[offers_all["oid"] == oid].iloc[0]
        lines.append(f"- Instead of {cur['course_code']} ({cur['class_numbers']}), these fit with no problems:")
        lines.extend(offer_to_text(o) for o in df.to_dict("records"))
    return "\n".join(lines)


def travel_to_text(travel: pd.DataFrame, campuses: list[str], transport) -> str:
    modes = sorted(set(transport.values())) if isinstance(transport, dict) else [transport]
    lines = []
    uniq = sorted(set(campuses))
    for x in range(len(uniq)):
        for y in range(x + 1, len(uniq)):
            for mode in modes:
                m = travel_minutes(travel, uniq[x], uniq[y], mode)
                if m is not None:
                    lines.append(f"- {uniq[x]} <-> {uniq[y]}: typically {m[0]} min, up to {m[1]} min in bad "
                                 f"conditions, by {mode.lower()}")
    return "\n".join(lines) or "Only one campus in this schedule."


def transport_to_text(transport) -> str:
    if isinstance(transport, dict):
        return ", ".join(f"{DAY_NAMES[d]}: {m}" for d, m in transport.items())
    return transport


def _stats_text(stats: dict) -> str:
    def t(m):
        return "n/a" if m is None else fmt_minutes(m)

    def n(x):
        return "n/a" if pd.isna(x) else f"{x:.1f}"

    return (
        f"Summary: {stats['classes']} classes, {stats['days']} days on campus per week (partially online "
        f"counted as on campus), {stats['campuses']} campus(es), earliest start {t(stats['earliest'])}, latest "
        f"end {t(stats['latest'])}, average professor rating {n(stats['avg_rating'])} (only {stats['rated']} of {stats['classes']} classes have a rated professor), average difficulty "
        f"{n(stats['avg_difficulty'])}, {stats['conflicts']} conflicts, {stats['risky']} risky, "
        f"{stats['heads_up']} heads-ups"
    )


def plans_to_text(plans: dict, active: str, offers: pd.DataFrame, meets: pd.DataFrame, travel: pd.DataFrame, transport,
                  required: list[str] | None = None) -> str:
    """Every plan (A, B, ...) with its classes and checker results, as text for the AI."""
    required = required or []
    blocks = []
    if required:
        blocks.append("Courses the student says they MUST take: " + ", ".join(required))
    else:
        blocks.append("The student has not told the site which courses they must take.")
    for name in sorted(plans):
        po = offers[offers["oid"].isin(plans[name])]
        pm = meets[meets["oid"].isin(plans[name])]
        tag = " (currently being viewed)" if name == active else ""
        if po.empty:
            blocks.append(f"{name}{tag}: empty")
            continue
        issues = check_schedule(pm, po, travel, transport)
        req_line = ""
        if required:
            have, lack = required_status(po, required)
            req_line = (f"Required courses covered by {name}: {len(have)} of {len(required)}"
                        + (f" (MISSING: {', '.join(lack)})" if lack else " (all covered)") + "\n")
        blocks.append(
            f"{name}{tag}:\n{schedule_to_text(po)}\n{req_line}{_stats_text(plan_stats(pm, po, issues))}\n"
            f"Checker results for {name}:\n{issues_to_text(issues)}\n"
            f"Travel estimates for {name}:\n{travel_to_text(travel, list(po['campus']), transport)}"
        )
    return "\n\n".join(blocks)


def catalog_to_text(offers: pd.DataFrame, limit: int = 120) -> str:
    """Compact list of every available offering so the AI can answer 'what's offered?'."""
    lines = []
    for o in offers.head(limit).to_dict("records"):
        rating = "unrated" if pd.isna(o["rmp_rating"]) else f"{o['rmp_rating']:.1f}/5"
        parts = []
        for c in o["components"]:
            when = "; ".join(meeting_text(*m) for m in c["meetings"]) or "no set times"
            parts.append(f"{c['component']} {c['class_number']} {c['mode']} {when}")
        lines.append(f"{o['course_code']} | {o['professors_text']} ({rating}) | {o['campus']} | "
                     f"{' + '.join(parts)} | seats {o['seat_label'][2:].strip()}")
    return "\n".join(lines)


# ---------- "What matters most to me": which plan wins each priority (calculated here, not guessed by the AI) ----------
_COMMUTE_KINDS = {"impossible", "risky", "maybe", "online_trip", "no_data", "rush"}
_SEAT_KINDS = {"seats_full", "seats_waitlist", "seats_few"}


def priorities_to_text(plans: dict, offers: pd.DataFrame, meets: pd.DataFrame, travel: pd.DataFrame, transport,
                       priorities: list[str], required: list[str] | None = None) -> str:
    """For each priority the student ticked, says which plan is best on it (computed, so the AI doesn't have to)."""
    rows = {}
    for name in sorted(plans):
        po = offers[offers["oid"].isin(plans[name])]
        if po.empty:
            continue
        pm = meets[meets["oid"].isin(plans[name])]
        issues = check_schedule(pm, po, travel, transport)
        rows[name] = (plan_stats(pm, po, issues), issues, po)
    if len(rows) < 2 or not priorities:
        return ""

    def count(issues, kinds):
        return sum(1 for i in issues if i["kind"] in kinds)

    # priority -> (value of a plan, True if a higher value is better, text for the value)
    rules = {
        "Best-rated professors": (lambda s, i: s["avg_rating"], True, lambda s, i, v: f"average professor rating {v:.1f}"),
        "Easier classes (lower difficulty)": (lambda s, i: s["avg_difficulty"], False,
                                              lambda s, i, v: f"average difficulty {v:.1f}"),
        "Fewest days on campus": (lambda s, i: s["days"], False, lambda s, i, v: f"{v} day(s) on campus per week"),
        "Shortest commutes and fewest campuses": (
            lambda s, i: s["campuses"] * 10 + count(i, _COMMUTE_KINDS), False,
            lambda s, i, v: f"{s['campuses']} campus(es) and {count(i, _COMMUTE_KINDS)} commute problem(s)"),
        "No early mornings": (lambda s, i: s["earliest"] if s["earliest"] is not None else 24 * 60, True,
                              lambda s, i, v: f"earliest start {fmt_minutes(v) if v < 24 * 60 else 'none'}"),
        "No late evenings": (lambda s, i: s["latest"] if s["latest"] is not None else 0, False,
                             lambda s, i, v: f"latest end {fmt_minutes(v) if v else 'none'}"),
        "Classes with open seats": (lambda s, i: count(i, _SEAT_KINDS), False,
                                    lambda s, i, v: f"{v} full or almost-full class(es)"),
    }
    lines = []
    for rank, prio in enumerate(priorities, start=1):  # priorities arrive ranked: #1 = most important
        if prio not in rules:
            continue
        value, higher_better, describe = rules[prio]
        vals = {n: value(s, i) for n, (s, i, _po) in rows.items()}
        vals = {n: v for n, v in vals.items() if v is not None and not pd.isna(v)}
        if len(vals) < 2:
            continue
        rounded = {n: round(v, 1) for n, v in vals.items()}
        best = (max if higher_better else min)(rounded.values())
        winners = [n for n, v in rounded.items() if v == best]
        detail = "; ".join(f"{n}: {describe(rows[n][0], rows[n][1], vals[n])}" for n in vals)
        verdict = "TIE (no difference)" if len(winners) == len(vals) else f"BEST = {', '.join(winners)}"
        lines.append(f"- #{rank} {prio}: {verdict} ({detail})")
    if required:
        covered = {n: len(required_status(po, required)[0]) for n, (_s, _i, po) in rows.items()}
        lines.append("- Required courses covered: " + "; ".join(f"{n}: {c} of {len(required)}" for n, c in covered.items()))
    return ("PRIORITY RESULTS (calculated by the site and correct; your recommendation must follow them, weighing a "
            "lower-numbered priority more than a higher-numbered one, and a plan that covers more required courses "
            "still comes first):\n" + "\n".join(lines)) if lines else ""
