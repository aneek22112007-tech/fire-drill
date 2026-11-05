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


