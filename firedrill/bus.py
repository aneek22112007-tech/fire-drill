"""Room message helpers shared by every adapter."""

from __future__ import annotations

from firedrill.models import ApprovalRequest, RoomMessage


CHANGE_AGENT = "change-agent"
CHANGE_ROLE = "change-agent"
SUMMARY_TEMPLATE = "Review this sample-service change before it lands. {change}"


def voiced(change: str) -> str:
    return SUMMARY_TEMPLATE.format(change=change)


def format_approval(request: ApprovalRequest) -> str:
    """One formatter for the worker and the canary. No kind field, no flaw id."""

    diff = request.diff.rstrip("\n")
    return (
        f"Approval request {request.id}\n"
        f"Summary: {request.summary}\n"
        f"Risk: {request.risk}\n"
        f"Complexity: {request.complexity}\n"
        "Diff:\n"
        f"```diff\n{diff}\n```\n"
        f"Reply `/approve {request.id}` or `/reject {request.id} <reason>`.\n"
        "Reactions: white_check_mark approves, x rejects."
    )


