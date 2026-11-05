"""The seeded drill produces the same metrics on every RoomBus."""

from __future__ import annotations

from pathlib import Path

import pytest

from firedrill.adapters.base import NotSupported
from firedrill.adapters.local import LocalAdapter
from firedrill.adapters.mattermost import messages_from_post_list
from firedrill.adapters.switch import SwitchAdapter, messages_from_context
from firedrill.metrics import compute_metrics
from firedrill.models import RoomMessage
from firedrill.paths import DrillPaths
from firedrill.simulate import build_recording, play
from firedrill.store import AuditorStore

ROOT = Path(__file__).resolve().parents[1]


class MemoryBus:
    """In-memory RoomBus with the same order, channels, and timestamps as LocalAdapter."""

    def __init__(self) -> None:
        self.messages: list[RoomMessage] = []

    def post(
        self,
        *,
        author: str,
        role: str,
        body: str,
        thread_id: str | None = None,
        channel: str = "room",
        ts: str | None = None,
    ) -> RoomMessage:
        message = RoomMessage(
            seq=len(self.messages) + 1,
            id=f"mem-{len(self.messages) + 1}",
            ts=ts or "",
            author=author,
            role=role,
            thread_id=thread_id,
            body=body,
            channel=channel,
        )
        self.messages.append(message)
        return message

    def read_room(self) -> list[RoomMessage]:
        return self.read_channel("room")

    def read_channel(self, channel: str) -> list[RoomMessage]:
        return [message for message in self.messages if message.channel == channel]

    def add_reaction(self, *, message_id: str, user: str, emoji: str, ts: str | None = None) -> None:
        del message_id, user, emoji, ts


def _metrics(paths: DrillPaths):
    store = AuditorStore(paths.drill_db)
    try:
        return compute_metrics(store.requests(), store.decisions())
    finally:
        store.close()


def test_same_drill_matches_on_local_and_fake_bus(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKER_SECRET", "contract-worker-secret")
    events, canary_key = build_recording(DrillPaths(root=ROOT), offline=True)
    local_root = DrillPaths(root=tmp_path / "local")
    fake_root = DrillPaths(root=tmp_path / "fake")
    local = play(local_root, events, canary_key=canary_key)
    fake = play(fake_root, events, bus=MemoryBus(), canary_key=canary_key)
    assert local == fake
    assert _metrics(local_root) == _metrics(fake_root)
    bus = LocalAdapter(local_root.room_db)
    try:
        room = bus.read_room()
        private = bus.read_channel("dm:avery") + bus.read_channel("dm:blake") + bus.read_channel("dm:casey")
    finally:
        bus.close()
    assert any(message.body.startswith("/approve") or message.body.startswith("/reject") for message in room)
    assert any(message.body.startswith("PRIVATE CANARY RESULT") for message in private)


def test_mattermost_post_list_keeps_author_and_create_order():
    payload = {
        "order": ["newer", "older"],
        "posts": {
            "newer": {
                "id": "newer",
                "create_at": 2_000,
                "user_id": "bot",
                "message": "/approve fd-00000002",
                "root_id": "",
                "props": {"firedrill_author": "blake", "firedrill_role": "human", "firedrill_ts": "2026-11-05T15:00:02.000Z"},
            },
            "older": {
                "id": "older",
                "create_at": 1_000,
                "user_id": "user-avery",
                "message": "/optin",
                "root_id": "",
                "props": {},
            },
        },
    }
    messages = messages_from_post_list(payload, channel="room", user_names={"user-avery": "avery"})
    assert [message.body for message in messages] == ["/optin", "/approve fd-00000002"]
    assert messages[0].author == "avery"
    assert messages[1].author == "blake"
    assert messages[1].ts == "2026-11-05T15:00:02.000Z"


def test_switch_context_parser_uses_documented_threads():
    payload = {
        "result": {
            "threads": [
                {
                    "root": {
                        "id": "b",
                        "kind": "message",
                        "sender_name": "casey",
                        "body": "/approve fd-00000002",
                        "timestamp": 2_000,
                    },
                    "replies": [],
                },
                {
                    "root": {
                        "id": "a",
                        "kind": "message",
                        "sender_name": "avery",
                        "body": "/optin",
                        "timestamp": 1_000,
                    },
                    "replies": [
                        {
                            "id": "j",
                            "kind": "room_join",
                            "sender_name": "switch",
                            "body": "casey joined the room",
                            "timestamp": 1_500,
                        }
                    ],
                },
            ],
            "truncated": False,
        }
    }
    messages = messages_from_context(payload)
    assert [message.body for message in messages] == ["/optin", "/approve fd-00000002"]
    assert messages[0].author == "avery"


def test_switch_refuses_private_reveal_and_reactions_without_a_call(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("unconfirmed Switch call")

    monkeypatch.setattr("firedrill.adapters.switch.httpx.post", explode)
    monkeypatch.setattr("firedrill.adapters.switch.httpx.get", explode)
    adapter = SwitchAdapter("http://127.0.0.1:9", "agent", "token", "room-1")
    with pytest.raises(NotSupported) as caught:
        adapter.post(
            author="auditor",
            role="auditor",
            body="PRIVATE CANARY RESULT: miss",
            channel="dm:avery",
        )
    text = str(caught.value)
    assert "private" in text.lower()
    assert "Missing" in text
    with pytest.raises(NotSupported) as reaction:
        adapter.add_reaction(message_id="m1", user="avery", emoji="white_check_mark")
    assert "reaction" in str(reaction.value).lower()
    assert "Missing" in str(reaction.value)
