"""One LLM client. Offline mode returns the template and does not call the network.

Provider: xAI Grok via the OpenAI-compatible chat completions API. Any
compatible endpoint works through ``XAI_BASE_URL``. The key is read only from
the server environment and never appears in errors, logs, or API responses.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import httpx


class LLMError(RuntimeError):
    """Provider failure with a message that is safe to show and log."""


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


class LLM:
    def __init__(self, offline: bool | None = None, *, client: httpx.Client | None = None) -> None:
        key = os.environ.get("XAI_API_KEY", "").strip()
        if offline is None:
            offline = not key
        self.offline = offline or not key
        self._key = key
        self.model = os.environ.get("XAI_MODEL", "grok-4.7")
        self.base_url = os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")
        self.timeout = float(_int_env("LLM_TIMEOUT_SECONDS", 30))
        self.max_tokens = _int_env("LLM_MAX_TOKENS", 200)
        self.max_calls = _int_env("LLM_MAX_CALLS_PER_RUN", 60)
        self.calls = 0
        self._lock = threading.Lock()
        self._client = client

    def __repr__(self) -> str:  # never include the key
        return f"LLM(model={self.model!r}, offline={self.offline})"

    def complete(self, system: str, user: str) -> str:
        if self.offline:
            return user.strip()
        with self._lock:
            if self.calls >= self.max_calls:
                raise LLMError(f"LLM call budget of {self.max_calls} per run exhausted")
            self.calls += 1
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user[:4000]},
            ],
            "stream": False,
            "max_tokens": self.max_tokens,
        }
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        url = f"{self.base_url}/chat/completions"
        try:
            if self._client is not None:
                response = self._client.post(url, headers=headers, json=body, timeout=self.timeout)
            else:
                response = httpx.post(url, headers=headers, json=body, timeout=self.timeout)
        except httpx.TimeoutException:
            raise LLMError("LLM provider timed out") from None
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM provider unreachable ({exc.__class__.__name__})") from None
        if response.status_code >= 400:
            raise LLMError(f"LLM provider returned HTTP {response.status_code}")
        try:
            payload: dict[str, Any] = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError("LLM provider returned an unexpected payload") from None
        if not isinstance(content, str) or not content.strip():
            raise LLMError("LLM provider returned an empty completion")
        return content.strip()[:1000]
