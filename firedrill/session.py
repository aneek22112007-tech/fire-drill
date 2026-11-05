"""Consent, decisions, and private canary feedback."""

from __future__ import annotations

from firedrill.adapters.local import LocalAdapter
from firedrill.commands import catch_dm, miss_dm, parse_approval, parse_command
from firedrill.adapt import is_flat
from firedrill.commitment import commitment_hash, commitment_message, reveal_message
from firedrill.executor import Executor, ExecutorRefusal
from firedrill.metrics import median
from firedrill.models import Decision, Flaw
from firedrill.store import AuditorStore
from firedrill.timeutil import seconds_between


class ConsentError(RuntimeError):
    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(
            "drill refused to start; missing /optin from: " + ", ".join(missing)
        )


class DrillSession:
    def __init__(
        self,
        *,
        bus: LocalAdapter,
        store: AuditorStore,
        executor: Executor,
        required: list[str],
        flaws: dict[str, Flaw],
        key_bytes: bytes,
    ) -> None:
        self.bus = bus
        self.store = store
        self.executor = executor
        self.required = list(required)
        self.flaws = flaws
        self.key_bytes = key_bytes
        self.started = False
        self._seen_seq = 0
        self.needs_explain: set[str] = set()
        self.explained_ready: set[str] = set()

    def command(self, reviewer: str, line: str, ts: str) -> str:
        parsed = parse_command(line)
        if parsed is None:
            self._say("auditor", "auditor", f"Unrecognised command from {reviewer}.", ts)
            return "unrecognised"
        if parsed.name == "optin":
            self.store.record_optin(reviewer, ts)
            self._say(reviewer, "human", "/optin", ts)
            return "opted-in"
        if not self.started:
            self._say(
                "auditor",
                "auditor",
                "The drill has not started. It is waiting for /optin from every reviewer.",
                ts,
            )
            return "not-started"
        if parsed.request_id is None:
            return "unrecognised"
        self.sync()
        request = self._request(parsed.request_id)
        if request is None:
            self._say("auditor", "auditor", f"Unknown request {parsed.request_id}.", ts)
            return "unknown"
        if parsed.name == "explain":
            decision = self._decision(request, reviewer, "explain", parsed.text, ts)
            self.explained_ready.add(reviewer)
            self.store.record_decision(decision)
            self._say(
                reviewer,
                "human",
                f"/explain {parsed.request_id} {parsed.text}",
                ts,
                thread_id=self._thread_for(parsed.request_id),
            )
            return "explained"
        if parsed.request_id in self._closed():
            self._say("auditor", "auditor", f"{parsed.request_id} is already decided.", ts)
            return "duplicate"
        if parsed.name == "approve" and reviewer in self.needs_explain and reviewer not in self.explained_ready:
            self._say(
                "auditor",
                "auditor",
                (
                    f"{reviewer} must /explain {parsed.request_id} in one sentence "
                    "before the next approval. Review times were flat, so explain-back is on."
                ),
                ts,
            )
            return "explain-required"
        reason = parsed.text if parsed.name == "reject" else ""
        decision = self._decision(request, reviewer, parsed.name, reason, ts)
        if request["is_canary"]:
            self._canary_feedback(reviewer, request, parsed.name, ts)
        elif parsed.name == "approve":
            try:
                self.executor.execute(parsed.request_id)
            except ExecutorRefusal as exc:
                self._say("auditor", "auditor", str(exc), ts)
                return "refused"
        self.store.record_decision(decision)
        verb = "approved" if parsed.name == "approve" else "rejected"
        detail = f" ({reason})" if reason else ""
        self._say(
            reviewer,
            "human",
            f"{reviewer} {verb} {parsed.request_id}{detail}",
            ts,
            thread_id=self._thread_for(parsed.request_id),
        )
        if parsed.name == "approve":
            self.explained_ready.discard(reviewer)
            self.needs_explain.discard(reviewer)
        self._arm_flatness(reviewer, ts)
        return parsed.name

    def react(self, reviewer: str, message_id: str, emoji: str, ts: str) -> str:
        """Map Mattermost-style reactions onto approve and reject."""

        self.bus.add_reaction(message_id=message_id, user=reviewer, emoji=emoji, ts=ts)
        body = self._message_body(message_id)
        if body is None:
            return "unknown"
        parsed = parse_approval(body)
        if parsed is None:
            return "unknown"
        if emoji in {"white_check_mark", "+1", "approve"}:
            return self.command(reviewer, f"/approve {parsed.id}", ts)
        if emoji in {"x", "-1", "reject"}:
            return self.command(reviewer, f"/reject {parsed.id} rejected by reaction", ts)
        return "ignored"

    def _arm_flatness(self, reviewer: str, ts: str) -> None:
        times = self._review_times(reviewer)
        if not is_flat(times) or reviewer in self.needs_explain:
            return
        self.needs_explain.add(reviewer)
        self.explained_ready.discard(reviewer)
        middle = median(times)
        rendered = "n/a" if middle is None else f"{middle:.3f}"
        self.store.record_adaptation(
            ts=ts,
            rule="flatness_explain_back",
            reviewer=reviewer,
            reason=(
                f"{reviewer} review times are flat (median {rendered}s across {len(times)} "
                "decisions). Explain-back is required before the next approval."
            ),
        )

    def _review_times(self, reviewer: str) -> list[float]:
        return [
            decision.latency_s
            for decision in self.store.decisions()
            if decision.reviewer == reviewer and decision.action in {"approve", "reject"}
        ]

