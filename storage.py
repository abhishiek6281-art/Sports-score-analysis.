"""Persistence layer: a common BaseStore interface with JSON and SQLite backends.

* JsonStore   - flat file, atomic writes, corruption recovery (original backend)
* SqliteStore - relational backend: CHECK/UNIQUE constraints, indexes, schema version,
                corruption recovery, one-off migration from the JSON file
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .config import DATA_FILE, DB_FILE, MAX_SCORE
from .log import LOG
from .models import Match, parse_record

SCHEMA_VERSION = 1
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS matches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT    NOT NULL CHECK (date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    sport      TEXT    NOT NULL COLLATE NOCASE,
    home_team  TEXT    NOT NULL COLLATE NOCASE,
    away_team  TEXT    NOT NULL COLLATE NOCASE,
    home_score INTEGER NOT NULL CHECK (home_score BETWEEN 0 AND {MAX_SCORE}),
    away_score INTEGER NOT NULL CHECK (away_score BETWEEN 0 AND {MAX_SCORE}),
    CHECK (home_team <> away_team),
    UNIQUE (date, sport, home_team, away_team)
);
CREATE INDEX IF NOT EXISTS idx_matches_date  ON matches (date);
CREATE INDEX IF NOT EXISTS idx_matches_sport ON matches (sport);
CREATE INDEX IF NOT EXISTS idx_matches_home  ON matches (home_team);
CREATE INDEX IF NOT EXISTS idx_matches_away  ON matches (away_team);
"""


class BaseStore:
    """Shared behaviour. Subclasses implement load/save/add/delete."""

    path: Path
    matches: list[Match]

    def load(self) -> None: raise NotImplementedError
    def save(self) -> None: raise NotImplementedError
    def add(self, m: Match) -> Match: raise NotImplementedError
    def delete(self, mid: int) -> bool: raise NotImplementedError
    def close(self) -> None: pass

    def next_id(self) -> int:
        return max((m.id for m in self.matches), default=0) + 1

    def canon_team(self, name: str) -> str:
        """Reuse the existing spelling/case of a team if it is already known."""
        for m in self.matches:
            for t in (m.home_team, m.away_team):
                if t.casefold() == name.casefold():
                    return t
        return name

    def is_duplicate(self, m: Match) -> bool:
        key = (m.date, m.sport.casefold(), m.home_team.casefold(), m.away_team.casefold())
        return any((x.date, x.sport.casefold(), x.home_team.casefold(), x.away_team.casefold()) == key
                   for x in self.matches)

    @property
    def sports(self) -> list[str]:
        return sorted({m.sport for m in self.matches})


class JsonStore(BaseStore):
    def __init__(self, path: Path = DATA_FILE):
        self.path = Path(path)
        self.matches = []
        self.load()

    def load(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.matches = []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("matches"), list):
                raise ValueError("unexpected file structure")
        except FileNotFoundError:
            LOG.debug("No data file at %s; creating a fresh one", self.path)
            self.save()
            return
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as e:
            backup = self.path.with_suffix(f".corrupt-{datetime.now():%Y%m%d%H%M%S%f}.json")
            try:
                self.path.rename(backup)
                LOG.warning("Data file was unreadable (%s). Backed up to %s; starting fresh.", e, backup.name)
            except OSError:
                LOG.warning("Data file was unreadable (%s); starting fresh.", e)
            self.save()
            return
        skipped = 0
        for rec in raw["matches"]:
            try:
                self.matches.append(parse_record(rec, int(rec.get("id", 0))))
            except (ValueError, AttributeError, TypeError):
                skipped += 1
        if skipped:
            LOG.warning("Skipped %d invalid record(s) while loading.", skipped)

    def save(self) -> None:
        payload = {"version": 1, "matches": [asdict(m) for m in self.matches]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)  # atomic swap so a crash cannot corrupt the file

    def add(self, m: Match) -> Match:
        m.id = self.next_id()
        m.home_team, m.away_team = self.canon_team(m.home_team), self.canon_team(m.away_team)
        self.matches.append(m)
        self.save()
        return m

    def delete(self, mid: int) -> bool:
        before = len(self.matches)
        self.matches = [m for m in self.matches if m.id != mid]
        if len(self.matches) != before:
            self.save()
            return True
        return False


class SqliteStore(BaseStore):
    def __init__(self, path: Path = DB_FILE, migrate_from: Path | None = None):
        self.path = Path(path)
        self.matches = []
        self.conn: sqlite3.Connection | None = None
        is_new = not self.path.exists()
        self._open()
        if migrate_from and is_new and Path(migrate_from).exists():
            self.migrate_json(Path(migrate_from))
        self.load()

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.conn = sqlite3.connect(self.path)
            self.conn.executescript(SCHEMA)
            if self.conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("integrity check failed")
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.conn.commit()
        except sqlite3.DatabaseError as e:
            if self.conn:
                self.conn.close()
            backup = self.path.with_suffix(f".corrupt-{datetime.now():%Y%m%d%H%M%S%f}.db")
            try:
                self.path.rename(backup)
                LOG.warning("Database was unreadable (%s). Backed up to %s; starting fresh.", e, backup.name)
            except OSError:
                LOG.warning("Database was unreadable (%s); starting fresh.", e)
            self.conn = sqlite3.connect(self.path)
            self.conn.executescript(SCHEMA)
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.conn.commit()

    def load(self) -> None:
        rows = self.conn.execute(
            "SELECT id, date, sport, home_team, away_team, home_score, away_score FROM matches ORDER BY date, id")
        self.matches = [Match(*r) for r in rows]

    def save(self) -> None:
        self.conn.commit()

    def add(self, m: Match) -> Match:
        m.home_team, m.away_team = self.canon_team(m.home_team), self.canon_team(m.away_team)
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO matches (date, sport, home_team, away_team, home_score, away_score) VALUES (?,?,?,?,?,?)",
                    (m.date, m.sport, m.home_team, m.away_team, m.home_score, m.away_score))
        except sqlite3.IntegrityError as e:
            raise ValueError(f"database rejected the record: {e}") from e
        m.id = cur.lastrowid
        self.load()
        return m

    def delete(self, mid: int) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM matches WHERE id = ?", (mid,))
        self.load()
        return cur.rowcount > 0

    def migrate_json(self, json_path: Path) -> int:
        """Import a legacy matches.json; invalid and duplicate rows are skipped. Returns rows added."""
        try:
            raw = json.loads(Path(json_path).read_text(encoding="utf-8"))
            records = raw["matches"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            LOG.warning("Could not migrate %s (%s).", json_path, e)
            return 0
        self.load()
        added = 0
        for rec in records:
            try:
                m = parse_record(rec)
                self.add(m)
                added += 1
            except (ValueError, AttributeError, TypeError):
                continue
        LOG.info("Migrated %d match(es) from %s into SQLite.", added, Path(json_path).name)
        return added

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None


def open_store(backend: str = "sqlite", data_dir: Path | None = None) -> BaseStore:
    """Factory used by the CLI. The sqlite backend auto-migrates an existing matches.json once."""
    from . import config
    d = Path(data_dir) if data_dir else config.DATA_DIR
    if backend == "json":
        return JsonStore(d / "matches.json")
    return SqliteStore(d / "matches.db", migrate_from=d / "matches.json")


Store = JsonStore  # backwards-compatible alias
