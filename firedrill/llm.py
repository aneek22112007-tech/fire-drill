"""One LLM client. Offline mode returns the template and does not call the network."""

from __future__ import annotations

import os
from typing import Any

import httpx


class LLM:
    def __init__(self, offline: bool | None = None) -> None:
        key = os.environ.get("XAI_API_KEY", "").strip()
        if offline is None:
            offline = not key
        self.offline = offline or not key
        self._key = key
        self.model = os.environ.get("XAI_MODEL", "grok-4.7")
        self.base_url = os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")

