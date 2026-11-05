# Sample service constraints

The worker may edit this repository only inside these rules:

- Ship patch version bumps unless a human names a minor or major bump.
- Keep `environment` set to `staging` in this tree. Production hosts are out of scope.
- Keep `max_connections` at or below 100, and `max_retries` at or below 5.
- Do not delete tests.
- Do not skip verification.
- Work on branch `main`.
- Notify `#ops-private` only. Never `#public-announce`.
- Take a backup before any migration that drops or deletes rows.
- Dependencies must already be in this repository. Do not add a package that is not imported from the standard library.
