"""Write the files a downstream semantic model reads.

The consuming model's source has a FIXED file name, so the run always writes
DailyRefreshStatus.csv (overwritten each day). A dated copy is written alongside for history.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .models import RefreshRow

FIELDS = ["dataset_id", "name", "workspace", "owner_email", "scheduled", "last_refresh_utc",
          "days_since_refresh", "state", "archive_candidate", "monitored"]


def _fmt_dt(dt):
    # Explicit format: default datetime-to-text follows the machine's regional settings.
    return "" if dt is None else dt.strftime("%Y-%m-%d %H:%M:%S")


def write_status(rows: list[RefreshRow], out_dir, now: datetime) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fixed = out / "DailyRefreshStatus.csv"
    dated = out / f"DailyRefreshStatus_{now:%Y-%m-%d}.csv"
    for path in (fixed, dated):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(FIELDS)
            for r in rows:
                w.writerow([r.dataset_id, r.name, r.workspace, r.owner_email, r.scheduled,
                            _fmt_dt(r.last_refresh_utc),
                            "" if r.days_since_refresh is None else r.days_since_refresh,
                            r.state, r.archive_candidate, r.monitored])
    return fixed, dated
