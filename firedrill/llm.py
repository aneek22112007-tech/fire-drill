"""One LLM client. Offline mode returns the template and does not call the network.

Any OpenAI-compatible chat completions provider (xAI Grok, Groq, ...).
Config: ``LLM_API_KEY`` / ``LLM_BASE_URL`` / ``LLM_MODEL`` / ``LLM_PROVIDER``,
each falling back to the original ``XAI_*`` names. 429/5xx responses are
retried a bounded number of times (Retry-After honoured, capped), and an
optional minimum interval spaces calls to stay inside free-tier rate limits. The key is read only from
the server environment and never appears in errors, logs, or API responses.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import httpx


class LLMError(RuntimeError):
    """Provider failure with a message that is safe to show and log."""


def _env(name: str, legacy: str, default: str = "") -> str:
    return (os.environ.get(name, "").strip() or os.environ.get(legacy, "").strip() or default)


def _float_env(name: str, default: float, cap: float) -> float:
    try:
        value = float(os.environ.get(name, "") or default)
    except ValueError:
        value = default
    return min(max(0.0, value), cap)


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


class LLM:
    def __init__(
        self,
        offline: bool | None = None,
        *,
        client: httpx.Client | None = None,
        sleep=time.sleep,  # injectable for tests
        clock=time.monotonic,
    ) -> None:
        key = _env("LLM_API_KEY", "XAI_API_KEY")
        if offline is None:
            offline = not key
        self.offline = offline or not key
        self._key = key
        self.model = _env("LLM_MODEL", "XAI_MODEL", "grok-4.7")
        self.base_url = _env("LLM_BASE_URL", "XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")
        self.provider = os.environ.get("LLM_PROVIDER", "").strip() or ("xai" if "x.ai" in self.base_url else "openai-compatible")
        self.max_retries = min(_int_env("LLM_MAX_RETRIES", 2), 5)
        self.retry_cap = _float_env("LLM_RETRY_AFTER_CAP_SECONDS", 20.0, 60.0)
        self.min_interval = _float_env("LLM_MIN_INTERVAL_SECONDS", 0.0, 30.0)
        self._sleep = sleep
        self._clock = clock
        self._last = None
        self.timeout = float(_int_env("LLM_TIMEOUT_SECONDS", 30))
        self.max_tokens = _int_env("LLM_MAX_TOKENS", 200)
        self.max_calls = _int_env("LLM_MAX_CALLS_PER_RUN", 60)
        self.calls = 0
        self._lock = threading.Lock()
        self._client = client

    def __repr__(self) -> str:  # never include the key
        return f"LLM(provider={self.provider!r}, model={self.model!r}, offline={self.offline})"

    def _wait_interval(self) -> None:
        if self.min_interval and self._last is not None:
            remaining = self.min_interval - (self._clock() - self._last)
            if remaining > 0:
                self._sleep(remaining)

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        header = response.headers.get("retry-after", "")
        try:
            delay = float(header)
        except ValueError:
            delay = 2.0 * (2**attempt)
        return min(max(0.0, delay), self.retry_cap)

    def complete(self, system: str, user: str) -> str:
        if self.offline:
            return user.strip()
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
        attempt = 0
        while True:
            with self._lock:  # every attempt, retries included, spends budget
                if self.calls >= self.max_calls:
                    raise LLMError(f"LLM call budget of {self.max_calls} per run exhausted")
                self.calls += 1
            self._wait_interval()
            self._last = self._clock()
            try:
                post = self._client.post if self._client is not None else httpx.post
                response = post(url, headers=headers, json=body, timeout=self.timeout)
            except httpx.TimeoutException:
                raise LLMError("LLM provider timed out") from None
            except httpx.HTTPError as exc:
                raise LLMError(f"LLM provider unreachable ({exc.__class__.__name__})") from None
            if (response.status_code == 429 or response.status_code >= 500) and attempt < self.max_retries:
                self._sleep(self._retry_delay(response, attempt))
                attempt += 1
                continue
            break
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
