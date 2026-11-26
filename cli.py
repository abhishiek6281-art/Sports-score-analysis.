"""Command-line interface: menu loop wiring user actions to the business logic."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

from . import __version__, config
from .analytics import (find_warnings, fmt_matches, fmt_standings, search, standings,
                        summary_lines, team_results)
from .charts import make_charts
from .config import BASE_DIR, MAX_SCORE, NAME_RE, REQUIRED_COLS, SAMPLE_FILE, SPORT_RE
from .log import LOG, setup_logging
from .models import Match, parse_date, parse_record
from .reports import export_reports, import_csv
from .storage import BaseStore, open_store
from .ui import (Cancel, ask, ask_date, ask_int, ask_text, ask_yes, c, err, heading, ok,
                 pause, paginate, warn)


def _rel(p: Path) -> str:
    try:
        return str(Path(p).relative_to(BASE_DIR))
    except ValueError:
        return str(p)


def choose_sport(store: BaseStore, allow_all=True) -> str:
    sports = store.sports
    if not sports:
        return ""
    label = f"  Sport ({', '.join(sports)}{', blank = all' if allow_all else ''}): "
    while True:
        s = ask(label)
        if not s and allow_all:
            return ""
        match = next((x for x in sports if x.casefold() == s.casefold()), None)
        if match:
            return match
        err("Unknown sport. Pick one from the list.")


def do_add(store: BaseStore):
    heading("Add match  (type /cancel at any prompt to abort)")
    if store.sports:
        print(f"  Existing sports: {', '.join(store.sports)}")
    sport = ask_text("  Sport: ", SPORT_RE, "Sport must be 2-20 letters (spaces allowed).").title()
    home = store.canon_team(ask_text("  Home team: ", NAME_RE, "Team name: 2-30 chars (letters, digits, space . & ' -)."))
    while True:
        away = store.canon_team(ask_text("  Away team: ", NAME_RE, "Team name: 2-30 chars (letters, digits, space . & ' -)."))
        if away.casefold() != home.casefold():
            break
        err("Away team must differ from the home team.")
    hs = ask_int(f"  {home} score (0-{MAX_SCORE}): ", 0, MAX_SCORE)
    aws = ask_int(f"  {away} score (0-{MAX_SCORE}): ", 0, MAX_SCORE)
    d = ask_date("  Date YYYY-MM-DD (blank = today): ")
    m = Match(0, d.isoformat(), sport, home, away, hs, aws)
    print(f"\n  {m.date} | {sport} | {home} {hs} - {aws} {away}")
    if store.is_duplicate(m):
        warn("An identical fixture already exists for that date.")
    if not ask_yes("  Save this match?"):
        print("  Discarded.")
        return
    m = store.add(m)
    ok(f"Saved as match #{m.id}.")
    for w in find_warnings(store.matches):
        if f"#{m.id} " in w or f"#{m.id})" in w:
            warn(w)


def do_view(store: BaseStore):
    heading("All matches")
    paginate(sorted(store.matches, key=lambda m: (m.date, m.id)), fmt_matches)


def do_search(store: BaseStore):
    heading("Search / filter  (leave a filter blank to skip it)")
    kw = ask("  Keyword (team or sport): ")
    sport = choose_sport(store)
    outcome = ""
    while True:
        outcome = ask("  Result (Home / Away / Draw, blank = any): ").title()
        if outcome in ("", "Home", "Away", "Draw"):
            break
        err("Enter Home, Away, Draw or leave blank.")
    dates = []
    for lab in ("  From date (YYYY-MM-DD): ", "  To date (YYYY-MM-DD): "):
        while True:
            raw = ask(lab)
            if not raw:
                dates.append(None)
                break
            try:
                dates.append(parse_date(raw))
                break
            except ValueError as e:
                err(str(e))
    res = search(store.matches, kw, sport, outcome, dates[0], dates[1])
    print(f"\n  {len(res)} match(es) found.")
    paginate(res, fmt_matches)


def do_rankings(store: BaseStore):
    heading("Rankings (W=3, D=1, L=0; tie-break: goal difference, then scored)")
    if not store.matches:
        print("  No data yet.")
        return
    sport = choose_sport(store)
    for s in ([sport] if sport else store.sports):
        print(c(f"\n  {s}", "1"))
        print("\n".join("  " + ln for ln in fmt_standings(standings([m for m in store.matches if m.sport == s])).split("\n")))


def do_summary(store: BaseStore):
    heading("Executive summary")
    for ln in summary_lines(store.matches):
        print("  " + ln)


def do_team(store: BaseStore):
    heading("Team profile")
    name = ask("  Team name: ")
    team = next((t for t in team_results(store.matches) if t.casefold() == name.casefold()), None)
    if not team:
        err("Team not found.")
        return
    games = team_results(store.matches)[team]
    rows = [r for s in store.sports for r in standings([m for m in store.matches if m.sport == s]) if r["team"] == team]
    r = rows[0]
    print(f"\n  {team}: P{r['P']} W{r['W']} D{r['D']} L{r['L']} | scored {r['GF']} (avg {r['Avg']}) conceded {r['GA']} | {r['Win%']}% wins | form {r['Form']}")
    print()
    for m, res, f, a in games[-10:]:
        opp = m.away_team if m.home_team == team else m.home_team
        print(f"  {m.date}  {res}  {f}-{a} vs {opp} ({'H' if m.home_team == team else 'A'})")


def do_charts(store: BaseStore):
    heading("Charts")
    files = make_charts(store.matches)
    for p in files:
        ok(f"Saved {_rel(p)}")


def do_export(store: BaseStore):
    heading("Export reports")
    if not store.matches:
        warn("Nothing to export yet.")
        return
    for p in export_reports(store.matches):
        ok(f"Saved {_rel(p)}")
    if ask_yes("  Also generate charts?"):
        do_charts(store)


def do_import(store: BaseStore):
    heading("Bulk CSV import")
    print("  Required columns: " + ", ".join(REQUIRED_COLS))
    raw = ask("  Path to CSV file: ").strip('"\'')
    path = Path(raw).expanduser()
    if not path.is_file():
        err("File not found.")
        return
    try:
        added, skipped, log = import_csv(store, path)
    except (ValueError, OSError, csv.Error, UnicodeDecodeError) as e:
        err(f"Import failed: {e}")
        return
    ok(f"{added} row(s) imported.")
    if skipped:
        warn(f"{skipped} row(s) rejected. Details: {_rel(log)}")


def do_delete(store: BaseStore):
    heading("Delete match")
    if not store.matches:
        print("  No data yet.")
        return
    mid = ask_int("  Match ID to delete: ", 1, 10**9)
    m = next((x for x in store.matches if x.id == mid), None)
    if not m:
        err(f"No match with ID {mid}.")
        return
    print(f"  #{m.id} {m.date} {m.home_team} {m.home_score}-{m.away_score} {m.away_team}")
    if ask_yes("  Delete permanently?"):
        store.delete(mid)
        ok("Deleted.")


def do_warnings(store: BaseStore):
    heading("Threshold warnings")
    w = find_warnings(store.matches)
    if not w:
        ok("No warnings. All entries look normal.")
    for line in w:
        warn(line)


BANNER = r"""
  ╔══════════════════════════════════════════════╗
  ║        ⚽  SPORTS SCORE ANALYZER  🏀           ║
  ║   Store scores · Wins · Averages · Rankings  ║
  ╚══════════════════════════════════════════════╝"""

MENU = [
    ("1", "Add match", do_add),
    ("2", "View all matches", do_view),
    ("3", "Search / filter", do_search),
    ("4", "Rankings", do_rankings),
    ("5", "Executive summary", do_summary),
    ("6", "Team profile", do_team),
    ("7", "Generate charts", do_charts),
    ("8", "Export reports (MD / TXT / CSV)", do_export),
    ("9", "Bulk import CSV", do_import),
    ("10", "Delete match", do_delete),
    ("11", "Threshold warnings", do_warnings),
]


def seed(store: BaseStore):
    try:
        data = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        err("Sample dataset not found or unreadable.")
        return
    added = 0
    for rec in data.get("matches", []):
        try:
            m = parse_record(rec)
        except ValueError:
            continue
        if not store.is_duplicate(m):
            store.add(m)
            added += 1
    ok(f"Seeded {added} sample match(es).")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ssa", description="Sports Score Analyzer: store scores, wins, averages, rankings.")
    p.add_argument("--seed", action="store_true", help="load the bundled sample dataset on start")
    p.add_argument("--backend", choices=("sqlite", "json"), default="sqlite", help="storage backend (default: sqlite)")
    p.add_argument("--data-dir", type=Path, help="folder for the database/JSON file and reports/")
    p.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.data_dir:
        config.DATA_DIR = args.data_dir
        config.REPORT_DIR = args.data_dir / "reports"
    setup_logging(args.log_level, config.REPORT_DIR / "ssa.log")
    print(c(BANNER, "1;32"))
    store = open_store(args.backend, config.DATA_DIR)
    LOG.debug("Started with backend=%s, %d matches", args.backend, len(store.matches))
    if args.seed:
        seed(store)
    actions = {k: fn for k, _, fn in MENU}
    try:
        while True:
            n_warn = len(find_warnings(store.matches))
            print(f"\n  {len(store.matches)} matches stored" + (c(f"  |  ⚠ {n_warn} warning(s)", "33") if n_warn else ""))
            for k, label, _ in MENU:
                print(f"   {k:>2}. {label}")
            print("    0. Exit")
            try:
                choice = input(c("\n  Choose an option: ", "1")).strip()
            except EOFError:
                choice = "0"
            except KeyboardInterrupt:
                print()
                choice = "0"
            if choice == "0":
                print("  Data saved. Goodbye!")
                return 0
            action = actions.get(choice)
            if not action:
                err("Invalid choice. Enter a number from the menu.")
                continue
            try:
                action(store)
            except Cancel:
                print("  Cancelled.")
            except (KeyboardInterrupt, EOFError):
                print("\n  Cancelled.")
            except OSError as e:
                LOG.exception("File error")
                err(f"File error: {e}")
            except Exception:  # last line of defence: log with traceback, keep the app alive
                LOG.exception("Unexpected error in menu action %s", choice)
                err("Unexpected error (details written to reports/ssa.log).")
            pause()
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
