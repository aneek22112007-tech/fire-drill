"""Room commands and the public approval-request parser."""

from __future__ import annotations

import re
from dataclasses import dataclass

from firedrill.models import ApprovalRequest

_APPROVAL = re.compile(
    r"Approval request (fd-[0-9a-f]{8})\n"
    r"Summary: (?P<summary>.+)\n"
    r"Risk: (?P<risk>low|medium|high)\n"
    r"Complexity: (?P<complexity>\d+)\n"
    r"Diff:\n```diff\n(?P<diff>.*?)\n```",
    re.S,
)
_OPTIN = re.compile(r"^/optin\s*$")
_APPROVE = re.compile(r"^/approve\s+(fd-[0-9a-f]{8})\s*$")
_REJECT = re.compile(r"^/reject\s+(fd-[0-9a-f]{8})\s+(\S.*)$", re.S)
_EXPLAIN = re.compile(r"^/explain\s+(fd-[0-9a-f]{8})\s+(\S.*)$", re.S)

MISS_MARK = "PRIVATE CANARY RESULT: miss"
CATCH_MARK = "PRIVATE CANARY RESULT: catch"


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    request_id: str | None = None
    text: str = ""


def parse_command(line: str) -> ParsedCommand | None:
    text = line.strip()
    if _OPTIN.match(text):
        return ParsedCommand("optin")
    approve = _APPROVE.match(text)
    if approve:
        return ParsedCommand("approve", approve.group(1))
    reject = _REJECT.match(text)
    if reject:
        return ParsedCommand("reject", reject.group(1), reject.group(2).strip())
    explain = _EXPLAIN.match(text)
    if explain:
        return ParsedCommand("explain", explain.group(1), explain.group(2).strip())
    return None


