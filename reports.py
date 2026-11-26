"""Report export (Markdown / TXT / CSV) and bulk CSV import with row-level error log."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from . import config
from .analytics import find_warnings, fmt_standings, standings, summary_lines
from .config import REQUIRED_COLS
from .models import parse_record
from .storage import BaseStore


def sport_standings_text(matches) -> str:
    parts = []
    for sport in sorted({m.sport for m in matches}):
        parts.append(f"{sport}\n{fmt_standings(standings([m for m in matches if m.sport == sport]))}")
    return "\n\n".join(parts)


def export_reports(matches, out_dir=None) -> list[Path]:
    out_dir = Path(out_dir) if out_dir else config.REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    warnings = find_warnings(matches)
    files = []

    md = [f"# Sports Score Analyzer Report\n\n_Generated {stamp}_\n", "## Executive Summary\n", "```"]
    md += summary_lines(matches) + ["```\n"]
    for sport in sorted({m.sport for m in matches}):
        rows = standings([m for m in matches if m.sport == sport])
        md.append(f"## {sport} Standings\n")
        md.append("| # | Team | P | W | D | L | GF | GA | GD | Pts | Win% | Avg | Form |")
        md.append("|---|------|---|---|---|---|----|----|----|-----|------|-----|------|")
        for r in rows:
            md.append(f"| {r['Rank']} | {r['team']} | {r['P']} | {r['W']} | {r['D']} | {r['L']} | {r['GF']} | {r['GA']} "
                      f"| {r['GD']:+d} | {r['Pts']} | {r['Win%']} | {r['Avg']} | {r['Form']} |")
        md.append("")
    md.append("## Warnings\n")
    md += [f"- {w}" for w in warnings] or ["- None"]
    p = out_dir / f"report_{ts}.md"
    p.write_text("\n".join(md) + "\n", encoding="utf-8")
    files.append(p)

    log = [f"SPORTS SCORE ANALYZER AUDIT LOG  |  generated {stamp}", "=" * 70, "MATCH RECORDS"]
    log += [f"[{m.id:03d}] {m.date} {m.sport:<10} {m.home_team} {m.home_score}-{m.away_score} {m.away_team}"
            for m in sorted(matches, key=lambda x: (x.date, x.id))]
    log += ["", "WARNINGS"] + (warnings or ["none"]) + ["", "SUMMARY"] + summary_lines(matches)
    p = out_dir / f"audit_log_{ts}.txt"
    p.write_text("\n".join(log) + "\n", encoding="utf-8")
    files.append(p)

    p = out_dir / f"standings_{ts}.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sport", "rank", "team", "played", "wins", "draws", "losses", "gf", "ga", "gd", "points", "win_pct", "avg_scored", "form"])
        for sport in sorted({m.sport for m in matches}):
            for r in standings([m for m in matches if m.sport == sport]):
                w.writerow([sport, r["Rank"], r["team"], r["P"], r["W"], r["D"], r["L"], r["GF"], r["GA"], r["GD"], r["Pts"], r["Win%"], r["Avg"], r["Form"]])
    files.append(p)

    p = out_dir / f"matches_{ts}.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", *REQUIRED_COLS])
        for m in sorted(matches, key=lambda x: (x.date, x.id)):
            w.writerow([m.id, m.date, m.sport, m.home_team, m.away_team, m.home_score, m.away_score])
    files.append(p)
    return files


def import_csv(store: "BaseStore", path: Path, out_dir=None) -> tuple[int, int, Path | None]:
    out_dir = Path(out_dir) if out_dir else config.REPORT_DIR
    added, skipped, errors = 0, 0, []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
        missing = [col for col in REQUIRED_COLS if col not in cols]
        if missing:
            raise ValueError(f"missing required column(s): {', '.join(missing)}")
        reader.fieldnames = cols
        for line_no, row in enumerate(reader, start=2):
            try:
                m = parse_record(row)
                m.home_team, m.away_team = store.canon_team(m.home_team), store.canon_team(m.away_team)
                if store.is_duplicate(m):
                    raise ValueError("duplicate of an existing match")
                store.add(m)
                added += 1
            except ValueError as e:
                skipped += 1
                errors.append(f"line {line_no}: {e} | raw={dict(row)}")
    log_path = None
    if errors:
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / f"import_errors_{datetime.now():%Y%m%d_%H%M%S}.log"
        log_path.write_text(f"Import of {path.name}: {added} added, {skipped} rejected\n" + "\n".join(errors) + "\n", encoding="utf-8")
    return added, skipped, log_path
