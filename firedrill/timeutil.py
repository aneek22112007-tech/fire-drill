"""UTC timestamps with millisecond precision, so sub-minute review times survive."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def parse_ts(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(text)


