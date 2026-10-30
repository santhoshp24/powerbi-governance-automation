"""Turn raw dataset facts into a refresh-status table.

Rules (all thresholds come from config):

  Not scheduled     no refresh schedule -> never reported as stale (nothing to be late for)
  Never refreshed   scheduled but no refresh history
  Failed            the last refresh attempt failed
  Stale             scheduled, and older than stale_after_days + grace_hours
  Healthy           otherwise

  archive_candidate  last refresh older than archive_after_days (a REVIEW flag, not an action:
                     archiving needs the dataset owner's confirmation)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .models import Dataset, RefreshRow


@dataclass(frozen=True)
class Config:
    stale_after_days: float = 1.0
    grace_hours: float = 2.0          # absorbs schedule jitter so a daily refresh does not flap
    archive_after_days: int = 183     # ~6 months
    fallback_owner: str = "governance@example.com"   # where datasets with no known owner are routed


def classify(ds: Dataset, now: datetime, cfg: Config) -> tuple[str, float | None]:
    days = None
    if ds.last_refresh_utc is not None:
        days = (now - ds.last_refresh_utc).total_seconds() / 86400
    if not ds.scheduled:
        return "Not scheduled", days
    if ds.last_refresh_utc is None:
        return "Never refreshed", None
    if (ds.last_status or "").lower() == "failed":
        return "Failed", days
    limit_hours = cfg.stale_after_days * 24 + cfg.grace_hours
    if days * 24 > limit_hours:
        return "Stale", days
    return "Healthy", days


def build_status(datasets: Iterable[Dataset], monitored_ids: set[str], now: datetime,
                 cfg: Config = Config()) -> list[RefreshRow]:
    rows = []
    for ds in datasets:
        state, days = classify(ds, now, cfg)
        rows.append(RefreshRow(
            dataset_id=ds.dataset_id, name=ds.name, workspace=ds.workspace,
            owner_email=(ds.owner_email or cfg.fallback_owner).strip().lower(),
            scheduled=ds.scheduled, last_refresh_utc=ds.last_refresh_utc,
            days_since_refresh=None if days is None else round(days, 2),
            state=state,
            archive_candidate=days is not None and days > cfg.archive_after_days,
            monitored=ds.dataset_id in monitored_ids,
        ))
    return sorted(rows, key=lambda r: (r.workspace, r.name, r.dataset_id))
