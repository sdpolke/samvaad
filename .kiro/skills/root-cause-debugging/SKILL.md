---
name: root-cause-debugging
description: Use when a test is failing, a bug is reported, or behavior is unexpected — especially after a fix attempt has already failed once. Guides a systematic reproduce → isolate → diagnose → fix → verify workflow that finds the real cause instead of patching symptoms.
---

# Root-Cause Debugging

Random tweaks waste time and mask defects. Work the problem systematically and fix the cause, not
the symptom.

## Workflow

1. **Reproduce reliably.** Find the smallest input/command that triggers the failure. If it is
   intermittent, pin down the nondeterminism (timing, ordering, shared state, randomness) first.
   Capture a failing test that reproduces it — this becomes the regression guard.
2. **Read the actual error.** Read the full traceback/log, top frame to root cause. Note the exact
   message, file, and line. Don't skim.
3. **Form one hypothesis** about the cause and state it explicitly ("I think X because Y").
4. **Isolate.** Narrow the surface: bisect the change, comment out layers, add targeted logging,
   or drop into a debugger. Confirm or reject the hypothesis with evidence before changing code.
5. **Fix the cause.** Make the smallest change that addresses the root cause. Avoid defensive
   band-aids that hide the failure.
6. **Verify.** Re-run the reproducing test and the surrounding suite. Confirm the fix works and
   nothing regressed. Remove temporary logging/scaffolding.

## When a fix attempt fails

- **Stop after two failed attempts on the same approach.** Do not keep tweaking.
- Re-read the error from scratch; question an assumption you've been treating as fact.
- State what you've ruled out and try a fundamentally different track.
- If the new track deviates from the original intent or drops a requirement, say so and confirm.

## Investigation discipline

- Verify claims against reality: read the file, run the command, check the state — don't assume.
- Distinguish what you've confirmed from what you suspect. Say which is which.
- Treat logs/outputs as evidence; reproduce before believing a theory.

## In this repo

- Use loguru output and the test log config; run the specific failing test with the test env
  sourced. Prefer extracting a pure function and property-testing it if a bug hides in decision
  logic (see the `property-based-testing` skill).
