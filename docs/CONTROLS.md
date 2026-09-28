# Controls — what is checked, and what is deliberately not

Not auto-loaded. Read it when you want to know whether something is enforced or merely written.

## The rule above the rules

**A check that has never been seen to reject cannot report green.**

Every check ships a `selftest` that builds the input it must refuse and asserts it is refused.
`harness check` marks any check whose selftest did not run here as `UNPROVEN` and counts it as a
defect. This is not a substitute for unit tests: the predecessor had 2,041 lines of tests across
four fixture workspaces and nine instrument defects shipped anyway, because a unit test proves the
function rejects a fixture, not that the check as wired into this workspace rejects this
workspace's actual failing case.

## The nine checks

| Check | What it decides |
|---|---|
| `state` | the schema and every ceiling; a passed phase's capture hashes to what state recorded |
| `brief` | every phase's slice is still a slice (≤ 4 KB), and names the facts it needs |
| `baseline` | executed and skipped counts, number for number, never relaxed to `>=` |
| `red` | no phase closed on a green nobody watched go red, and the pair is two different runs |
| `evidence-visible` | every cited path survives a clone; committed evidence has not silently moved |
| `ignore` | the raw stream is gitignored, and nothing cites it |
| `memory` | what a previous run paid for was read, and this run's was written |
| `spec-coverage` | every deliverable the spec asserts maps to a command that runs |
| `selftest` | every check above has been seen to reject its own bad input |

The exit code is the defect count.

## The ceilings

All defined once, in `harness/state.py`, imported by both the writer and the checker. The
predecessor kept three copies of one pattern in step with a comment saying to keep them
identical; they diverged anyway.

| Ceiling | Value | Why this number |
|---|---|---|
| `state.json` | 64 KB | more than this is evidence, not state |
| any single string | 1,000 chars | the anti-paste rule; one ledger's capture section reached 195,816 |
| `cursor.next_action` | 200 chars | one action, not a retrospective |
| facts | 40 rows | both real runs settled 36 |
| fact statement | 300 chars | a fact, not a paragraph |
| a capture file | 200 KB | beyond this is a raw stream |
| a brief | 4 KB hard, 2 KB target | beyond this the slice has become the ledger again |

`cursor` is **one object**, so two active phases are unrepresentable rather than forbidden. The
predecessor forbade them in prose and its cursor section reached 420 of 620 lines holding every
phase's result. A positional ceiling would have relocated that growth a third time; the eviction
of captures out of the ledger had already relocated it once.

## The phase exit gate

All four, or the phase does not close:

1. **The build succeeds** — error count zero and exit code 0.
2. **The tests ran, and the runner said how many** — a non-zero executed count, not exit 0.
3. **The phase's own test went red before it went green**, and the two captures are the same
   command.
4. **No red signal is left standing** — every failing observable this phase saw is fixed with a
   green capture of the same command, ruled pre-existing against the baseline, or escalated with
   the cursor left where it is.

Clauses 1, 2 and 4 have no full automated detector; they are enforced by the session reading its
own captures, which is the weakest enforcement here and is recorded as such rather than left
implied. Clause 3 has one: `red`.

## What is deliberately not checked

- Whether the product is any good, or whether anyone would want it.
- Whether a phase test asserts what it claims — only whether it can go red.
- Whether a deliverable traces to the spec. No parser tells invented scope from requested scope;
  `spec-coverage` only asks whether a command exists behind each claim.
- Whether the architecture is the right architecture — only whether a rule has a check.
- Whether a capture was pasted or typed.
- Whether a human sign-off reflects a human having actually looked.

The two observables that notice most of the above are `git status --porcelain` read against the
spec, and a person. A cold reviewer is not one of them on this evidence: two blind reviewers ruled
`9 PROVEN / 0 NOT PROVEN` over a tree where a named spec deliverable had never been built, and the
cleanup read found it a day later. `reconcile` is where both happen.

## Amending a check

Tighten it in the phase that found the gap, and record the failure row that prompted it. A check
that was loosened to make a red go away is the failure it was meant to catch, wearing the shape of
a fix.
