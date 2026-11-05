"""Switch adapter. Only calls confirmed in the published agent protocol are used.

Confirmed at https://docs.switchagents.ai/switch-rooms/internals/agent-protocol
and the operation signatures in switch_core (read_context, post_message,
send_targeted_message):
- GET /health
- POST /agents/{agent_id}/message with JSON {room_id, content}
- GET /agents/{agent_id}/ops
- POST /agents/{agent_id}/ops/{operation} with Authorization: Bearer
  and an optional X-Switch-Connection-Id
- read_context(limit, since, before, room_id), and only with names the live
  schema lists

send_targeted_message is in the catalog, but other participants still see it
in the room. There is no private DM and no reaction operation. Those raise
NotSupported and name the missing call. No Switch CLI is installed here
(`/usr/bin/kswitch` is Kerberos), so none of this has been run against a
live server.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import httpx

from firedrill.adapters.base import AdapterError, NotSupported, assign_stable_seq
from firedrill.models import RoomMessage
from firedrill.timeutil import format_ts


def property_names(node: object) -> set[str] | None:
    """Return published argument names, or None when the schema does not list them."""

    if not isinstance(node, dict):
        return None
    props = node.get("properties")
    if isinstance(props, dict):
        return {str(key) for key in props}
    for key in ("parameters", "arguments", "input", "schema", "input_schema"):
        if key in node:
            found = property_names(node[key])
            if found is not None:
                return found
    return None


def filter_arguments(schema: object, arguments: dict[str, object]) -> dict[str, object]:
    allowed = property_names(schema)
    if allowed is None:
        raise AdapterError("operation schema has no properties; refusing to guess argument names")
    extra = sorted(set(arguments) - allowed)
    if extra:
        raise AdapterError(f"refusing arguments that the schema does not list: {', '.join(extra)}")
    return {key: value for key, value in arguments.items() if key in allowed}


def find_operation(payload: object, name: str) -> object | None:
    if isinstance(payload, dict):
        if name in payload and isinstance(payload[name], dict):
            return payload[name]
        for key in ("operations", "ops", "result"):
            found = find_operation(payload.get(key), name)
            if found is not None:
                return found
        for value in payload.values():
            if isinstance(value, dict) and value.get("name") == name:
                return value
    if isinstance(payload, list):
        for item in payload:
            found = find_operation(item, name)
            if found is not None:
                return found
    return None


def messages_from_context(payload: object) -> list[RoomMessage]:
    """Parse read_context's documented {threads: [{root, replies}]} timeline."""

    if not isinstance(payload, dict):
        raise NotSupported(
            "read_context did not return an object. "
            "Missing: the documented shape {threads: [{root, replies}]}."
        )
    data = payload
    if "threads" not in data and isinstance(data.get("result"), dict):
        data = data["result"]
    threads = data.get("threads") if isinstance(data, dict) else None
    if not isinstance(threads, list):
        raise NotSupported(
            "read_context did not return threads. "
            "Missing: the documented timeline shape {threads: [{root, replies}]}."
        )
    entries: list[dict[str, Any]] = []
    for thread in threads:
        if not isinstance(thread, dict):
            continue
        root = thread.get("root")
        if isinstance(root, dict):
            entries.append(root)
        replies = thread.get("replies")
        if isinstance(replies, list):
            entries.extend(item for item in replies if isinstance(item, dict))

    def _key(entry: dict[str, Any]) -> tuple[int, str]:
        stamp = entry.get("timestamp")
        return (stamp if isinstance(stamp, int) else 0, str(entry.get("id") or ""))

    messages: list[RoomMessage] = []
    for index, entry in enumerate(sorted(entries, key=_key)):
        if entry.get("kind") not in (None, "message"):
            continue
        body = entry.get("body")
        if not isinstance(body, str):
            continue
        stamp = entry.get("timestamp")
        if isinstance(stamp, int):
            ts = format_ts(datetime.fromtimestamp(stamp / 1000.0, timezone.utc))
        else:
            ts = ""
        messages.append(
            RoomMessage(
                seq=index + 1,
                id=str(entry.get("id") or f"switch-ctx-{index}"),
                ts=ts,
                author=str(entry.get("sender_name") or entry.get("sender") or ""),
                role="human",
                thread_id=None,
                body=body,
                channel="room",
            )
        )
    return messages


def _switch_target() -> tuple[str, str, str, str, str | None]:
    base = os.environ.get("SWITCH_BASE_URL", "").strip().rstrip("/")
    token = os.environ.get("SWITCH_API_TOKEN", "").strip()
    agent_id = os.environ.get("SWITCH_AGENT_ID", "").strip()
    room_id = os.environ.get("SWITCH_ROOM_ID", "").strip()
    if not base:
        raise AdapterError(
            "SWITCH_BASE_URL is empty. Point it at a Switch server, set "
            "SWITCH_AGENT_ID, SWITCH_API_TOKEN, and SWITCH_ROOM_ID, then run "
            "`firedrill up --adapter switch`. The local adapter remains the default."
        )
    try:
        health = httpx.get(f"{base}/health", timeout=5.0)
    except httpx.HTTPError as exc:
        raise AdapterError(
            f"Switch is not reachable at {base} ({exc.__class__.__name__}). "
            "GET /health failed, so Fire Drill will not pretend the room is connected."
        ) from exc
    if health.status_code >= 400:
        raise AdapterError(f"GET {base}/health returned {health.status_code}.")
    missing = [
        name
        for name, value in (
            ("SWITCH_API_TOKEN", token),
            ("SWITCH_AGENT_ID", agent_id),
            ("SWITCH_ROOM_ID", room_id),
        )
        if not value
    ]
    if missing:
        raise AdapterError(
            "Switch /health succeeded. Still missing " + ", ".join(missing) + ". "
            "Fire Drill does not invent agent or room ids."
        )
    connection = os.environ.get("SWITCH_CONNECTION_ID", "").strip() or None
    return base, token, agent_id, room_id, connection


def connect_switch() -> SwitchAdapter:
    """Open the agent bridge. Does not post a readiness line."""

    base, token, agent_id, room_id, connection = _switch_target()
    return SwitchAdapter(base, agent_id, token, room_id, connection)


def probe_switch() -> str:
    adapter = connect_switch()
    adapter.post_room("Fire Drill Switch adapter is up.")
    return f"switch ready at {adapter.base_url} room {adapter.room_id}"


class SwitchAdapter:
    def __init__(
        self,
        base_url: str,
        agent_id: str,
        token: str,
        room_id: str,
        connection_id: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.token = token
        self.room_id = room_id
        self.connection_id = connection_id
        self._sent: list[RoomMessage] = []
        self._seqs: dict[str, int] = {}
        self._ops: object | None = None

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if self.connection_id:
            headers["X-Switch-Connection-Id"] = self.connection_id
        return headers

    def post_room(self, content: str) -> dict[str, Any]:
        """POST /agents/{id}/message. This call does not need a websocket connection."""

        response = httpx.post(
            f"{self.base_url}/agents/{self.agent_id}/message",
            headers=self._headers(),
            json={"room_id": self.room_id, "content": content},
            timeout=15.0,
        )
        if response.status_code >= 400:
            raise AdapterError(
                f"POST /agents/{self.agent_id}/message returned {response.status_code}."
            )
        payload = response.json()
        if isinstance(payload, dict):
            return payload
        return {"result": payload}

    def operations(self) -> object:
        if self._ops is None:
            response = httpx.get(
                f"{self.base_url}/agents/{self.agent_id}/ops",
                headers=self._headers(),
                timeout=10.0,
            )
            if response.status_code >= 400:
                raise AdapterError(f"GET /agents/{self.agent_id}/ops returned {response.status_code}.")
            self._ops = response.json()
        return self._ops

    def call_operation(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        schema = find_operation(self.operations(), name)
        if schema is None:
            raise NotSupported(
                f"GET /agents/{self.agent_id}/ops did not list {name}. "
                f"Missing: the {name} operation. Fire Drill will not call it."
            )
        payload = filter_arguments(schema, arguments)
        response = httpx.post(
            f"{self.base_url}/agents/{self.agent_id}/ops/{name}",
            headers=self._headers(),
            json=payload,
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise AdapterError(f"POST /ops/{name} returned {response.status_code}.")
        body = response.json()
        if isinstance(body, dict):
            return body
        return {"result": body}

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
        if channel != "room":
            raise NotSupported(
                "Switch has no private direct-message call. "
                "send_targeted_message(body, target_names, target_roles, thread_id) is in "
                "the operation catalog, but other participants still see that message in the room. "
                "Missing: a private channel. Fire Drill will not put a canary reveal in the room."
            )
        # POST /agents/{id}/message accepts {room_id, content} only. thread_id belongs
        # to the post_message operation, which needs a connected session. The body
        # still goes to the room.
        self.post_room(body)
        message = RoomMessage(
            seq=len(self._sent) + 1,
            id=f"switch-{len(self._sent) + 1}",
            ts=ts or "",
            author=author,
            role=role,
            thread_id=thread_id,
            body=body,
            channel=channel,
        )
        self._sent.append(message)
        return message

    def read_room(self) -> list[RoomMessage]:
        remote = self._read_context_messages()
        sent = [message for message in self._sent if message.channel == "room"]
        if not _covers(remote, sent):
            raise AdapterError(
                "Switch read_context did not include the room posts this process already sent. "
                "Missing: those posts on the room timeline. read_context returns the connected "
                "room, or the room passed as room_id when that argument is in the schema. "
                "Fire Drill will not pretend the posts were visible."
            )
        return assign_stable_seq(self._seqs, _align(sent, remote))

    def read_channel(self, channel: str) -> list[RoomMessage]:
        if channel == "room":
            return self.read_room()
        raise NotSupported(
            f"Switch has no confirmed read for {channel}. "
            "read_context returns the room timeline only. "
            "Missing: a private-channel read."
        )

    def _read_context_messages(self) -> list[RoomMessage]:
        try:
            payload = self.call_operation("read_context", {"room_id": self.room_id, "limit": 200})
        except NotSupported:
            raise
        except AdapterError as exc:
            text = str(exc)
            if "does not list" in text or "no properties" in text:
                raise NotSupported(
                    "read_context is listed, but its schema does not accept the published "
                    "arguments room_id and limit. Missing: those argument names. "
                    f"Detail: {exc}"
                ) from exc
            raise
        return messages_from_context(payload)

    def add_reaction(self, *, message_id: str, user: str, emoji: str, ts: str | None = None) -> None:
        del message_id, user, emoji, ts
        raise NotSupported(
            "Switch has no reaction operation. The messaging catalog lists post_message, "
            "send_targeted_message, and read_context. Missing: a reaction call. "
            "Use /approve or /reject in the room."
        )


def _covers(remote: list[RoomMessage], sent: list[RoomMessage]) -> bool:
    have = Counter(message.body for message in remote)
    for message in sent:
        if have[message.body] <= 0:
            return False
        have[message.body] -= 1
    return True


def _align(sent: list[RoomMessage], remote: list[RoomMessage]) -> list[RoomMessage]:
    """Keep the author and timestamp this process posted when the body matches."""

    pool: dict[str, list[RoomMessage]] = {}
    for message in sent:
        pool.setdefault(message.body, []).append(message)
    aligned: list[RoomMessage] = []
    for message in remote:
        bucket = pool.get(message.body)
        if bucket:
            local = bucket.pop(0)
            aligned.append(
                message.model_copy(
                    update={
                        "author": local.author,
                        "role": local.role,
                        "ts": local.ts or message.ts,
                        "channel": local.channel,
                        "thread_id": local.thread_id or message.thread_id,
                    }
                )
            )
        else:
            aligned.append(message)
    return aligned
