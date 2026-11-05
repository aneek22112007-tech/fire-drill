"""Shared records for a fire drill.

The public approval request is the same shape for real work and for canaries.
Flaw ids stay out of this object on purpose. The canary sends that mapping
only to the auditor service.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Risk = Literal["low", "medium", "high"]
DecisionAction = Literal["approve", "reject", "explain"]


class ApprovalRequest(BaseModel):
    """What a reviewer sees. Worker and canary both use this schema."""

    id: str = Field(pattern=r"^fd-[0-9a-f]{8}$")
    summary: str
    diff: str
    risk: Risk
    complexity: int = Field(ge=1, le=10)

