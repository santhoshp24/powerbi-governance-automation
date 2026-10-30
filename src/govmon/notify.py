"""Build (not send) owner notifications for datasets that need attention.

Design choices:
  * Only datasets that are MONITORED (used by an active dashboard) trigger owner emails.
    Scanning everything and emailing everyone is how alert fatigue starts.
  * One email per owner, listing all of their problem datasets.
  * Test mode redirects every email to a test recipient and prefixes the subject with the
    intended recipient, so the full flow can be rehearsed against real data safely.
  * Sending is a separate concern: this module returns Message objects. A FileOutbox is
    provided for the demo; a real deployment would hand them to a mail connector.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .models import RefreshRow

ATTENTION_STATES = ("Stale", "Failed", "Never refreshed")


@dataclass(frozen=True)
class Message:
    to: tuple[str, ...]
    subject: str
    body: str


@dataclass
class Notifier:
    mode: str = "test"                              # "test" or "live"
    test_recipient: str = "me@example.com"
    extra_recipients: tuple[str, ...] = ()          # added to To in live mode (e.g. a team mailbox)
    messages: list[Message] = field(default_factory=list)

    def build(self, rows: list[RefreshRow]) -> list[Message]:
        if self.mode not in ("test", "live"):
            raise ValueError("mode must be 'test' or 'live'")
        by_owner: dict[str, list[RefreshRow]] = defaultdict(list)
        for r in rows:
            if r.monitored and r.state in ATTENTION_STATES:
                by_owner[r.owner_email].append(r)
        out = []
        for owner in sorted(by_owner):
            items = sorted(by_owner[owner], key=lambda r: (r.workspace, r.name))
            subject = f"Action needed: {len(items)} dataset(s) not refreshing"
            lines = [f"Hello,", "", "These datasets you own need attention:", ""]
            for r in items:
                age = "never refreshed" if r.days_since_refresh is None else f"{r.days_since_refresh:.1f} days ago"
                lines.append(f"- {r.workspace} / {r.name}: {r.state} (last refresh: {age})")
            lines += ["", "Please check the refresh schedule and credentials."]
            if self.mode == "test":
                subject = f"[TEST - intended for {owner}] {subject}"
                to = (self.test_recipient,)
            else:
                to = tuple(dict.fromkeys((owner, *self.extra_recipients)))
            out.append(Message(to=to, subject=subject, body="\n".join(lines)))
        self.messages = out
        return out


class FileOutbox:
    """Writes each message as a text file instead of sending it."""

    def __init__(self, directory):
        self.dir = Path(directory)

    def send(self, messages: list[Message]) -> list[Path]:
        self.dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, m in enumerate(messages, 1):
            p = self.dir / f"{i:03d}.txt"
            p.write_text(f"To: {', '.join(m.to)}\nSubject: {m.subject}\n\n{m.body}\n", encoding="utf-8")
            paths.append(p)
        return paths
