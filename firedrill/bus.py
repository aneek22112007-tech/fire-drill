"""Room message helpers shared by every adapter."""

from __future__ import annotations

from firedrill.models import ApprovalRequest, RoomMessage


CHANGE_AGENT = "change-agent"
CHANGE_ROLE = "change-agent"
SUMMARY_TEMPLATE = "Review this sample-service change before it lands. {change}"


