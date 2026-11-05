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


