"""Tests for the notification / observability sinks."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from aureum.notify import (
    Notification,
    console_sink,
    file_and_console,
    write_notification,
)


def test_write_notification_creates_expected_json(tmp_path: Path):
    notif = Notification(
        run_id="run-abc123",
        timestamp="2024-01-15T09:30:00Z",
        level="info",
        title="Live rebalance complete",
        body="mode=paper, orders=3, errors=0",
        metadata={"live_mode": "paper", "orders": 3, "errors": 0},
    )
    path = write_notification(notif, tmp_path)

    assert path.exists()
    assert path.parent == tmp_path
    assert "notification-run-abc123-2024-01-15T09-30-00Z.json" == path.name

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == "run-abc123"
    assert data["timestamp"] == "2024-01-15T09:30:00Z"
    assert data["level"] == "info"
    assert data["title"] == "Live rebalance complete"
    assert data["body"] == "mode=paper, orders=3, errors=0"
    assert data["metadata"] == {"live_mode": "paper", "orders": 3, "errors": 0}


def test_file_and_console_appends_and_prints(capsys, tmp_path: Path):
    notif = Notification(
        run_id="run-def456",
        timestamp="2024-06-01T16:00:00+00:00",
        level="warning",
        title="Kill switch active",
        body="Run aborted.",
        metadata={"kill_switch": "/tmp/kill.switch"},
    )
    path = file_and_console(notif, tmp_path)

    assert path.exists()
    files = list(tmp_path.glob("notification-*.json"))
    assert len(files) == 1

    captured = capsys.readouterr()
    assert captured.out == (
        "[WARNING] 2024-06-01T16:00:00+00:00 run=run-def456 "
        "Kill switch active: Run aborted.\n"
    )


def test_console_sink_prints_one_line(capsys):
    notif = Notification(
        run_id="run-ghi789",
        timestamp="2024-12-31T23:59:59Z",
        level="error",
        title="Live rebalance failed",
        body="Connection timeout",
        metadata={"exception_type": "ConnectionError"},
    )
    console_sink(notif)

    captured = capsys.readouterr()
    assert captured.out == (
        "[ERROR] 2024-12-31T23:59:59Z run=run-ghi789 "
        "Live rebalance failed: Connection timeout\n"
    )


@pytest.mark.parametrize(
    "timestamp",
    [
        "2024-01-15T09:30:00Z",
        "2024-06-01T16:00:00+00:00",
        "2024-12-31T23:59:59.123456+05:30",
    ],
)
def test_notification_fields_and_iso_timestamp(tmp_path: Path, timestamp: str):
    notif = Notification(
        run_id="run-jkl012",
        timestamp=timestamp,
        level="info",
        title="T",
        body="B",
        metadata={},
    )
    path = write_notification(notif, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert "run_id" in data
    assert "timestamp" in data
    assert "level" in data
    assert "title" in data
    assert "body" in data
    assert "metadata" in data

    # ISO-8601 timestamps contain a date, a 'T' separator, and a time component.
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", data["timestamp"])
    assert data["level"] in {"info", "warning", "error"}
