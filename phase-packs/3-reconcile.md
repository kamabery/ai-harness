# Phase N+1 — reconcile

Cleanup and archive, in one phase, deliberately. This is the phase with the best record in the
evidence: it found a named spec deliverable that had never been built, after nine green phases and
two blind reviewers ruling `9 PROVEN / 0 NOT PROVEN` over the same tree.

**Test:** `harness check` → 0 defects, then `git status --porcelain` read against the spec.

## Do

1. `git status --porcelain` — the whole list, read line by line. Every entry is a kept deliverable,
   an intended edit, or scratch to remove. Nothing is "probably fine".
2. **Read the diff against `SPEC.md`.** For each thing the spec says this run builds, name the
   command that proves it exists. `harness check --checks spec-coverage` does the mechanical half;
   the reading is yours.
3. Run the **withheld-evidence control**: hand a fresh subagent the criteria and the captures with
   one phase's evidence removed, and confirm it rules that criterion unproven. A reviewer that
   cannot rule against the run is not an instrument. Then run it over the full set.
4. `harness archive` — writes `.harness/memory.json` and renders `docs/MEMORY.md`.
5. Confirm nothing metered is still running: containers, processes, trial resources.

## Red

The `git status` listing is the red: the cleanup work list, before any of it is done.

## PASS signal

`harness check` exits 0; every spec deliverable maps to a command; the control ruled against the
withheld criterion and the full run ruled for it; memory gained a row per expensive fact and per
failure.

## FAIL modes

- **A spec deliverable has no command behind it.** It was not built, or it was built and nothing
  watches it. Both are this phase's work — reopen the slice.
- **Memory gained nothing while the run recorded failures.** The next run will re-derive them.
  This is the exact defect that cost the predecessor four lessons in one run.
- **A failure row with no cheaper observable.** A lesson that names no cheaper way to have caught
  it is a story.
- **Live state left in the cursor that will not survive the week.** A PID and a container name are
  instructions a resuming session cannot follow. Say how to recreate it, not what it was called.
- **The run self-closed.** It does not. A person closes it.
