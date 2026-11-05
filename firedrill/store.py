"""Private auditor database. The room never reads this file."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from firedrill.models import Decision


class AuditorStore:
