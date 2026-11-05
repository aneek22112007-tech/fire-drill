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

    def complete(self, system: str, user: str) -> str:
        if self.offline:
            return user.strip()
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Grok returned an empty completion")
        return content.strip()
