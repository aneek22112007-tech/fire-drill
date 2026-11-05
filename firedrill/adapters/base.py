"""Room bus interface. Switch and Mattermost implement this with verified calls only."""

from __future__ import annotations

from typing import Protocol

from firedrill.models import RoomMessage


class AdapterError(RuntimeError):
    """A remote adapter refused to guess a call it could not verify."""


class NotSupported(AdapterError):
    """The verified protocol has no call for this. The message names what is missing."""


def assign_stable_seq(known: dict[str, int], messages: list[RoomMessage]) -> list[RoomMessage]:
    """Keep a seq for each id. New ids take the next seq, in the order they are first seen."""

    next_seq = max(known.values(), default=0) + 1
    for message in messages:
        if message.id not in known:
            known[message.id] = next_seq
            next_seq += 1
    ordered = sorted(messages, key=lambda item: known[item.id])
    return [item.model_copy(update={"seq": known[item.id]}) for item in ordered]


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

    def read_channel(self, channel: str) -> list[RoomMessage]: ...

    def add_reaction(self, *, message_id: str, user: str, emoji: str, ts: str | None = None) -> None: ...
