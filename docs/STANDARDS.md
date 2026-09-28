# Standards — what evidence has to look like

Rules only. Where a rule exists because something went wrong, the failure is named in one clause,
not argued for in a paragraph. Roughly half the words in this document's predecessor argued for
its rules; that half is gone.

Not auto-loaded. Read the section you need.

## What a capture is

- One file per phase, at `runs/<name>/captures/phase-<n>.md`. Committed.
- Two blocks close a phase: a `--- RED` block and a `--- PASS` block, **of the same command**.
- Each block holds the exact command, the raw stream unedited, and the exit marker.
- The two blocks' first lines must differ. One run pasted twice is not a pair.
- Ceiling 200 KB. The full stream goes to `.harness/raw/`, which is gitignored and **not citable**.
- A capture file that exists but says nothing does not close a phase: `state` compares its sha256
  against what the phase recorded. Ten template stubs reading `(nothing captured yet)` passed the
  predecessor's presence check.

## What a phase test is

- One command, kept in the tree, whose exit code is the verdict.
- Run it against the case it must reject **before** trusting it. A check whose green is
  unreachable and a check whose green is unfalsifiable are the same bug from opposite sides.
- Read the **count**, never the exit code. `dotnet test` with no project, `pytest` collecting 0
  items, and a placeholder `npm test` all exit 0. So does a real suite.
- Record executed **and skipped**. A skip count that rose between phases is a silenced check.
- Never relax a count comparison to `>=`. That repair makes the red go away and deletes the
  control, and it looks like tidying.
- No check may match text it or its own template authored. `Contains("IN_PROGRESS")` matched the
  legend line defining the word, so it was true in every run that ever existed.
- Pair every absence assertion with a presence one. Zero is trivially true of nothing: a page that
  rendered nothing scored `overflow=False consoleErrors=0 axe=0`.

## What a retry may wait on

- A post-change invariant: a resolved token, a settled class, a value that is now readable.
- Never a bare timeout, and never a re-navigation to ride out a transient.
- **A retry around a render is the finding, not the fix.** One run filed a defect as "a ~1-in-3
  flake, retry once or shard"; the next run root-caused it as a wait on the wrong element. It was
  never a flake.
- A marker a test waits on must render only when the thing it stands for is true.

## What a fact must contain

- An `A#` id, a statement under 300 characters, and evidence as `path:line` or a capture citation.
- `cost: cheap` — re-checkable in about a second, no build. Always re-run; never inherited.
- `cost: expensive` — needs a build, a browser, or enumerates more than a handful of things.
  Inheritable while its checksum matches, and it must carry a `recheck_cmd`.
- `source: inherited` means a previous run proved it. **It is open until this run has watched the
  re-check pass.** A citation is not a signal.
- A detected value is a lead. A package in a manifest is a declaration, not an installation.

## What a failure row must contain

- The **verbatim first line** of the error. Not a summary.
- A count. When the same first line reaches **2**, stop: surface the captures and ask. Two
  identical failures means an upstream fact is wrong, and the next speculative fix is the third.
- `changed_what` — the cause that changed. "Skipped the test", "added a retry", "excluded the
  path" and "widened the timeout" are not causes that changed.
- `changed_in_phase` — which later phase the lesson altered, or nothing if none could use it.

## What memory must contain

- One file, `.harness/memory.json`, rendered read-only to `docs/MEMORY.md`.
- Every failure carries a **cheaper observable**: the thing that would have caught it sooner. A
  lesson that names none is a story.
- Every row is carried regardless of what the run did with it. A lesson applied inside one run
  does not mean the next run knows it — the predecessor's archive excluded applied lessons by
  rule, and the next run in the same repository re-derived four of them.

## Citations

- Every cited path is `git check-ignore -v`'d as the citation is written. `git status` is silent
  about an ignored file, which is the failure mode. This earned itself three times: `*.e2e` hid a
  whole test project, and `[Ll]ogs/` plus `*.log` each independently hid three cited logs —
  negating only the first left them ignored, so a fix that looked complete was not.
- Evidence a phase closed on is committed. What is not committed is evidence only this machine has.
- A committed evidence file whose sha changes without a phase row is a rewrite: one run's suite
  silently overwrote 30 of 38 committed PNGs belonging to a finished run, exit `0`.
