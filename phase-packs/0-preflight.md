# Phase 0 — preflight

**Test:** `harness check --checks state,memory,ignore` → 0 defects, and no fact left open.

## Do

1. `harness inherit` — **first, before deriving anything.** A fact re-derived from memory has been
   paid for twice and the second payment is invisible.
2. `harness brief 0` — what this phase is handed.
3. For each inherited fact, run its `recheck_cmd` and set `reverified` only when you watched it
   pass. An inherited fact is a lead until then.
4. For every fact still open: run the command that answers it, paste the output into
   `captures/phase-0.md`, and record the fact with that citation. Where no command can answer it,
   **ask**. Do not pick the plausible value.
5. Run each of this run's own gates once against the case it must reject, and capture that run.

## Red

Free, and at scaffold time: every fact is open, so the check is red before anything is asked.
Capture that first run. It is the before-picture and it costs nothing.

## PASS signal

`harness check --checks state,memory,ignore` exits 0, and `harness status` shows `0 open`.

## FAIL modes

- **A fact was filled from the tree rather than from a command.** The better documented the tree,
  the more confidently it answers; a well-kept repository is the dangerous case, not the safe one.
- **A gate's PASS signal is unreachable.** Run it once and confirm the number it prints can be
  driven to the value the plan demands. Two recorded failures were this: a case-insensitive regex
  matching the ledger's own description of the gate, and a count taken by eye off the source when
  the runner counted `[Theory]` rows.
- **An inherited fact was marked reverified without the command running.** That is a citation
  standing in for a signal, which is the thing this phase exists to prevent.
- **A conflict was answered with a new fact row.** A conflict is not an open question. Nothing you
  run settles it; raise it now, where it costs a sentence.
