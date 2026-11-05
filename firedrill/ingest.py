"""Canary-side client for POST /mappings. It has no method that reads the key."""

from __future__ import annotations

import httpx


class MappingClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._url = base_url.rstrip("/") + "/mappings"
        self._headers = {"Authorization": f"Bearer {token}"}

    def submit(self, request_id: str, flaw_id: str) -> None:
        response = httpx.post(
            self._url,
            json={"request_id": request_id, "flaw_id": flaw_id},
            headers=self._headers,
            timeout=10.0,
        )
        if response.status_code != 201:
            raise RuntimeError(
                f"POST /mappings returned HTTP {response.status_code}. "
                "The canary ingest token is write-only."
            )
