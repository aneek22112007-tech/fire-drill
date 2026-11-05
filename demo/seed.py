"""Build the seeded drill the offline demo and the replay share.

The seed is 20261105. Request ids, canary placement, the salt, and the demo
answer-key seal all come from that seed. Replay reads demo/recorded_drill.jsonl
and does not roll them again.
"""

from __future__ import annotations

from firedrill.paths import default_paths
from firedrill.simulate import SEED, build_events, run_demo

__all__ = ["SEED", "build_events", "run_demo"]


def main() -> None:
    headline = run_demo(default_paths(), offline=True)
    print(headline)


if __name__ == "__main__":
    main()
