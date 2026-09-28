<!-- BEGIN ai-harness -->
## How work is done in this repo

Work happens in runs. There is one run shape: **0 preflight, 1 baseline, 2..N slices, N+1
reconcile**. Only the slices produce product code; the other three make them falsifiable.

**Never read the state file whole. Ask for the slice:**

```
harness brief <n>
```

That is phase `n`, the one-line cursor, only the facts that phase names, and any failure still
open. Everything else is deliberately not in it.

@docs/ARCHITECTURE.md

### The rules that earned their place

Each of these was written because something shipped without it. Nine recorded defects in the
previous harness were of exactly these shapes, and **none of them was a bug in the application** —
all were defects in the instruments.

- **Run every new check against the case it must reject, and capture that run.** A check whose
  green is unreachable and a check whose green is unfalsifiable are the same bug seen from
  opposite sides.
- **Read the count, not the exit code.** A test command that exits 0 having run nothing is the
  most dangerous green available. Record executed **and skipped**, and compare both to phase 1.
  Never relax a comparison to `>=`.
- **`git check-ignore -v` every new path as you create it.** `git status` is silent about an
  ignored file, which is the failure mode. This caught a whole hidden test project and three
  hidden evidence logs.
- **Pair every absence assertion with a presence one.** Zero is trivially true of nothing.
- **Log the verbatim first line of every failure, and stop at two.** Two identical failures means
  an upstream fact is wrong; the next speculative fix would be the third guess.
- **A retry around a render is the finding, not the fix.** Wait on a post-change invariant, never
  a bare timeout. One run filed a defect as a flake; the next proved it was never a flake.
- **An open fact is a STOP, not a decision point.** Ask. Do not pick the plausible value — and
  note that the better documented the tree, the more confidently it answers.
- **An inherited fact is a lead until this run has watched its re-check pass.** A citation is not
  a signal.
- **Raw output goes to `.harness/raw/`**, which is gitignored and may never be cited. What a phase
  closed on is committed.
- Commands here are written for {{SHELL}}.

### The commands

| Command | What it does |
|---|---|
| `harness brief <n>` | what phase `n` is handed — the slice, never the document |
| `harness status` | where the run is, in one screen |
| `harness check` | the nine checks; the exit code is the defect count |
| `harness inherit` | adopt what a previous run proved; re-run what is cheap |
| `harness archive` | fold this run into the workspace's memory |
| `harness score` | what is actually enforced here, and what is not measured |

`docs/STANDARDS.md` says what evidence must look like. `docs/CONTROLS.md` says what is checked and
what is deliberately not. Read the one that fits the task; neither is auto-loaded, and both are
rules rather than arguments.
<!-- END ai-harness -->
