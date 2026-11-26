"""Domain model and validation (pure functions: no I/O, no printing)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .config import DATE_FORMATS, MAX_SCORE, NAME_RE, SPORT_RE


def parse_date(raw: str) -> date:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{raw}' is not a valid date (use YYYY-MM-DD)")


@dataclass
class Match:
    id: int
    date: str
    sport: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int

    @property
    def total(self) -> int:
        return self.home_score + self.away_score

    @property
    def margin(self) -> int:
        return abs(self.home_score - self.away_score)

    @property
    def outcome(self) -> str:
        if self.home_score > self.away_score:
            return "Home"
        if self.away_score > self.home_score:
            return "Away"
        return "Draw"


def parse_record(d: dict, mid: int = 0) -> Match:
    """Validate a raw dict and build a Match. Raises ValueError listing every problem."""
    problems = []

    def get(key):
        v = d.get(key)
        return " ".join(str(v).split()) if v is not None else ""

    sport = get("sport")
    home, away = get("home_team"), get("away_team")
    if not SPORT_RE.fullmatch(sport):
        problems.append("sport must be 2-20 letters")
    for label, name in (("home_team", home), ("away_team", away)):
        if not NAME_RE.fullmatch(name):
            problems.append(f"{label} is invalid or blank")
    if home and away and home.casefold() == away.casefold():
        problems.append("home and away teams must differ")

    scores = {}
    for key in ("home_score", "away_score"):
        try:
            val = int(get(key))
            if not 0 <= val <= MAX_SCORE:
                problems.append(f"{key} must be 0-{MAX_SCORE}")
            scores[key] = val
        except ValueError:
            problems.append(f"{key} is not a whole number")

    try:
        dt = parse_date(get("date"))
        if dt > date.today():
            problems.append("date is in the future")
    except ValueError as e:
        problems.append(str(e))
        dt = None

    if problems:
        raise ValueError("; ".join(problems))
    return Match(mid, dt.isoformat(), sport.title(), home, away,
                 scores["home_score"], scores["away_score"])


