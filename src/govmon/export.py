"""Star-schema CSV export for a Power BI report.

Tables (all keyed on dataset_id, never on name):

  dim_dataset            one row per dataset, current state
  fact_daily_status      one row per dataset per day: the state the rules gave that morning
  fact_refresh_attempt   one row per refresh attempt (history window)
  dim_date               one row per day in the snapshot window

The daily snapshots are produced with the SAME rules as the live status (status.classify),
evaluated as of each past day using only the attempts that had happened by then, so the
trend a report shows is what the monitor would really have said.
"""
from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from .models import Attempt, Dataset, RefreshRow
from .status import Config, classify


def _dt(x):
    return "" if x is None else x.strftime("%Y-%m-%d %H:%M:%S")   # explicit, not machine-regional


def state_as_of(ds: Dataset, attempts: list[Attempt], when: datetime, cfg: Config):
    prior = [a for a in attempts if a.end_utc <= when]
    if prior:
        last = max(prior, key=lambda a: a.end_utc)
        view = replace(ds, last_refresh_utc=last.end_utc, last_status=last.status)
    elif ds.last_refresh_utc is not None and ds.last_refresh_utc <= when:
        view = ds            # last refresh was before the history window
    else:
        view = replace(ds, last_refresh_utc=None, last_status=None)
    return classify(view, when, cfg)


def build_tables(datasets: list[Dataset], history: dict[str, list[Attempt]], rows: list[RefreshRow],
                 now: datetime, cfg: Config = Config(), snapshot_days: int = 30) -> dict[str, list[dict]]:
    by_id = {d.dataset_id: d for d in datasets}
    dim_dataset = [{
        "dataset_id": r.dataset_id, "name": r.name, "workspace": r.workspace, "owner_email": r.owner_email,
        "scheduled": r.scheduled, "monitored": r.monitored, "archive_candidate": r.archive_candidate,
        "state": r.state, "last_refresh_utc": _dt(r.last_refresh_utc),
        "days_since_refresh": "" if r.days_since_refresh is None else r.days_since_refresh,
    } for r in rows]

    daily = []
    days = []
    for i in range(snapshot_days - 1, -1, -1):
        when = now - timedelta(days=i)
        days.append(when.date())
        for r in rows:
            state, age = state_as_of(by_id[r.dataset_id], history.get(r.dataset_id, []), when, cfg)
            daily.append({"date": when.date().isoformat(), "dataset_id": r.dataset_id, "state": state,
                          "days_since_refresh": "" if age is None else round(age, 2)})

    attempts = []
    for r in rows:
        for a in history.get(r.dataset_id, []):
            attempts.append({"dataset_id": a.dataset_id, "date": a.end_utc.date().isoformat(),
                             "start_utc": _dt(a.start_utc), "end_utc": _dt(a.end_utc),
                             "duration_min": round((a.end_utc - a.start_utc).total_seconds() / 60, 1),
                             "status": a.status})

    dim_date = [{"date": d.isoformat(), "year": d.year, "month": d.month, "month_name": d.strftime("%b"),
                 "day_of_week": d.strftime("%a"), "is_latest": d == days[-1]} for d in days]
    return {"dim_dataset": dim_dataset, "fact_daily_status": daily,
            "fact_refresh_attempt": attempts, "dim_date": dim_date}


def write_tables(tables: dict[str, list[dict]], out_dir) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, rows in tables.items():
        p = out / f"{name}.csv"
        with open(p, "w", newline="", encoding="utf-8") as fh:
            if rows:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
        paths.append(p)
    return paths
