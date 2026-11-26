"""Central logging: coloured console feedback for the user + rotating debug log file."""
import logging
import logging.handlers
import sys
from pathlib import Path

LOG = logging.getLogger("ssa")
_SYMBOL = {logging.DEBUG: ("·", "2"), logging.INFO: ("✔", "32"), logging.WARNING: ("⚠", "33"),
           logging.ERROR: ("✖", "31"), logging.CRITICAL: ("✖", "1;31")}


class _ConsoleFormatter(logging.Formatter):
    def format(self, record):
        sym, code = _SYMBOL.get(record.levelno, ("", "0"))
        text = f"  {sym} {record.getMessage()}"
        return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


class _StdoutHandler(logging.StreamHandler):
    """Resolves sys.stdout at emit time so redirection (and tests) keep working."""
    def __init__(self):
        super().__init__(sys.stdout)

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, _value):
        pass


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> logging.Logger:
    """Idempotent: replaces any handlers installed by a previous call."""
    for h in list(LOG.handlers):
        LOG.removeHandler(h)
        h.close()
    LOG.setLevel(logging.DEBUG)
    LOG.propagate = False
    console = _StdoutHandler()
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(_ConsoleFormatter())
    LOG.addHandler(console)
    if log_file:
        try:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(log_file, maxBytes=500_000, backupCount=2, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(module)s: %(message)s"))
            LOG.addHandler(fh)
        except OSError as exc:  # logging must never crash the app
            LOG.warning("Could not open log file %s (%s)", log_file, exc)
    return LOG
