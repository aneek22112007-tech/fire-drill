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
