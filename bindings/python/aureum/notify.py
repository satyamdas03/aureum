"""Post-trade notification / observability sinks for Aureum live trading.

Notifications are lightweight, machine-readable audit events emitted by the
live trading loop.  They can be written to a directory as deterministic JSON
files, printed to the console, or both.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

NotificationLevel = Literal["info", "warning", "error"]


@dataclass
class Notification:
    """A single live-trading observability event."""

    run_id: str
    timestamp: str
    level: NotificationLevel
    title: str
    body: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "level": self.level,
            "title": self.title,
            "body": self.body,
            "metadata": self.metadata,
        }


def _notification_filename(notification: Notification) -> str:
    """Build a deterministic, filesystem-safe filename from the notification."""
    safe_ts = (
        notification.timestamp.replace(":", "-")
        .replace("+", "_")
        .replace("Z", "Z")
    )
    return f"notification-{notification.run_id}-{safe_ts}.json"


def write_notification(notification: Notification, directory: str | Path) -> Path:
    """Write ``notification`` as a deterministic JSON file under ``directory``."""
    dest = Path(directory)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / _notification_filename(notification)
    path.write_text(
        json.dumps(notification.to_dict(), indent=2, default=str, sort_keys=False),
        encoding="utf-8",
    )
    return path


def console_sink(notification: Notification) -> None:
    """Print a one-line summary of ``notification`` to stdout."""
    print(
        f"[{notification.level.upper()}] {notification.timestamp} "
        f"run={notification.run_id} {notification.title}: {notification.body}",
        file=sys.stdout,
    )


def file_and_console(notification: Notification, directory: str | Path) -> Path:
    """Write the notification to disk and print a one-line console summary."""
    path = write_notification(notification, directory)
    console_sink(notification)
    return path
