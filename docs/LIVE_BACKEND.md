# Live backend

`firedrill web` serves `public/` and a small JSON API from one FastAPI process.

| Route | Auth | Purpose |
|---|---|---|
| `GET /api/health` | none | provider readiness (no key material), runs enabled, active run |
| `GET /api/metrics/latest` | none | aggregate metrics of the latest successful run (404 → dashboard uses the recorded export) |
| `GET /api/runs`, `GET /api/runs/{id}` | none | run status: mode, model, LLM call count, safe error |
| `POST /api/runs` `{"mode":"live"\|"offline"}` | `Bearer FIREDRILL_ADMIN_TOKEN` | start a drill |

## Modes

- **live-llm**: each of the 50 real Worker proposals is rewritten by xAI Grok
  (`XAI_API_KEY`, `XAI_MODEL`, `XAI_BASE_URL`, OpenAI-compatible chat completions).
- **offline-template**: same drill, no network calls. Labelled as such everywhere.

Reviewers are **simulated** (Avery, Blake, Casey) in both modes, and the API reports
`switch_room: false`. A live Switch room needs `firedrill up --adapter switch` with
real Switch credentials; that path has not been verified against a live server.

## Safety

- Canary isolation is unchanged: canary ids are never registered, so the executor refuses them.
- Each run uses its own directory; the answer key is deleted when the run ends.
  Stored/returned data passes `assert_public` (no flaw ids, request ids, tokens, or key names).
- Provider key: server env only; never returned, logged, or sent to the browser. Provider
  errors are reduced to status/class (e.g. `HTTP 401`).
- Limits: admin token (constant-time compare), failed-auth throttle (10 / 5 min / IP),
  one run at a time, cooldown, daily cap, per-run LLM call budget, max tokens, timeout,
  1 KB request bodies, strict request schema.

## Storage

Run summaries are JSON files in `FIREDRILL_DATA_DIR`. On Render's free plan the disk is
ephemeral: history resets on restart, redeploy, or spin-down. Durable history needs a paid
instance with a persistent disk (or Postgres; not implemented).

## Local

```bash
uv sync --python 3.12
FIREDRILL_ADMIN_TOKEN=dev uv run firedrill web --port 8000
curl -XPOST -H 'Authorization: Bearer dev' -H 'Content-Type: application/json' \
  -d '{"mode":"offline"}' localhost:8000/api/runs
```
