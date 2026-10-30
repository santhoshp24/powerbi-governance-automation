from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Dataset:
    dataset_id: str                  # join on the GUID, never the name (names repeat across workspaces)
    name: str
    workspace: str
    owner_email: Optional[str]
    scheduled: bool                  # has a refresh schedule enabled
    last_refresh_utc: Optional[datetime]   # None = never refreshed
    last_status: Optional[str]       # "Completed" | "Failed" | None


@dataclass(frozen=True)
class RefreshRow:
    dataset_id: str
    name: str
    workspace: str
    owner_email: str
    scheduled: bool
    last_refresh_utc: Optional[datetime]
    days_since_refresh: Optional[float]
    state: str            # Healthy | Stale | Failed | Never refreshed | Not scheduled
    archive_candidate: bool
    monitored: bool


@dataclass(frozen=True)
class Attempt:
    """One refresh attempt from a dataset's refresh history."""
    dataset_id: str
    start_utc: datetime
    end_utc: datetime
    status: str           # Completed | Failed
