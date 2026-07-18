---
inclusion: fileMatch
fileMatchPattern: 'api/tests/**'
---

# Testing Conventions

## Harness

- **pytest** with `asyncio_mode = auto` (async tests need no decorator). Config in `api/pytest.ini`.
- Tests live under `api/tests/`, mirroring the package layout. Files: `test_*.py` / `*_test.py`.
- **Always source the test env** so tests hit the test DB, never dev/prod:
  ```bash
  source venv/bin/activate && set -a && source api/.env.test && set +a && python -m pytest api/tests/...
  ```

## Database isolation

- `conftest.py` provisions a separate `*_test` database, runs Alembic migrations once per session,
  and wraps **each test in a transaction rolled back at teardown** (savepoint pattern). Tests may
  call `session.commit()` — it commits only to the savepoint. Do not defeat this isolation.
- Use the provided fixtures: `db_session` (DBClient on the test session), `async_session`, and
  `test_client_factory` (auth-overridden `httpx` client per user). Prefer these over ad-hoc engines.

## What to test

- **New feature or bug fix ⇒ tests.** Cover the happy path, boundaries, and failure/error paths.
- Keep tenant isolation under test: assert that org-scoped reads/writes reject cross-org access.
- For routes, test through `test_client_factory`; for services, test the service directly.

## Property-based testing (Hypothesis)

- Use **Hypothesis** for pure decision logic (reducers, classifiers, schedule/gate evaluators,
  formatters). Minimum **100 iterations** per property; one property-based test per property.
- Tag each property test with a comment referencing the design property, e.g.
  `# Feature: <feature>, Property <n>: <text>`.
- Design generators to hit edge cases explicitly (empty/full inputs, boundaries, DST/week edges,
  every enum value). Let Hypothesis shrink counterexamples; add regressions via `@example(...)`.
- Reserve example/integration tests for side-effecting behavior PBT is unsuited for (real
  telephony wiring, external contracts with mocks, end-to-end scenario walkthroughs).

## Hygiene

- Do not mock what you can run cheaply in-process; do mock external network/telephony/LLM calls.
- Clean up any temp files a test creates. Keep tests deterministic (seed randomness).
- Run the relevant tests before presenting a change as done; fix failures rather than skipping.
