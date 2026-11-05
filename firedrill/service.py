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


class MappingIn(BaseModel):
    request_id: str
    flaw_id: str


def create_app(key_file: Path, tokens_file: Path, drill_db: Path) -> FastAPI:
    key_path = Path(key_file)
    tokens = load_tokens(tokens_file)
    store = AuditorStore(drill_db)
    app = FastAPI(title="Fire Drill auditor", docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.key_path = key_path
    app.state.tokens = tokens

    def presented(authorization: str | None) -> str:
        if not authorization or not authorization.startswith(_BEARER):
            return ""
        return authorization[len(_BEARER) :].strip()

    def require_auditor(authorization: str | None) -> None:
        if presented(authorization) != tokens["auditor_token"]:
            raise HTTPException(status_code=401, detail="unauthorized")

    def require_ingest(authorization: str | None) -> None:
        token = presented(authorization)
        allowed = {tokens["auditor_token"], tokens["canary_ingest_token"]}
        if token not in allowed:
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/mappings", status_code=201)
    def add_mapping(body: MappingIn, authorization: str | None = Header(default=None)) -> dict[str, str]:
        require_ingest(authorization)
        store.add_mapping(body.request_id, body.flaw_id)
        return {"status": "stored"}

    @app.get("/mappings/{request_id}")
    def get_mapping(request_id: str, authorization: str | None = Header(default=None)) -> dict[str, str]:
        require_auditor(authorization)
        flaw_id = store.mapping_for(request_id)
        if flaw_id is None:
            raise HTTPException(status_code=404, detail="unknown request")
        return {"request_id": request_id, "flaw_id": flaw_id}

    @app.get("/key")
    def read_key(authorization: str | None = Header(default=None)) -> dict[str, object]:
        require_auditor(authorization)
        raw = key_path.read_bytes()
        return {"key": json.loads(raw.decode("utf-8")), "bytes": raw.decode("utf-8")}

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(authorization: str | None = Header(default=None)) -> str:
        require_auditor(authorization)
        return render_dashboard(store)

    return app
