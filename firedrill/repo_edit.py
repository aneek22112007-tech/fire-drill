"""Apply the worker's structured edits and render a unified diff.

This module never runs a shell. Canary text is not applied here.
"""

from __future__ import annotations

import difflib
import shutil
import tempfile
from pathlib import Path

from firedrill.models import Action


