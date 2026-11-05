"""Seeded drill player. The same event list produces the same report.

Flatness adaptations are recorded by the session while the drill plays.
Route and batch adaptations are events, so a replay does not invent a second copy.
The simulated clock is the timestamps in the events. Nothing here sleeps.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from firedrill.adapt import (
    assign_canary,
    is_flat,
    note_canary,
    note_high_risk,
    note_low_risk_batch,
    note_round_robin,
    route_high_risk,
    take_low_risk_batch,
)
from firedrill.adapters.base import RoomBus
from firedrill.adapters.local import LocalAdapter
from firedrill.agents.auditor import Auditor
from firedrill.agents.canary import Canary, load_library
from firedrill.agents.worker import Worker, make_function
from firedrill.agents.worker import describe_action
from firedrill.bus import voiced
from firedrill.executor import Executor
from firedrill.humans import REVIEWERS, latency_seconds, review
from firedrill.ingest import MappingClient
from firedrill.llm import LLM
from firedrill.models import Action
from firedrill.paths import DrillPaths
from firedrill.registry import WorkerRegistry
from firedrill.repo_edit import bump_patch, read_version
from firedrill.report import write_report
from firedrill.service import running_auditor
from firedrill.session import DrillSession
from firedrill.store import AuditorStore, load_tokens
from firedrill.timeutil import add_seconds, parse_ts, seconds_between

SEED = 20261106
REAL_ITEMS = 50
CANARY_ITEMS = 12
TOTAL_ITEMS = REAL_ITEMS + CANARY_ITEMS
BATCH_SIZE = 3
BASE_TS = "2026-11-05T15:00:00.000Z"
_LLM_SYSTEM = "Rewrite the change as one sentence. Keep every concrete value."
_EXPLAIN = "I read the diff and it matches the summary."


@dataclass
class Item:
    request_id: str
    is_canary: bool
    risk: str
    complexity: int
    public_summary: str
    diff: str
    change: str
    action: dict[str, object] | None
    flaw_id: str | None


def demo_key_bytes(seed: int) -> bytes:
    """A demo seal derived from the seed. It is revealed at the end of the drill."""

    payload = {
        "drill_key": hashlib.sha256(f"fire-drill-demo-{seed}".encode("utf-8")).hexdigest(),
        "purpose": "fire-drill answer-key seal",
        "version": 1,
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def demo_salt(seed: int) -> str:
    digest = hashlib.sha256(f"fire-drill-salt-{seed}".encode("utf-8")).hexdigest()
    return "fd-salt-" + digest[:8]


def read_events(path: Path) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def write_events(path: Path, events: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(json.dumps(event, sort_keys=True) + "\n" for event in events)
    path.write_text(rendered, encoding="utf-8")


def build_events(paths: DrillPaths, *, offline: bool, seed: int = SEED) -> list[dict[str, object]]:
    flaws = load_library(paths.library)
    if len(flaws) != CANARY_ITEMS:
        raise RuntimeError(f"canary library has {len(flaws)} flaws, expected {CANARY_ITEMS}")
    by_id = {flaw.id: flaw for flaw in flaws}
    rng = random.Random(seed)
    slots = set(rng.sample(range(TOTAL_ITEMS), CANARY_ITEMS))
    order = [flaw.id for flaw in flaws]
    rng.shuffle(order)
    flaw_at = {slot: order[index] for index, slot in enumerate(sorted(slots))}
    used: set[str] = set()

    def next_id() -> str:
        while True:
            request_id = f"fd-{rng.getrandbits(32):08x}"
            if request_id not in used:
                used.add(request_id)
                return request_id

    llm = LLM(offline=True if offline else None)
    version = read_version(paths.sample_repo)
    kind_i = 0
    flag_n = 0
    fn_n = 0
    real_i = 0
    items: list[Item] = []
    for slot in range(TOTAL_ITEMS):
        if slot in flaw_at:
            flaw = by_id[flaw_at[slot]]
            items.append(
                Item(
                    request_id=next_id(),
                    is_canary=True,
                    risk=flaw.risk,
                    complexity=flaw.complexity,
                    public_summary=flaw.template.format(change=flaw.summary),
                    diff=flaw.diff.strip() + "\n",
                    change=flaw.summary,
                    action=None,
                    flaw_id=flaw.id,
                )
            )
            continue
        action = _real_action(
            real_i,
            version=version,
            kind_i=kind_i,
            flag_n=flag_n,
            fn_n=fn_n,
        )
        version = action.version or version
        if action.kind == "version_bump":
            kind_i += 1
        elif action.kind == "add_function":
            kind_i += 1
            fn_n += 1
        elif action.key != "max_connections":
            kind_i += 1
            flag_n += 1
        change, risk, complexity = describe_action(action)
        change = llm.complete(_LLM_SYSTEM, change)
        items.append(
            Item(
                request_id=next_id(),
                is_canary=False,
                risk=risk,
                complexity=complexity,
                public_summary=voiced(change),
                diff="",
                change=change,
                action=action.model_dump(mode="json"),
                flaw_id=None,
            )
        )
        real_i += 1
    if real_i != REAL_ITEMS:
        raise RuntimeError(f"built {real_i} real items, expected {REAL_ITEMS}")

    profiles = {row["id"]: row["profile"] for row in REVIEWERS}
    reviewers = [row["id"] for row in REVIEWERS]
    careful = next(row["id"] for row in REVIEWERS if row["profile"] == "careful")
    last_ts: dict[str, str | None] = {reviewer: None for reviewer in reviewers}
    latencies: dict[str, list[float]] = {reviewer: [] for reviewer in reviewers}
    canary_counts = {reviewer: 0 for reviewer in reviewers}
    medium_counts = {reviewer: 0 for reviewer in reviewers}
    needs_explain: set[str] = set()
    cursor = 0
    medium_cursor = 0
    events: list[dict[str, object]] = [
        {
            "kind": "meta",
            "seed": seed,
            "salt": demo_salt(seed),
            "key_b64": base64.b64encode(demo_key_bytes(seed)).decode("ascii"),
        }
    ]
    clock = BASE_TS
    for reviewer in reviewers:
        events.append({"kind": "optin", "reviewer": reviewer, "ts": clock})
        clock = add_seconds(clock, 1)
    events.append({"kind": "start", "salt": demo_salt(seed), "ts": clock})
    clock = add_seconds(clock, 1)

    def emit(group: list[Item], note_rule: str | None, at: str) -> str:
        nonlocal cursor, medium_cursor
        if note_rule == "batch" and len(group) >= 2:
            note = note_low_risk_batch(len(group))
            events.append(_note(note.rule, note.reviewer, note.reason, at))
            at = add_seconds(at, 0.05)
        posted: list[tuple[Item, str]] = []
        for item in group:
            events.append(_post(item, at))
            posted.append((item, at))
            at = add_seconds(at, 0.05)
        for item, post_ts in posted:
            if item.is_canary:
                reviewer = assign_canary(reviewers, canary_counts, careful)
                note = note_canary(reviewer, canary_counts[reviewer])
                canary_counts[reviewer] += 1
                events.append(_note(note.rule, note.reviewer, note.reason, at))
                at = add_seconds(at, 0.05)
            elif note_rule == "each":
                if item.risk == "high":
                    reviewer = route_high_risk(reviewers, last_ts)
                    note = note_high_risk(reviewers, last_ts)
                else:
                    reviewer = reviewers[medium_cursor % len(reviewers)]
                    medium_cursor += 1
                    note = note_round_robin(reviewer, medium_counts[reviewer])
                    medium_counts[reviewer] += 1
                events.append(_note(note.rule, note.reviewer, note.reason, at))
                at = add_seconds(at, 0.05)
            else:
                reviewer = reviewers[cursor % len(reviewers)]
                cursor += 1
            at = _decide(
                item,
                reviewer,
                post_ts,
                at,
                events,
                profiles,
                last_ts,
                latencies,
                needs_explain,
            )
        return at

    pending: list[Item] = []
    for item in items:
        if item.risk == "low":
            pending.append(item)
            released = take_low_risk_batch(pending, BATCH_SIZE)
            if released:
                clock = emit(released, "batch", clock)
            continue
        if pending:
            held = list(pending)
            pending.clear()
            clock = emit(held, "batch" if len(held) >= 2 else None, clock)
        clock = emit([item], "each", clock)
    if pending:
        held = list(pending)
        pending.clear()
        clock = emit(held, "batch" if len(held) >= 2 else None, clock)
    events.append({"kind": "reveal", "ts": clock})
    return events


def run_demo(paths: DrillPaths, *, offline: bool) -> str:
    events = build_events(paths, offline=offline)
    write_events(paths.recorded, events)
    return play(paths, read_events(paths.recorded))


def replay(paths: DrillPaths, recording: Path) -> str:
    return play(paths, read_events(recording))


def play(
    paths: DrillPaths,
    events: list[dict[str, object]],
    bus: RoomBus | None = None,
) -> str:
    meta = next(event for event in events if event.get("kind") == "meta")
    key_bytes = base64.b64decode(str(meta["key_b64"]), validate=True)
    secret = os.environ.get("WORKER_SECRET", "").strip() or "firedrill-demo-worker-secret"
    _reset(paths)
    server = running_auditor(paths)
    base = server.__enter__()
    try:
        submit = MappingClient(base, load_tokens(paths.tokens_file)["canary_ingest_token"]).submit
        created: LocalAdapter | None = None
        if bus is None:
            created = LocalAdapter(paths.room_db)
            bus = created
        store = AuditorStore(paths.drill_db)
        registry = WorkerRegistry(paths.registry_db, secret.encode("utf-8"))
        flaws = {flaw.id: flaw for flaw in load_library(paths.library)}
        session = DrillSession(
            bus=bus,
            store=store,
            executor=Executor(registry, paths.work_repo),
            required=[row["id"] for row in REVIEWERS],
            flaws=flaws,
            key_bytes=key_bytes,
        )
        auditor = Auditor(session)
        worker = Worker(registry, bus, paths.work_repo)
        canary = Canary(bus, submit)
        for index, event in enumerate(events):
            kind = str(event["kind"])
            if kind == "meta":
                continue
            if kind == "optin":
                result = _speak(bus, auditor, str(event["reviewer"]), "/optin", str(event["ts"]))
                if result != "opted-in":
                    raise RuntimeError(f"event {index}: optin returned {result}")
                continue
            if kind == "start":
                auditor.start(str(event["salt"]), str(event["ts"]))
                continue
            if kind == "adaptation":
                reviewer = event.get("reviewer")
                store.record_adaptation(
                    ts=str(event["ts"]),
                    rule=str(event["rule"]),
                    reviewer=None if reviewer is None else str(reviewer),
                    reason=str(event["reason"]),
                )
                continue
            if kind == "real":
                worker.propose(
                    Action.model_validate(event["action"]),
                    summary=str(event["summary"]),
                    risk=str(event["risk"]),  # type: ignore[arg-type]
                    complexity=int(event["complexity"]),
                    request_id=str(event["id"]),
                    ts=str(event["ts"]),
                )
                continue
            if kind == "canary":
                canary.post_flaw(flaws[str(event["flaw_id"])], request_id=str(event["id"]), ts=str(event["ts"]))
                continue
            if kind == "command":
                result = _speak(bus, auditor, str(event["reviewer"]), str(event["line"]), str(event["ts"]))
                expected = str(event["expect"])
                if result != expected:
                    raise RuntimeError(
                        f"event {index}: {event['line']!r} returned {result}, expected {expected}"
                    )
                continue
            if kind == "reveal":
                auditor.reveal(str(event["ts"]))
                continue
            raise RuntimeError(f"event {index}: unknown kind {kind}")
        _sample_tests(paths.work_repo)
        return write_report(store, paths.report)
    finally:
        try:
            if "registry" in locals():
                registry.close()
            if "store" in locals():
                store.close()
            if "created" in locals() and created is not None:
                created.close()
        finally:
            server.__exit__(*sys.exc_info())


def _speak(bus: RoomBus, auditor: Auditor, reviewer: str, line: str, ts: str) -> str:
    """Post a reviewer line, then read /approve /reject /explain /optin back off the bus."""

    bus.post(author=reviewer, role="human", body=line, channel="room", ts=ts)
    results = auditor.ingest_commands()
    if not results:
        raise RuntimeError(f"room did not return a command for {reviewer}: {line}")
    return results[-1]


def _real_action(
    real_i: int,
    *,
    version: str,
    kind_i: int,
    flag_n: int,
    fn_n: int,
) -> Action:
    if real_i % 10 == 0:
        # Stays at or below the documented cap of 100, and moves off the stock value.
        return Action(kind="config_set", key="max_connections", value=min(100, 30 + real_i))
    kind = kind_i % 3
    if kind == 0:
        return Action(kind="version_bump", version=bump_patch(version))
    if kind == 1:
        return Action(kind="config_set", key=f"feature_{flag_n + 1:02d}", value=True)
    return make_function(fn_n + 1)


def _post(item: Item, ts: str) -> dict[str, object]:
    if item.is_canary:
        return {"kind": "canary", "id": item.request_id, "flaw_id": item.flaw_id, "ts": ts}
    return {
        "kind": "real",
        "id": item.request_id,
        "ts": ts,
        "summary": item.change,
        "risk": item.risk,
        "complexity": item.complexity,
        "action": item.action,
    }


def _note(rule: str, reviewer: str | None, reason: str, ts: str) -> dict[str, object]:
    return {"kind": "adaptation", "rule": rule, "reviewer": reviewer, "reason": reason, "ts": ts}


def _decide(
    item: Item,
    reviewer: str,
    post_ts: str,
    clock: str,
    events: list[dict[str, object]],
    profiles: dict[str, str],
    last_ts: dict[str, str | None],
    latencies: dict[str, list[float]],
    needs_explain: set[str],
) -> str:
    if item.is_canary:
        action, reason = review(profiles[reviewer], item.public_summary, item.diff)
    else:
        action, reason = "approve", ""
    raw = latency_seconds(profiles[reviewer], item.complexity)
    decision_ts = add_seconds(post_ts, raw)
    actual = seconds_between(post_ts, decision_ts)
    if action == "approve" and reviewer in needs_explain:
        explain_ts = clock if parse_ts(clock) < parse_ts(decision_ts) else post_ts
        events.append(
            {
                "kind": "command",
                "reviewer": reviewer,
                "line": f"/explain {item.request_id} {_EXPLAIN}",
                "ts": explain_ts,
                "expect": "explained",
            }
        )
    if action == "approve":
        line = f"/approve {item.request_id}"
        expect = "approve"
    else:
        line = f"/reject {item.request_id} {reason}"
        expect = "reject"
    events.append(
        {
            "kind": "command",
            "reviewer": reviewer,
            "line": line,
            "ts": decision_ts,
            "expect": expect,
        }
    )
    latencies[reviewer].append(actual)
    last_ts[reviewer] = decision_ts
    if action == "approve":
        needs_explain.discard(reviewer)
    if is_flat(latencies[reviewer]) and reviewer not in needs_explain:
        needs_explain.add(reviewer)
    if parse_ts(decision_ts) > parse_ts(clock):
        return add_seconds(decision_ts, 0.05)
    return add_seconds(clock, 0.05)


def _reset(paths: DrillPaths) -> None:
    paths.ensure()
    for db in (paths.room_db, paths.registry_db, paths.drill_db):
        _unlink_db(db)
    if paths.work_repo.exists():
        shutil.rmtree(paths.work_repo)
    shutil.copytree(
        paths.sample_repo,
        paths.work_repo,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _unlink_db(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix) if suffix else path
        if candidate.exists():
            candidate.unlink()


def _sample_tests(repo: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--rootdir",
            str(repo),
            "-c",
            str(repo / "pytest.ini"),
            str(repo / "tests"),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "sample repo tests failed after the drill\n"
            + completed.stdout
            + completed.stderr
        )
