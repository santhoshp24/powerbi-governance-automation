import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .client import SyntheticClient
from .export import build_tables, write_tables
from .notify import FileOutbox, Notifier
from .outputs import write_status
from .status import Config, build_status

ROOT = Path(__file__).resolve().parents[2]


def load_monitored(path) -> set[str]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return {r["dataset_id"].strip() for r in csv.DictReader(fh)}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="govmon")
    ap.add_argument("--client", choices=["synthetic", "rest"], default="synthetic",
                    help="synthetic = invented tenant (default); rest = Power BI REST API (needs POWERBI_TOKEN)")
    ap.add_argument("--now", default=None, help="UTC timestamp to evaluate at (default: 2026-10-30T09:00 for synthetic, now for rest)")
    ap.add_argument("--mode", choices=["test", "live"], default="test")
    ap.add_argument("--test-recipient", default="me@example.com")
    ap.add_argument("--extra-recipient", action="append", default=[])
    ap.add_argument("--monitored", default=None,
                    help="CSV with a dataset_id column. Default: sample list (synthetic) / none (rest: nothing is 'monitored')")
    ap.add_argument("--snapshot-days", type=int, default=30)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    if a.client == "synthetic":
        now = datetime.fromisoformat(a.now or "2026-10-30T09:00:00").replace(tzinfo=timezone.utc)
        client = SyntheticClient(now)
        monitored_path = a.monitored or str(ROOT / "sample_data" / "monitored_datasets.csv")
        out = Path(a.out or ROOT / "output")
    else:
        token = os.environ.get("POWERBI_TOKEN")
        if not token:
            sys.exit("Set POWERBI_TOKEN to a Power BI access token (see powerbi/README.md).")
        from .client import RestClient
        now = (datetime.fromisoformat(a.now).replace(tzinfo=timezone.utc) if a.now
               else datetime.now(timezone.utc).replace(microsecond=0))
        client = RestClient(token)
        monitored_path = a.monitored
        out = Path(a.out or ROOT / "output_real")     # real-tenant output stays out of git

    cfg = Config()
    datasets = client.list_datasets()
    monitored = load_monitored(monitored_path) if monitored_path else set()
    rows = build_status(datasets, monitored, now, cfg)
    history = {d.dataset_id: client.refresh_history(d) for d in datasets}

    fixed, dated = write_status(rows, out, now)
    tables = build_tables(datasets, history, rows, now, cfg, a.snapshot_days)
    write_tables(tables, out / "powerbi")

    notifier = Notifier(mode=a.mode, test_recipient=a.test_recipient, extra_recipients=tuple(a.extra_recipient))
    msgs = notifier.build(rows)
    FileOutbox(out / "outbox").send(msgs)

    counts = {}
    for r in rows:
        counts[r.state] = counts.get(r.state, 0) + 1
    print(f"Evaluated {len(rows)} datasets at {now:%Y-%m-%d %H:%M} UTC ({a.client} client)")
    for k in ("Healthy", "Stale", "Failed", "Never refreshed", "Not scheduled"):
        print(f"  {k:<16}{counts.get(k, 0)}")
    print(f"  archive candidates {sum(r.archive_candidate for r in rows)}")
    print(f"  monitored          {sum(r.monitored for r in rows)}")
    print(f"Wrote {fixed.name}, {dated.name} and {len(tables)} Power BI tables in {out / 'powerbi'}; "
          f"{len(msgs)} owner email(s) in {a.mode} mode -> {out / 'outbox'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
