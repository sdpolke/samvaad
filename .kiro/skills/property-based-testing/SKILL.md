---
name: property-based-testing
description: Use when testing pure, deterministic decision logic — reducers, classifiers, schedule/gate evaluators, parsers, formatters, or any function with an invariant that should hold across all inputs. Guides writing Hypothesis property tests that assert invariants over generated inputs rather than hand-picked examples.
---

# Property-Based Testing (Hypothesis)

Example tests check the cases you thought of. Property tests check invariants across inputs the
machine generates — surfacing edge cases you didn't. Use them for pure logic; keep side-effecting
behavior in example/integration tests.

## When to use

- Good fits: state reducers, classification/mapping functions, schedule/business-hours evaluators,
  gate/authorization decisions, formatters and their inverses, validation, ordering/dedup.
- Poor fits: real network/telephony/LLM calls, DB side effects, end-to-end conversation flows —
  test those with mocks and worked examples instead.

## How to find a property

Ask what must ALWAYS be true, regardless of input. Common shapes:

- **Round-trip:** `decode(encode(x)) == x` (e.g. format a phone number, then re-extract the digits).
- **Invariant:** an output constraint holds for all inputs (e.g. a populated field is never re-asked;
  a terminal turn emits only the prescribed line).
- **Oracle:** result matches a simpler reference implementation.
- **Idempotence / commutativity:** `f(f(x)) == f(x)`; order does not change the result.
- **Metamorphic:** a known input change produces a known output change.

## Writing the test

```python
from hypothesis import given, strategies as st

# Feature: <feature-name>, Property <n>: <the invariant in words>
@given(dob=st.dates(), record=st.dates())
def test_dob_match_determines_verification(dob, record):
    assert verify(dob, record).success is (dob == record)
```

- **One property per test**; name and comment-tag it with the design property it validates.
- Minimum **100 iterations** (Hypothesis default is fine; raise via `@settings(max_examples=...)`).
- Shape generators to the real domain (valid enums, ranges); cover edge cases explicitly with
  `@example(...)` (empty, full, boundaries, DST/week edges, every enum value).
- Let Hypothesis **shrink** failures to a minimal counterexample; turn each counterexample into a
  permanent `@example(...)` regression.

## Rules

- Test the property, not the implementation — don't reimplement the function inside the assertion.
- Keep the function under test pure; if it isn't, extract the pure core so it can be generated over.
- Deterministic only: no wall-clock/network/random side effects inside the property.

## In this repo

- Hypothesis is the standard PBT library. Pure switchboard/workflow decision logic should be
  extracted into side-effect-free functions and covered this way (see `.kiro/steering/testing.md`).
