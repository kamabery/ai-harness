# ai-harness

A build harness whose **state is queryable** and whose **checks prove themselves**.

It replaces `ai-dlc`, and it was designed from measurements of that harness's three real runs
rather than from a theory about what went wrong. Two of those runs shipped working software and
caught 20 documented bugs; one was abandoned at phase 3 of 12. The redesign keeps what those runs
demonstrably earned and removes what they demonstrably did not use.

## What the evidence said

The premise under investigation was that builds were expensive because there was too much context.
That is **half right, and wrong about the cause**:

- The run that **failed** carried the **smallest** payload — ~35k tokens of run documents against
  the most successful run's ~83k. Across three data points, context size is *anti-correlated* with
  failure.
- The dominant cost is **tool output**, not prompt text. One run's `logs/` alone is 1.4 MB ≈ 333k
  tokens — 4× that run's entire document payload. Auto-loaded doctrine was ~26k tokens and was
  implicated in **0 of 9** recorded failures.
- So doctrine here is trimmed for **legibility, not cost**: cutting all of it would have recovered
  under 10% of a run.

What actually broke was subtler: **markers that exist before the thing they stand for.**
Ten capture files existed as 818-byte stubs reading `(nothing captured yet)` and the check that
was supposed to catch them tested presence, not content. Six of ten architectural rules sat behind
`"unchecked_because": "TODO – no check written yet"` and were counted as coverage. A cursor section
whose own rule said "exactly one active phase" reached 420 of 620 lines, with nothing enforcing it.

Nine recorded defects were of that shape, and **not one was a bug in the application.** All were
defects in the instruments.

## What follows from that

**State is typed and queried, never read whole.** `cursor` is one object, so two active phases are
unrepresentable rather than forbidden. No string may exceed 1,000 characters, so a pasted stream
cannot enter state at all — the predecessor's fix evicted captures from its ledger and the growth
simply relocated to the next unbounded section. A positional ceiling moves the problem; a typed
one does not.

**A phase is handed a slice.** `harness brief <n>` emits that phase, its cursor, only the facts it
declares it needs, and any failure still open. Measured on a run with 36 facts: 1,072 bytes, three
facts. The ceiling is 4 KB and a check enforces it.

**A check that has never been seen to reject cannot report green.** Every check ships a `selftest`
that constructs the input it must refuse. This is not a substitute for unit tests — the predecessor
had 2,041 lines of tests across four fixture workspaces and the nine defects shipped anyway,
because a unit test proves a function rejects a fixture, not that the check *as wired into this
workspace* rejects this workspace's failing case.

**Cross-run memory is one file.** It was two, and one of them — `docs/LESSONS-LEDGER.md` — was
required to be read first and written at every archive, and never existed in either workspace. The
archive also carried only lessons marked `CARRIED`, excluding the ones applied inside the run; the
next run in the same repository re-derived four of those three days later. Here every row is
carried regardless, because a lesson applied inside one run does not mean the next run knows it.

## The run shape

One shape. Four fixed phases, and the slices between them.

| Phase | What it is for |
|---|---|
| `0 preflight` | facts resolved; every gate run against the case it must reject |
| `1 baseline` | instruments up, red channel proved, executed and skipped counts recorded |
| `2..N slice-k` | **the only phases that produce product code** |
| `N+1 reconcile` | cleanup and archive, merged |

The predecessor ran 10 to 13 phases, of which 7 produced no product code. Four were cut: README,
self-improvement, the separate archive, and the standalone adversarial review — that last one on
its own record. Two blind reviewers ruled `9 PROVEN / 0 NOT PROVEN` over a tree where a named spec
deliverable had never been built; a `git status --porcelain` read against the spec found it a day
later. The review survives as one subagent call inside `reconcile`, with its withheld-evidence
control, which is the half that was 2-for-2.

## Using it

```
harness -C <workspace> import <old-workspace>   # read what a previous harness paid for
harness -C <workspace> start <run> --slices 3
harness -C <workspace> inherit                  # before deriving anything
harness -C <workspace> brief 0                  # what phase 0 is handed
harness -C <workspace> check                    # exit code is the defect count
harness -C <workspace> score                    # what is enforced here, and what is not measured
```

Nothing defaults to the current directory. The workspace is always an argument: a shell's working
directory is not evidence of which tree a request meant, and scaffolding into the wrong one is
invisible from inside the documents — they read as authoritative against a repository nobody meant.

## What this does not fix

The ~200k tokens per phase of browser and build output. The ceilings here recover under 10% of a
phase. The remaining lever is fewer assertions per slice, and that trade surrenders the instruments
that caught most of the 20 bugs — so it is left as a decision rather than made quietly.

`docs/STANDARDS.md` — what evidence must look like. `docs/CONTROLS.md` — what is checked, and what
is deliberately not. Neither is auto-loaded.
