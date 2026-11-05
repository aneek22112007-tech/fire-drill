"""Worker-signed registry. The executor trusts an id only when the HMAC matches."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
from pathlib import Path

from firedrill.models import Action


class RegistryError(RuntimeError):
    pass


