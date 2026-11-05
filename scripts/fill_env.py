#!/usr/bin/env python3
"""Fill empty secrets in .env from auditor_private/tokens.json. Never prints them."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TOKENS = ROOT / "auditor_private" / "tokens.json"


