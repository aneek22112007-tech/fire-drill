"""M4: worker and canary cannot read the key, and the commitment matches the reveal."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from firedrill.commitment import commitment_hash, commitment_message, reveal_message, verify_reveal_text
from firedrill.service import create_app


