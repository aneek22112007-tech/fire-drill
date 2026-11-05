"""Answer-key commitment. SHA-256(key.json bytes + newline + salt)."""

from __future__ import annotations

import base64
import hashlib
import re


