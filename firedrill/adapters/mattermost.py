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


