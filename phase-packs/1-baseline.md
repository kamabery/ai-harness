# Phase 1 — baseline

The instruments, before any product code. Nothing after this phase can be compared to anything
unless this phase wrote the numbers down.

**Test:** the build and test commands from phase 0's facts, plus the red-channel probe.

## Do

1. Run the real build command. Capture it.
2. Run the real test command. Capture the **summary line** with its executed and skipped counts,
   and record both in `counts.baseline_executed` / `baseline_skipped`.
3. **Prove the test command can report a failure at all.** Break one assertion deliberately, watch
   the runner name it, revert in full, and capture all three steps. A suite that has never been
   seen to fail is not a baseline.
4. Confirm the tree is clean afterwards: `git status --porcelain`.

## Red

The red-channel probe is the red: the runner reporting one more failure than the baseline. The
revert is what makes it green again.

## PASS signal

A non-zero executed count, `0` errors on the build, the probe's extra failure observed and
reverted, and a clean tree.

## FAIL modes

- **Zero tests executed.** That is a FAIL, not a baseline. At the exit code it is
  indistinguishable from a passing suite, and every later phase leaning on it inherits the
  illusion. If the tree has no runnable tests, stop and settle what runnable check replaces them.
- **The red channel could not be proved.** Then no later count means anything.
- **A count was read off a manifest, a CI job name or a README.** Those are three claims about a
  command and all three drift. Take the number from the runner's own summary.
- **A new file was created without `git check-ignore -v`.** Do it as the path is created, not at
  the archive, when it is far too late.
