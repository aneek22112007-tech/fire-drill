#!/usr/bin/env python3
"""Create auditor_private and, when the OS allows it, the firedrill-auditor user.

Creating a macOS user needs an administrator password. This script tries a
non-interactive sudo. When that is refused it keeps going: the directory is
mode 0700 and the token-gated service is the isolation boundary.
"""

from __future__ import annotations

import json
import os
import secrets
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDITOR_DIR = ROOT / "auditor_private"
USER_NAME = "firedrill-auditor"


