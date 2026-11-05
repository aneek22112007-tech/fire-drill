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


