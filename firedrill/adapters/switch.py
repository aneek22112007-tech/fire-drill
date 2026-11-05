"""Switch adapter. Calls that are not in the published agent protocol are refused.

Verified:
- GET /health
- POST /agents/{agent_id}/message with JSON {room_id, content}
- GET /agents/{agent_id}/ops
- POST /agents/{agent_id}/ops/{operation} with Authorization: Bearer
  and an optional X-Switch-Connection-Id

Operation arguments are sent only when the ops schema lists them.
Argument names are not hardcoded for send_targeted_message or read_context.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from firedrill.adapters.base import AdapterError
from firedrill.models import RoomMessage


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


def probe_switch() -> str:
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
    adapter = SwitchAdapter(base, agent_id, token, room_id, connection)
    adapter.post_room("Fire Drill Switch adapter is up.")
    return f"switch ready at {base} room {room_id}"


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
            raise AdapterError(f"GET /ops did not list {name}. Fire Drill will not call it.")
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

