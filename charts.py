"""Matplotlib charts (optional dependency: degrades gracefully when missing)."""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from . import config
from .analytics import standings
from .log import LOG


def make_charts(matches, out_dir=None) -> list[Path]:
    out_dir = Path(out_dir) if out_dir else config.REPORT_DIR
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        LOG.warning("Matplotlib is not installed. Run:  pip install matplotlib")
        return []
    if not matches:
        LOG.warning("No data to plot.")
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sports = sorted({m.sport for m in matches})
    files = []

    # 1. standings (points by team) per sport
    fig, axes = plt.subplots(1, len(sports), figsize=(5.5 * len(sports), 4.5), squeeze=False)
    for ax, sport in zip(axes[0], sports):
        rows = standings([m for m in matches if m.sport == sport])[::-1]
        bars = ax.barh([r["team"] for r in rows], [r["Pts"] for r in rows], color="#2e8b57")
        ax.bar_label(bars, padding=3)
        ax.set_title(f"{sport}: points")
        ax.set_xlabel("Points (W=3, D=1, L=0)")
    fig.suptitle("League standings", fontweight="bold")
    fig.tight_layout()
    files.append(out_dir / f"chart_standings_{ts}.png")
    fig.savefig(files[-1], dpi=130)
    plt.close(fig)

    # 2. trend: weekly average total score per sport
    fig, axes = plt.subplots(len(sports), 1, figsize=(8, 3 * len(sports)), squeeze=False)
    for ax, sport in zip(axes[:, 0], sports):
        weekly = defaultdict(list)
        for m in matches:
            if m.sport == sport:
                d = datetime.strptime(m.date, "%Y-%m-%d").date()
                weekly[d - timedelta(days=d.weekday())].append(m.total)
        xs = sorted(weekly)
        ys = [statistics.mean(weekly[x]) for x in xs]
        ax.plot(xs, ys, marker="o", color="#1f77b4")
        ax.set_title(f"{sport}: average total score per week")
        ax.set_ylabel("Avg total")
        ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    files.append(out_dir / f"chart_trend_{ts}.png")
    fig.savefig(files[-1], dpi=130)
    plt.close(fig)

    # 3. distributions: histogram of totals per sport + overall result split
    fig, axes = plt.subplots(1, len(sports) + 1, figsize=(4.5 * (len(sports) + 1), 4), squeeze=False)
    for ax, sport in zip(axes[0], sports):
        ax.hist([m.total for m in matches if m.sport == sport], bins=8, color="#ff7f0e", edgecolor="white")
        ax.set_title(f"{sport}: total score distribution")
        ax.set_xlabel("Total score")
        ax.set_ylabel("Matches")
    counts = defaultdict(int)
    for m in matches:
        counts[m.outcome] += 1
    labels = ["Home", "Draw", "Away"]
    bars = axes[0][-1].bar(labels, [counts[l] for l in labels], color=["#2e8b57", "#999999", "#c0392b"])
    axes[0][-1].bar_label(bars)
    axes[0][-1].set_title("Result split (all sports)")
    fig.tight_layout()
    files.append(out_dir / f"chart_distribution_{ts}.png")
    fig.savefig(files[-1], dpi=130)
    plt.close(fig)
    return files
