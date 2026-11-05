"""Mattermost adapter. Only the API v4 calls checked against the public API are used.

Verified:
- GET /api/v4/system/ping
- GET /api/v4/users/me with Authorization: Bearer
- POST /api/v4/posts with {channel_id, message, root_id?}
- POST /api/v4/reactions with {user_id, post_id, emoji_name}
- POST /api/v4/channels/direct with [id1, id2]

There is no guessed admin login. A missing token stops with instructions.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from firedrill.adapters.base import AdapterError
from firedrill.models import RoomMessage


def missing_token_message(base: str) -> str:
    return (
        f"Mattermost is reachable at {base}, and MM_TOKEN or MM_CHANNEL_ID is empty. "
        "Create a personal access token, put MM_TOKEN and MM_CHANNEL_ID in .env, and run "
        "`firedrill up --adapter mattermost`. Fire Drill does not guess an admin password."
    )


def probe_mattermost() -> str:
    """Confirm the server, then post one readiness line when a token is configured."""

    base = os.environ.get("MM_BASE_URL", "http://127.0.0.1:8065").rstrip("/")
    token = os.environ.get("MM_TOKEN", "").strip()
    channel = os.environ.get("MM_CHANNEL_ID", "").strip()
    try:
        ping = httpx.get(f"{base}/api/v4/system/ping", timeout=5.0)
    except httpx.HTTPError as exc:
        raise AdapterError(
            f"Mattermost is not reachable at {base} ({exc.__class__.__name__}). "
            "Start it with `docker compose up -d` in the fire-drill directory. "
            "The compose file publishes mattermost/mattermost-preview on port 8065."
        ) from exc
    if ping.status_code == 404:
        raise AdapterError(
            f"GET {base}/api/v4/system/ping returned 404. "
            "Fire Drill does not try another probe."
        )
    if ping.status_code >= 400:
        raise AdapterError(f"GET {base}/api/v4/system/ping returned {ping.status_code}.")
    if not token or not channel:
        raise AdapterError(missing_token_message(base))
    me = httpx.get(
        f"{base}/api/v4/users/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    if me.status_code == 401:
        raise AdapterError("Mattermost rejected MM_TOKEN (401 from /api/v4/users/me).")
    if me.status_code >= 400:
        raise AdapterError(f"GET /api/v4/users/me returned {me.status_code}.")
    payload: dict[str, Any] = me.json() if me.headers.get("content-type", "").startswith("application/json") else {}
    user_id = str(payload.get("id", ""))
    username = str(payload.get("username") or "the token user")
    adapter = MattermostAdapter(base, token, channel, user_id)
    adapter.post_message(channel, "Fire Drill Mattermost adapter is up.", root_id=None)
    return f"mattermost ready at {base} as {username}"


class MattermostAdapter:
    def __init__(self, base_url: str, token: str, channel_id: str, user_id: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.channel_id = channel_id
        self.user_id = user_id
        self._sent: list[RoomMessage] = []

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def post_message(self, channel_id: str, message: str, root_id: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {"channel_id": channel_id, "message": message}
        if root_id:
            body["root_id"] = root_id
        response = httpx.post(
            f"{self.base_url}/api/v4/posts",
            headers=self._headers(),
            json=body,
            timeout=15.0,
        )
        if response.status_code >= 400:
            raise AdapterError(f"POST /api/v4/posts returned {response.status_code}.")
        payload = response.json()
        if not isinstance(payload, dict):
            raise AdapterError("POST /api/v4/posts did not return an object.")
        return payload

    def react(self, post_id: str, emoji_name: str) -> None:
        response = httpx.post(
            f"{self.base_url}/api/v4/reactions",
            headers=self._headers(),
            json={"user_id": self.user_id, "post_id": post_id, "emoji_name": emoji_name},
            timeout=15.0,
        )
        if response.status_code >= 400:
            raise AdapterError(f"POST /api/v4/reactions returned {response.status_code}.")

    def direct_channel(self, other_user_id: str) -> str:
        response = httpx.post(
            f"{self.base_url}/api/v4/channels/direct",
            headers=self._headers(),
            json=[self.user_id, other_user_id],
            timeout=15.0,
        )
        if response.status_code >= 400:
            raise AdapterError(f"POST /api/v4/channels/direct returned {response.status_code}.")
        payload = response.json()
        channel_id = payload.get("id") if isinstance(payload, dict) else None
        if not channel_id:
            raise AdapterError("POST /api/v4/channels/direct did not return a channel id.")
        return str(channel_id)

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
        target = self.channel_id
        if channel.startswith("dm:"):
            other = os.environ.get(f"MM_USER_{channel[3:].upper()}", "").strip()
            if not other:
                raise AdapterError(
                    f"No Mattermost user id for {channel}. "
                    f"Set MM_USER_{channel[3:].upper()} in .env."
                )
            target = self.direct_channel(other)
        payload = self.post_message(target, body, thread_id)
        message = RoomMessage(
            seq=len(self._sent) + 1,
            id=str(payload.get("id") or f"local-{len(self._sent) + 1}"),
            ts=ts or str(payload.get("create_at") or ""),
            author=author,
            role=role,
            thread_id=thread_id,
            body=body,
            channel=channel,
        )
        self._sent.append(message)
        return message

    def read_room(self) -> list[RoomMessage]:
        """Messages this process posted. Listing history is not a verified call here."""

        return [message for message in self._sent if message.channel == "room"]

    def read_channel(self, channel: str) -> list[RoomMessage]:
        return [message for message in self._sent if message.channel == channel]

    def add_reaction(self, *, message_id: str, user: str, emoji: str, ts: str | None = None) -> None:
        del user, ts
        self.react(message_id, emoji)
