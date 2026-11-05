"""Room bus interface. Switch and Mattermost implement this with verified calls only."""

from __future__ import annotations

from typing import Protocol

from firedrill.models import RoomMessage


class AdapterError(RuntimeError):
    """A remote adapter refused to guess a call it could not verify."""


class RoomBus(Protocol):
    def post(
        self,
        *,
        author: str,
        role: str,
        body: str,
        thread_id: str | None = None,
        channel: str = "room",
        ts: str | None = None,
    ) -> RoomMessage: ...

    def read_room(self) -> list[RoomMessage]: ...

