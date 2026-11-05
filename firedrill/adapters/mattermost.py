"""Mattermost adapter. Only API v4 calls checked against the public API are used.

Verified against the Mattermost OpenAPI posts and channels fragments:
- GET /api/v4/system/ping
- GET /api/v4/users/me with Authorization: Bearer
- POST /api/v4/posts with {channel_id, message, root_id?, props?}
- GET /api/v4/channels/{channel_id}/posts?page=&per_page= (PostList: order, posts)
- POST /api/v4/reactions with {user_id, post_id, emoji_name}
- POST /api/v4/channels/direct with [id1, id2]

Replies are polled with GetPostsForChannel. The websocket at /api/v4/websocket
is a second client; this adapter does not open it. MM_TOKEN is the bot or
personal access token. There is no guessed admin login.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from firedrill.adapters.base import AdapterError, assign_stable_seq
from firedrill.models import RoomMessage
from firedrill.timeutil import format_ts

_PAGE_SIZE = 100
_MAX_PAGES = 50


def missing_token_message(base: str) -> str:
    return (
        f"Mattermost is reachable at {base}, and MM_TOKEN or MM_CHANNEL_ID is empty. "
        "Create a personal access token, put MM_TOKEN and MM_CHANNEL_ID in .env, and run "
        "`firedrill up --adapter mattermost`. Fire Drill does not guess an admin password."
    )


def messages_from_post_list(
    payload: object,
    *,
    channel: str,
    user_names: dict[str, str],
) -> list[RoomMessage]:
    """Parse a documented PostList. `order` is not trusted for chronology; create_at is."""

    if not isinstance(payload, dict):
        raise AdapterError("GET /api/v4/channels/{channel_id}/posts did not return an object.")
    post_map = payload.get("posts")
    order = payload.get("order")
    if not isinstance(post_map, dict) or not isinstance(order, list):
        raise AdapterError(
            "GET /api/v4/channels/{channel_id}/posts did not return a PostList "
            "with an order array and a posts object."
        )
    raw: list[dict[str, Any]] = []
    for post_id in order:
        post = post_map.get(str(post_id))
        if isinstance(post, dict):
            raw.append(post)
    raw.sort(key=lambda post: (int(post.get("create_at") or 0), str(post.get("id") or "")))
    messages: list[RoomMessage] = []
    for post in raw:
        deleted = post.get("delete_at")
        if isinstance(deleted, int) and deleted > 0:
            continue
        post_id = str(post.get("id") or "")
        if not post_id:
            continue
        props = post.get("props") if isinstance(post.get("props"), dict) else {}
        user_id = str(post.get("user_id") or "")
        author = str(props.get("firedrill_author") or user_names.get(user_id) or user_id or "mattermost")
        role = str(props.get("firedrill_role") or "human")
        posted_channel = str(props.get("firedrill_channel") or channel)
        stamped = props.get("firedrill_ts")
        if isinstance(stamped, str) and stamped:
            ts = stamped
        else:
            created = post.get("create_at")
            if isinstance(created, int) and created > 0:
                ts = format_ts(datetime.fromtimestamp(created / 1000.0, timezone.utc))
            else:
                ts = ""
        root_id = str(post.get("root_id") or "") or None
        body = post.get("message")
        if not isinstance(body, str):
            continue
        messages.append(
            RoomMessage(
                seq=0,
                id=post_id,
                ts=ts,
                author=author,
                role=role,
                thread_id=root_id,
                body=body,
                channel=posted_channel,
            )
        )
    return messages


def _mattermost_login() -> tuple[str, str, str, str, str]:
    """Ping, then users/me. Returns base, token, channel, user id, username."""

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
    if not user_id:
        raise AdapterError("GET /api/v4/users/me did not return an id.")
    bot = os.environ.get("MM_BOT_USER_ID", "").strip()
    if bot and bot != user_id:
        raise AdapterError(
            "MM_BOT_USER_ID does not match GET /api/v4/users/me. "
            "Fire Drill will not post as a different user."
        )
    username = str(payload.get("username") or "the token user")
    return base, token, channel, user_id, username


def connect_mattermost() -> MattermostAdapter:
    """Open the room with MM_TOKEN. Does not post a readiness line."""

    base, token, channel, user_id, _username = _mattermost_login()
    return MattermostAdapter(base, token, channel, user_id)


def probe_mattermost() -> str:
    """Confirm the server, then post one readiness line when a token is configured."""

    base, token, channel, user_id, username = _mattermost_login()
    del token
    adapter = MattermostAdapter(base, os.environ.get("MM_TOKEN", "").strip(), channel, user_id)
    adapter.post_message(channel, "Fire Drill Mattermost adapter is up.", root_id=None)
    return f"mattermost ready at {base} as {username}"


class MattermostAdapter:
    def __init__(self, base_url: str, token: str, channel_id: str, user_id: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.channel_id = channel_id
        self.user_id = user_id
        self._sent: list[RoomMessage] = []
        self._seqs: dict[str, int] = {}
        self._direct: dict[str, str] = {}

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def post_message(
        self,
        channel_id: str,
        message: str,
        root_id: str | None,
        props: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"channel_id": channel_id, "message": message}
        if root_id:
            body["root_id"] = root_id
        if props:
            body["props"] = props
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
        self._direct[other_user_id] = str(channel_id)
        return str(channel_id)

    def channel_posts(self, channel_id: str) -> list[dict[str, Any]]:
        """GET /api/v4/channels/{channel_id}/posts, one documented page at a time."""

        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for page in range(_MAX_PAGES):
            response = httpx.get(
                f"{self.base_url}/api/v4/channels/{channel_id}/posts",
                headers=self._headers(),
                params={"page": page, "per_page": _PAGE_SIZE},
                timeout=15.0,
            )
            if response.status_code >= 400:
                raise AdapterError(
                    f"GET /api/v4/channels/{channel_id}/posts returned {response.status_code}."
                )
            payload = response.json()
            messages_from_post_list(payload, channel="room", user_names={})
            order = payload.get("order") if isinstance(payload, dict) else None
            if not isinstance(order, list) or not order:
                break
            post_map = payload.get("posts") if isinstance(payload, dict) else None
            if isinstance(post_map, dict):
                for post_id in order:
                    post = post_map.get(str(post_id))
                    if isinstance(post, dict) and str(post.get("id") or "") not in seen:
                        seen.add(str(post.get("id")))
                        collected.append(post)
            if len(order) < _PAGE_SIZE:
                break
            if page == _MAX_PAGES - 1:
                raise AdapterError(
                    f"GET /api/v4/channels/{channel_id}/posts still has another page after "
                    f"{_MAX_PAGES * _PAGE_SIZE} posts. Fire Drill stopped rather than read a partial room."
                )
        return collected

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
        props = {
            "firedrill_author": author,
            "firedrill_role": role,
            "firedrill_channel": channel,
        }
        if ts:
            props["firedrill_ts"] = ts
        payload = self.post_message(target, body, thread_id, props)
        post_id = payload.get("id")
        if not post_id:
            raise AdapterError("POST /api/v4/posts did not return an id.")
        message = RoomMessage(
            seq=len(self._sent) + 1,
            id=str(post_id),
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
        return self.read_channel("room")

    def read_channel(self, channel: str) -> list[RoomMessage]:
        if channel == "room":
            remote = self._listed(self.channel_id, channel)
        elif channel.startswith("dm:"):
            remote = self._remote_dm(channel)
        else:
            remote = []
        return self._merge(channel, remote)

    def _listed(self, channel_id: str, channel: str) -> list[RoomMessage]:
        posts = self.channel_posts(channel_id)
        payload = {
            "order": [str(post.get("id")) for post in posts if post.get("id")],
            "posts": {str(post.get("id")): post for post in posts if post.get("id")},
        }
        return messages_from_post_list(payload, channel=channel, user_names=self._user_names())

    def _remote_dm(self, channel: str) -> list[RoomMessage]:
        reviewer = channel[3:]
        other = os.environ.get(f"MM_USER_{reviewer.upper()}", "").strip()
        if not other:
            return []
        target = self._direct.get(other) or self.direct_channel(other)
        return self._listed(target, channel)

    def _user_names(self) -> dict[str, str]:
        names = {self.user_id: "mattermost"}
        for reviewer in ("avery", "blake", "casey"):
            user_id = os.environ.get(f"MM_USER_{reviewer.upper()}", "").strip()
            if user_id:
                names[user_id] = reviewer
        return names

    def _merge(self, channel: str, remote: list[RoomMessage]) -> list[RoomMessage]:
        local = [message for message in self._sent if message.channel == channel]
        local_by_id = {message.id: message for message in local}
        remote_ids = {message.id for message in remote}
        ordered: list[RoomMessage] = []
        for message in remote:
            ordered.append(local_by_id.get(message.id, message))
        for message in local:
            if message.id not in remote_ids:
                ordered.append(message)
        return assign_stable_seq(self._seqs, ordered)

    def add_reaction(self, *, message_id: str, user: str, emoji: str, ts: str | None = None) -> None:
        del user, ts
        self.react(message_id, emoji)
