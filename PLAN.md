# Fire Drill plan

Chaos engineering for human oversight of AI agents. Each milestone is implemented, tested, run, and committed before the next one starts.

## Discovery (2026-11-05)

| Check | Result |
| --- | --- |
| OS | macOS 27.3, Darwin 27.3.0, arm64 |
| Python | 3.13.7 (`/usr/local`), 3.12.15 (`/opt/homebrew`). No 3.11 binary. Project requires `>=3.11` and is pinned to 3.12 via uv. |
| uv | 0.11.3 |
| Node | v22.20.0 (not used) |
| Docker | CLI 29.9.2 and Compose v5.6.1 installed. Daemon was not running at discovery (`~/.docker/run/docker.sock` missing). Docker Desktop was launched during the build. |
| Mattermost | Not installed, nothing listening on port 8065. |
| Switch | Switch Console is not installed. No `switch` CLI on `PATH`, no `~/.switch` or `~/.config/switch`. `/usr/bin/kswitch` is Kerberos, not Switch. |
| Git | `aneek22112007-tech <aneek22112007@gmail.com>` from the global config. |

Switch room templates and the agent protocol were read from the published docs, not invented:

- Template language: [docs/TEMPLATES.md](https://github.com/sandbox-quantum/switch/blob/main/docs/TEMPLATES.md) and the worked example `triage-pair.template.yaml`.
- Agent protocol: <https://docs.switchagents.ai/switch-rooms/internals/agent-protocol> (`GET /health`, `POST /agents/{id}/message` with `{room_id, content}`, `GET /agents/{id}/ops`, `POST /agents/{id}/ops/{operation}`).
- Mattermost API v4: bearer personal access tokens, `POST /api/v4/posts`, `POST /api/v4/reactions`, `GET /api/v4/users/me`.
- Grok: `POST https://api.x.ai/v1/chat/completions`, model `grok-4.7`, bearer `XAI_API_KEY`.

Anything not confirmed by those docs stays behind `adapters/` and is implemented only on `LocalAdapter` until a live call succeeds.

## Milestones

### M1 — Skeleton and bus

Package, CLI entry, pydantic models, and a SQLite `LocalAdapter` that stores author, role, timestamp, thread, and channel. Test: post three messages and read them back in commit order.

### M2 — Worker and executor

The worker proposes real edits on `sample_repo/` (patch version bump, config change, add a function and a test) and posts an `ApprovalRequest`. `executor.py` applies the action only when the id is in the worker registry and the HMAC made with `WORKER_SECRET` matches. Test: an approval changes the tree and its tests pass; a rejection leaves the tree untouched.

### M3 — Canary library and canary agent

`canaries/library.yaml` holds 12 flaws. The canary posts requests through the same formatter and id shape as the worker, sends `{request_id → flaw_id}` to the auditor service, and does not keep a copy. Test: a canary id is absent from the worker registry, so the executor refuses it.

### M4 — Answer-key isolation

`make setup-auditor` creates `auditor_private/` mode `0700` and, where the OS allows it without an interactive password, the `firedrill-auditor` user. The default path is a token-gated FastAPI service on `127.0.0.1`: the canary holds a write-only ingest token, and only the auditor token can read `key.json`. At start the auditor posts `SHA-256(key.json bytes + newline + salt)`. At the end it posts the key and the salt. Tests: worker and canary receive 401 on the key; the revealed commitment matches.

