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

    def public_dict(self) -> dict[str, object]:
        return self.model_dump()


class Decision(BaseModel):
    request_id: str
    reviewer: str
    action: DecisionAction
    reason: str = ""
    timestamp: str
    latency_s: float = Field(ge=0)


class Reviewer(BaseModel):
    id: str
    name: str
    profile: Literal["careful", "rushed", "average", "human"] = "human"
    opted_in: bool = False


class Flaw(BaseModel):
    id: str
    title: str
    mast_mode: str
    template: str
    tell: str
    summary: str
    risk: Risk
    complexity: int = Field(ge=1, le=10)
    diff: str


class DrillConfig(BaseModel):
    reviewers: list[Reviewer]
    seed: int = 20261105
    real_items: int = 50
    batch_size: int = 3
    flatness_cv: float = 0.25
    flatness_min_decisions: int = 5
    flatness_median_seconds: float = 8.0
    offline: bool = True


class Action(BaseModel):
    """A structured edit. The executor applies this, never a shell command."""

    kind: Literal["version_bump", "config_set", "add_function"]
    version: str | None = None
    key: str | None = None
    value: str | int | bool | None = None
    function_name: str | None = None
    function_body: str | None = None
    test_name: str | None = None
    test_body: str | None = None


class RoomMessage(BaseModel):
    seq: int
    id: str
    ts: str
    author: str
    role: str
    thread_id: str | None = None
    body: str
    channel: str = "room"
