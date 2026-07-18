---
name: test-driven-development
description: Use when implementing a new feature, fixing a bug, or changing behavior in code that can be tested. Guides a red-green-refactor workflow — write a failing test first, make it pass with the simplest change, then refactor — so changes are verified and regressions are caught early.
---

# Test-Driven Development

Write the test before the implementation. This forces a clear spec, keeps scope honest, and
leaves a regression net behind.

## Loop

1. **Red** — write the smallest test that expresses the next required behavior. Run it; confirm it
   fails for the right reason (asserts behavior, not a typo/import error).
2. **Green** — write the minimum code to make it pass. Do not add unrequested features.
3. **Refactor** — clean up names, duplication, and structure with the test green. Re-run.
4. Repeat for the next behavior.

## How to choose the next test

- Start with the simplest meaningful case, then add boundaries and failure paths.
- One behavior per test. A test name should read as a sentence about the behavior.
- Prefer testing observable behavior and public interfaces over private internals.

## Rules

- **Never write implementation without a failing test first** for new behavior or a bug fix.
- **Reproduce bugs with a failing test before fixing** — the test proves the fix and prevents
  regression.
- Keep tests fast and deterministic; seed randomness; isolate side effects (network, DB, time).
- If a test is hard to write, treat it as a design smell — the unit probably needs to be smaller
  or have fewer dependencies. Extract pure functions.
- Run the full relevant suite before declaring done; fix failures rather than skipping/xfailing.

## In this repo

- Tests live in `api/tests/` (mirror the package). Source `api/.env.test` before pytest.
- Use the transactional fixtures (`db_session`, `test_client_factory`) — see `.kiro/steering/testing.md`.
- For pure decision logic, pair TDD with property-based tests (see the `property-based-testing` skill).
