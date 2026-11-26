"""Business logic: standings, warnings, summaries, search (pure functions, fully unit-tested)."""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

from .config import INACTIVE_DAYS, MIN_FOR_STATS, POINTS, Z_THRESHOLD


def team_results(matches):
    """team -> chronological list of (match, 'W'/'D'/'L', scored, conceded)."""
    res = defaultdict(list)
    for m in sorted(matches, key=lambda x: (x.date, x.id)):
        h, a = m.home_score, m.away_score
        rh, ra = ("W", "L") if h > a else ("L", "W") if a > h else ("D", "D")
        res[m.home_team].append((m, rh, h, a))
        res[m.away_team].append((m, ra, a, h))
    return res


def standings(matches):
    """Ranked table rows. Sort: points, goal difference, scored, name."""
    rows = []
    for team, games in team_results(matches).items():
        w = sum(1 for g in games if g[1] == "W")
        d = sum(1 for g in games if g[1] == "D")
        l = sum(1 for g in games if g[1] == "L")
        gf, ga = sum(g[2] for g in games), sum(g[3] for g in games)
        p = len(games)
        rows.append({
            "team": team, "P": p, "W": w, "D": d, "L": l, "GF": gf, "GA": ga,
            "GD": gf - ga, "Pts": w * POINTS["W"] + d * POINTS["D"],
            "Win%": round(100 * w / p, 1), "Avg": round(gf / p, 2),
            "Form": "".join(g[1] for g in games[-5:]),
        })
    rows.sort(key=lambda r: (-r["Pts"], -r["GD"], -r["GF"], r["team"]))
    for i, r in enumerate(rows, 1):
        r["Rank"] = i
    return rows


def fmt_standings(rows) -> str:
    head = f"{'#':>2}  {'Team':<20}{'P':>3}{'W':>3}{'D':>3}{'L':>3}{'GF':>6}{'GA':>6}{'GD':>6}{'Pts':>5}{'Win%':>7}{'Avg':>7}  Form"
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(f"{r['Rank']:>2}  {r['team'][:19]:<20}{r['P']:>3}{r['W']:>3}{r['D']:>3}{r['L']:>3}"
                     f"{r['GF']:>6}{r['GA']:>6}{r['GD']:>+6}{r['Pts']:>5}{r['Win%']:>7.1f}{r['Avg']:>7.2f}  {r['Form']}")
    return "\n".join(lines)


def fmt_matches(rows) -> str:
    head = f"{'ID':>3}  {'Date':<10}  {'Sport':<11}{'Home':<19}{'Score':^11}{'Away':<19}"
    lines = [head, "-" * len(head)]
    for m in rows:
        lines.append(f"{m.id:>3}  {m.date:<10}  {m.sport[:10]:<11}{m.home_team[:18]:<19}"
                     f"{m.home_score:>3} - {m.away_score:<3}  {m.away_team[:18]:<19}")
    return "\n".join(lines)




def find_warnings(matches) -> list[str]:
    out = []
    # 1. duplicates
    seen = {}
    for m in matches:
        key = (m.date, m.sport.casefold(), m.home_team.casefold(), m.away_team.casefold())
        if key in seen:
            out.append(f"Possible duplicate: match #{m.id} repeats #{seen[key]} ({m.home_team} v {m.away_team}, {m.date})")
        seen.setdefault(key, m.id)
    # 2. statistical anomalies per sport
    by_sport = defaultdict(list)
    for m in matches:
        by_sport[m.sport].append(m)
    for sport, ms in by_sport.items():
        if len(ms) < MIN_FOR_STATS:
            continue
        for label, fn, two_sided in (("total score", lambda x: x.total, True),
                                     ("winning margin", lambda x: x.margin, False)):
            vals = [fn(m) for m in ms]
            mu, sd = statistics.mean(vals), statistics.pstdev(vals)
            if sd == 0:
                continue
            for m in ms:
                z = (fn(m) - mu) / sd
                if z >= Z_THRESHOLD or (two_sided and z <= -Z_THRESHOLD):
                    out.append(f"Anomalous {label} in {sport}: #{m.id} {m.home_team} {m.home_score}-{m.away_score} "
                               f"{m.away_team} ({fn(m)} vs avg {mu:.1f}, z={z:.1f})")
    # 3. inactive teams (overdue)
    today = date.today()
    for team, games in team_results(matches).items():
        last = datetime.strptime(games[-1][0].date, "%Y-%m-%d").date()
        if today - last > timedelta(days=INACTIVE_DAYS):
            out.append(f"Inactive team: {team} has not played for {(today - last).days} days (last: {last})")
    return out


def summary_lines(matches) -> list[str]:
    """Executive summary. Score metrics are computed per sport because
    scales differ (a basketball total is not comparable to a hockey total)."""
    if not matches:
        return ["No matches recorded yet."]
    n = len(matches)
    teams = team_results(matches)
    dates = sorted(m.date for m in matches)
    sports = sorted({m.sport for m in matches})
    L = [
        f"Matches recorded : {n}",
        f"Teams            : {len(teams)}",
        f"Sports           : {', '.join(sports)}",
        f"Date range       : {dates[0]} to {dates[-1]}",
    ]
    for sport in sports:
        ms = [m for m in matches if m.sport == sport]
        totals = [m.total for m in ms]
        oc = defaultdict(int)
        for m in ms:
            oc[m.outcome] += 1
        k = len(ms)
        top_t = max(ms, key=lambda m: m.total)
        top_m = max(ms, key=lambda m: m.margin)
        rows = standings(ms)
        lead = rows[0]
        L += [
            "",
            f"[{sport}]  {k} matches, {len(rows)} teams",
            f"  Total scored     : {sum(totals)}  (avg/match {statistics.mean(totals):.2f}, median {statistics.median(totals):.1f})",
            f"  Avg home / away  : {statistics.mean(m.home_score for m in ms):.2f} / {statistics.mean(m.away_score for m in ms):.2f}",
            f"  Results          : Home {oc['Home']} ({100*oc['Home']/k:.0f}%), Draw {oc['Draw']} ({100*oc['Draw']/k:.0f}%), Away {oc['Away']} ({100*oc['Away']/k:.0f}%)",
            f"  Highest scoring  : #{top_t.id} {top_t.home_team} {top_t.home_score}-{top_t.away_score} {top_t.away_team} ({top_t.total})",
            f"  Biggest margin   : #{top_m.id} {top_m.home_team} {top_m.home_score}-{top_m.away_score} {top_m.away_team} (+{top_m.margin})",
            f"  Leader           : {lead['team']} ({lead['Pts']} pts, {lead['Win%']}% wins, form {lead['Form']})",
        ]
        formed = [r for r in rows if r["P"] >= 3]
        if formed:
            def form_pts(r): return sum(POINTS[x] for x in r["Form"]) / len(r["Form"])
            hot, cold = max(formed, key=form_pts), min(formed, key=form_pts)
            L.append(f"  Hottest / coldest: {hot['team']} ({hot['Form']}) / {cold['team']} ({cold['Form']})")
        if k >= 10:
            ordered = sorted(ms, key=lambda m: (m.date, m.id))
            recent = statistics.mean(m.total for m in ordered[-5:])
            prev = statistics.mean(m.total for m in ordered[-10:-5])
            arrow = "▲ rising" if recent > prev * 1.05 else "▼ falling" if recent < prev * 0.95 else "► steady"
            L.append(f"  Scoring trend    : last 5 avg {recent:.1f} vs previous 5 avg {prev:.1f}  {arrow}")
        else:
            L.append("  Scoring trend    : needs 10+ matches in this sport")
    L += ["", f"Warnings         : {len(find_warnings(matches))}  (see menu option 11)"]
    return L


def search(matches, keyword="", sport="", outcome="", date_from=None, date_to=None):
    res = []
    for m in matches:
        if keyword and keyword.casefold() not in f"{m.home_team} {m.away_team} {m.sport}".casefold():
            continue
        if sport and m.sport.casefold() != sport.casefold():
            continue
        if outcome and m.outcome != outcome:
            continue
        if date_from and m.date < date_from.isoformat():
            continue
        if date_to and m.date > date_to.isoformat():
            continue
        res.append(m)
    return sorted(res, key=lambda m: (m.date, m.id))
