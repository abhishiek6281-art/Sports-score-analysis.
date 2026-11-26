"""Project-wide constants and paths (overridable via SSA_DATA_DIR / SSA_REPORT_DIR)."""
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SSA_DATA_DIR", BASE_DIR / "data"))
DATA_FILE = DATA_DIR / "matches.json"      # legacy / json backend
DB_FILE = DATA_DIR / "matches.db"          # default sqlite backend
SAMPLE_FILE = BASE_DIR / "sample_data" / "sample_matches.json"
REPORT_DIR = Path(os.environ.get("SSA_REPORT_DIR", BASE_DIR / "reports"))

MAX_SCORE = 200            # hard validation limit for a single side's score
PAGE_SIZE = 15             # rows per page in tables
POINTS = {"W": 3, "D": 1, "L": 0}
Z_THRESHOLD = 2.5          # statistical anomaly threshold
MIN_FOR_STATS = 8          # matches needed in a sport before z-scores are used
INACTIVE_DAYS = 30         # warn if a team has not played for this long

NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .&'\-]{1,29}")
SPORT_RE = re.compile(r"[A-Za-z][A-Za-z ]{1,19}")
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")
REQUIRED_COLS = ("date", "sport", "home_team", "away_team", "home_score", "away_score")
