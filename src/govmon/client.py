"""Data sources for dataset facts.

SyntheticClient  deterministic fake tenant used by the demo and the tests (tested).
RestClient       SKETCH of a Power BI REST client using a service principal.
                 NOT tested from this repo: it needs a real tenant. Treat it as a starting
                 point and verify endpoints, scopes and permissions against Microsoft's docs.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Protocol

from .models import Attempt, Dataset


class Client(Protocol):
    def list_datasets(self) -> list[Dataset]: ...
    def refresh_history(self, ds: Dataset) -> list[Attempt]: ...


WORKSPACES = ["Ops Analytics", "Finance Reporting", "HSE Reporting", "Sales Insights"]
OWNERS = ["asha@example.com", "ben@example.com", "chen@example.com", "dana@example.com", "eli@example.com"]


class SyntheticClient:
    """40 invented datasets with every state the rules care about."""

    def __init__(self, now: datetime, seed: int = 7):
        self.now = now
        self.seed = seed
        self.rng = random.Random(seed)

    def refresh_history(self, ds: Dataset, window_days: int = 45) -> list[Attempt]:
        """Deterministic history consistent with the dataset's current state.

        Scheduled datasets refresh about once a day back to the window start (a stale dataset
        simply stops at its last refresh); unscheduled ones are refreshed by hand every 6-12 days.
        About 3% of earlier attempts fail. The newest attempt always matches the dataset's own
        last_refresh_utc and last_status, so exports and the status table agree.
        """
        if ds.last_refresh_utc is None:
            return []
        rng = random.Random(f"{self.seed}:{ds.dataset_id}")
        limit = self.now - timedelta(days=window_days)
        out, t, k = [], ds.last_refresh_utc, 0
        while t >= limit:
            status = (ds.last_status or "Completed") if k == 0 else ("Failed" if rng.random() < 0.03 else "Completed")
            dur = timedelta(minutes=rng.uniform(2, 25))
            out.append(Attempt(ds.dataset_id, t - dur, t, status))
            k += 1
            step = timedelta(days=1) if ds.scheduled else timedelta(days=rng.randint(6, 12))
            jitter = timedelta(minutes=rng.randint(-20, 20)) if ds.scheduled else timedelta(0)
            t = t - step + jitter
        return sorted(out, key=lambda a: a.end_utc)

    def list_datasets(self) -> list[Dataset]:
        rng, now, out = self.rng, self.now, []
        # (count, scheduled, age_days range, last_status)
        plan = [
            (22, True, (0.05, 0.9), "Completed"),      # healthy
            (5, True, (2.0, 6.0), "Completed"),        # stale
            (3, True, (0.1, 0.9), "Failed"),           # failed on last attempt
            (1, True, None, None),                     # never refreshed
            (4, False, (3.0, 60.0), "Completed"),      # not scheduled
            (3, True, (190.0, 320.0), "Completed"),    # long stale: archive candidates
            (2, False, (200.0, 400.0), "Completed"),   # abandoned and unscheduled
        ]
        n = 0
        for count, scheduled, age, status in plan:
            for _ in range(count):
                n += 1
                last = None if age is None else now - timedelta(days=rng.uniform(*age))
                out.append(Dataset(
                    dataset_id=f"00000000-0000-0000-0000-{n:012d}",
                    name=f"Dataset {n:02d}",
                    workspace=rng.choice(WORKSPACES),
                    owner_email=None if n in (9, 30) else rng.choice(OWNERS),   # two with no owner
                    scheduled=scheduled, last_refresh_utc=last, last_status=status))
        return out


class RestClient:  # pragma: no cover - sketch, needs a real tenant
    """Sketch only. Service principal, read-only. Never put secrets in code: read them from a vault."""

    BASE = "https://api.powerbi.com/v1.0/myorg"

    def __init__(self, token: str):
        import requests  # imported lazily so the demo needs no third-party packages
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token}"
        self._group_of: dict[str, str] = {}      # dataset_id -> workspace id, for the history call

    def _get(self, path, **params):
        r = self.s.get(f"{self.BASE}{path}", params=params, timeout=60)
        r.raise_for_status()
        return r.json().get("value", [])

    def list_datasets(self) -> list[Dataset]:
        out = []
        for g in self._get("/groups"):
            for d in self._get(f"/groups/{g['id']}/datasets"):
                self._group_of[d["id"]] = g["id"]
                hist = self._get(f"/groups/{g['id']}/datasets/{d['id']}/refreshes", **{"$top": 1})
                last = hist[0] if hist else None
                end = last.get("endTime") if last else None
                out.append(Dataset(
                    dataset_id=d["id"], name=d["name"], workspace=g["name"],
                    owner_email=d.get("configuredBy"),
                    scheduled=bool(d.get("isRefreshable")),   # refine with the refresh-schedule endpoint
                    last_refresh_utc=datetime.fromisoformat(end.replace("Z", "+00:00")).astimezone(timezone.utc) if end else None,
                    last_status=last.get("status") if last else None))
        return out

    def refresh_history(self, ds: Dataset) -> list[Attempt]:
        gid = self._group_of.get(ds.dataset_id)
        if not gid:
            return []
        out = []
        for h in self._get(f"/groups/{gid}/datasets/{ds.dataset_id}/refreshes", **{"$top": 60}):
            if h.get("status") not in ("Completed", "Failed") or not h.get("endTime"):
                continue          # skip in-progress / disabled / cancelled entries
            def parse(x):
                return datetime.fromisoformat(x.replace("Z", "+00:00")).astimezone(timezone.utc)
            out.append(Attempt(ds.dataset_id, parse(h["startTime"]), parse(h["endTime"]), h["status"]))
        return sorted(out, key=lambda a: a.end_utc)
