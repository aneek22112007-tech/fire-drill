"""One LLM client. Offline mode returns the template and does not call the network."""

from __future__ import annotations

import os
from typing import Any

import httpx


class LLM:
