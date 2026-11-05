"""UTC timestamps with millisecond precision, so sub-minute review times survive."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def parse_ts(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(text)


def format_ts(moment: datetime) -> str:
    utc = moment.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def seconds_between(start: str, end: str) -> float:
    return max(0.0, (parse_ts(end) - parse_ts(start)).total_seconds())


def add_seconds(start: str, seconds: float) -> str:
    return format_ts(parse_ts(start) + timedelta(seconds=seconds))
