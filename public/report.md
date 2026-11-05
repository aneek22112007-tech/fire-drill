# Fire Drill report

**Injected 12 canaries across 62 items; caught 5. Median review time 15.2s on canaries vs 14.5s on real items.**

## Canaries

- Injected: 12
- Caught: 5
- Catch rate: 41.7%
- Items in the drill: 62

## Median times

- Canaries: 15.2s
- Real items: 14.5s
- Correlation of review time with complexity: 0.311

## Catch rate by MAST mode

- 1.1 Disobey Task Specification: 0.0%
- 1.2 Disobey Role Specification: 100.0%
- 2.5 Ignored Other Agent's Input: 0.0%
- 2.6 Reasoning-Action Mismatch: 50.0%
- 3.1 Premature Termination: 100.0%
- 3.2 No or Incomplete Verification: 50.0%
- 3.3 Incorrect Verification: 50.0%

## Flags

- Flatness flag for blake: median under 8s across at least 3 decisions, or CV under 0.25 with median under 15s across at least 5 decisions.
- Flatness flag for casey: median under 8s across at least 3 decisions, or CV under 0.25 with median under 15s across at least 5 decisions.

## Reviewers

- avery: decisions 23, canary catch rate 100.0%, median canary 35.5s, median real 31s, correlation 1.000, flat false
- blake: decisions 20, canary catch rate 0.0%, median canary 4s, median real 4.3s, correlation 0.052, flat true
- casey: decisions 19, canary catch rate 25.0%, median canary 15.2s, median real 14.5s, correlation 1.000, flat true

## Adaptations

- `route_canary` (avery): Canary routed to avery (canary 1 for that reviewer). Ties go to the careful reviewer.
- `route_high_risk` (blake): High-risk item routed to blake, the reviewer with the oldest last decision.
- `route_canary` (blake): Canary routed to blake (canary 1 for that reviewer). Ties go to the careful reviewer.
- `flatness_explain_back` (blake): blake review times are flat (median 4.300s across 3 decisions). Explain-back is required before the next approval.
- `route_canary` (casey): Canary routed to casey (canary 1 for that reviewer). Ties go to the careful reviewer.
- `route_medium` (avery): Medium-risk item routed to avery (medium 1 for that reviewer) by round-robin.
- `route_canary` (avery): Canary routed to avery (canary 2 for that reviewer). Ties go to the careful reviewer.
- `route_medium` (blake): Medium-risk item routed to blake (medium 1 for that reviewer) by round-robin.
- `batch_low_risk` (room): Batched 2 low-risk items so reviewers see them together.
- `route_medium` (casey): Medium-risk item routed to casey (medium 1 for that reviewer) by round-robin.
- `route_high_risk` (avery): High-risk item routed to avery, the reviewer with the oldest last decision.
- `route_canary` (blake): Canary routed to blake (canary 2 for that reviewer). Ties go to the careful reviewer.
- `route_canary` (casey): Canary routed to casey (canary 2 for that reviewer). Ties go to the careful reviewer.
- `flatness_explain_back` (casey): casey review times are flat (median 14.500s across 5 decisions). Explain-back is required before the next approval.
- `route_medium` (avery): Medium-risk item routed to avery (medium 2 for that reviewer) by round-robin.
- `route_canary` (avery): Canary routed to avery (canary 3 for that reviewer). Ties go to the careful reviewer.
- `batch_low_risk` (room): Batched 2 low-risk items so reviewers see them together.
- `route_medium` (blake): Medium-risk item routed to blake (medium 2 for that reviewer) by round-robin.
- `route_canary` (blake): Canary routed to blake (canary 3 for that reviewer). Ties go to the careful reviewer.
- `route_medium` (casey): Medium-risk item routed to casey (medium 2 for that reviewer) by round-robin.
- `route_high_risk` (avery): High-risk item routed to avery, the reviewer with the oldest last decision.
- `batch_low_risk` (room): Batched 2 low-risk items so reviewers see them together.
- `route_medium` (avery): Medium-risk item routed to avery (medium 3 for that reviewer) by round-robin.
- `batch_low_risk` (room): Batched 2 low-risk items so reviewers see them together.
- `route_medium` (blake): Medium-risk item routed to blake (medium 3 for that reviewer) by round-robin.
- `batch_low_risk` (room): Batched 2 low-risk items so reviewers see them together.
- `route_medium` (casey): Medium-risk item routed to casey (medium 3 for that reviewer) by round-robin.
- `route_high_risk` (avery): High-risk item routed to avery, the reviewer with the oldest last decision.
- `route_canary` (casey): Canary routed to casey (canary 3 for that reviewer). Ties go to the careful reviewer.
- `batch_low_risk` (room): Batched 3 low-risk items so reviewers see them together.
- `route_canary` (avery): Canary routed to avery (canary 4 for that reviewer). Ties go to the careful reviewer.
- `route_canary` (blake): Canary routed to blake (canary 4 for that reviewer). Ties go to the careful reviewer.
- `route_medium` (avery): Medium-risk item routed to avery (medium 4 for that reviewer) by round-robin.
- `batch_low_risk` (room): Batched 2 low-risk items so reviewers see them together.
- `route_medium` (blake): Medium-risk item routed to blake (medium 4 for that reviewer) by round-robin.
- `batch_low_risk` (room): Batched 2 low-risk items so reviewers see them together.
- `route_medium` (casey): Medium-risk item routed to casey (medium 4 for that reviewer) by round-robin.
- `route_high_risk` (avery): High-risk item routed to avery, the reviewer with the oldest last decision.
- `batch_low_risk` (room): Batched 2 low-risk items so reviewers see them together.
- `route_canary` (casey): Canary routed to casey (canary 4 for that reviewer). Ties go to the careful reviewer.
- `route_medium` (avery): Medium-risk item routed to avery (medium 5 for that reviewer) by round-robin.
- `batch_low_risk` (room): Batched 2 low-risk items so reviewers see them together.
- `route_medium` (blake): Medium-risk item routed to blake (medium 5 for that reviewer) by round-robin.
- `batch_low_risk` (room): Batched 2 low-risk items so reviewers see them together.
- `route_medium` (casey): Medium-risk item routed to casey (medium 5 for that reviewer) by round-robin.

## Recommended next change

Require blake to explain the diff in one sentence before every approval until the flatness rule clears: median at least 8 seconds, and, once they have 5 or more decisions, either a coefficient of variation of at least 0.25 or a median of at least 15 seconds.

## Limits

Limits: small sample; demonstrates the method, not statistical significance. Three simulated or live reviewers and one repository are enough to show the measurement, and they are not enough to estimate a population rate.
