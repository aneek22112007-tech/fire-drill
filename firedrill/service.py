"""Token-gated auditor service. Only the auditor token can read the answer key."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from firedrill.report import render_dashboard
from firedrill.store import AuditorStore, load_tokens

_BEARER = "Bearer "


