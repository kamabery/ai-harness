# Phase 2..N — a slice

The only phases that produce product code. Everything else exists to make these falsifiable.

**Test:** one command, kept in the tree, red before green, with counts compared to phase 1.

## Do

1. `harness brief <n>` — this phase, its cursor, and only the facts it names in `needs`.
2. **Write the check first** and run it against the untouched tree. Read the failures: each must
   name the thing this phase is about, not a missing fixture or a connection error.
3. Build the slice.
4. Run the check. Then run every earlier phase's check, unmodified.
5. Record executed and skipped counts, and compare them to phase 1's numbers.

## If this slice changes anything a person sees

Set `needs_human` on the phase, and close it on a person having looked - not on the render sweep
going green. The sweep asserts six absences (overflow, colour==background, unpainted svg, unnamed
control, console errors, axe violations); a screen can satisfy all six and still be cramped,
confusing, or missing what the user came for. Put `SPEC.md`'s *What it must feel like to use* in
front of them, and record what they saw:

```
APPROVED-BY: <name> <date>
SAW: <which screens, which viewports, which themes>
```

## Red

Free if the check is written first. Where it is not free, manufacture it deliberately and put it
back — and capture all of it.

## PASS signal

The same command that went red now exits 0; the executed count is at or above phase 1's baseline
plus this phase's new tests; the skipped count has not risen.

## FAIL modes

- **A count fell, or a skip count rose.** A check was removed, not a bug fixed. A silenced check
  produces a green byte-for-byte identical to a real fix.
- **The red and the green are not the same command.** Then nothing was proved.
- **An absence assertion with no presence assertion beside it.** Zero is trivially true of nothing.
- **A red was made green by widening a timeout, excluding a path, or adding a retry.** None of
  those is a cause that changed. A retry around a render is the finding.
- **The same first-line error twice.** Stop. Surface the captures and ask; an upstream fact is
  wrong and the next fix would be the third guess.
- **A generator's samples left in the tree.** Whatever `new`/`init`/`scaffold` emitted that the
  spec did not ask for is this run's own orphan to remove.
