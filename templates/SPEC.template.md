# SPEC — {{RUN_NAME}}

<!--
  What this run is for, in the requester's own words. Per-run and disposable; ARCHITECTURE.md is
  the durable half.

  NOTHING IN A RUN EDITS THIS FILE. Not to tidy the grammar, not to sharpen a criterion, not to
  resolve an ambiguity. A paraphrase drifts, and it drifts silently because it reads better. Where
  the spec leaves something unobservable, ask the requester or make it a phase-0 fact.

  `harness check --checks spec-coverage` reads this file and asks one mechanical question of every
  sentence that says something gets built: is there a command behind it? It cannot tell invented
  scope from requested scope, which is why the wording here has to be theirs.
-->

## What I want

{{WHAT_I_WANT}}

<!-- Their words. What it is for, and who uses it. -->

## Every screen it has

{{THE_SCREENS}}

<!-- Name each one, or write "none - this has no interface".

     A spec that names no screens hands the quantifier to the run, and a run picks the screens it
     built most recently. Every visual check downstream is quantified as "every screen the spec
     names". -->

## What "done" means

{{DONE_MEANS}}

<!-- One line per criterion, each naming something that prints, exits, or is visibly on screen.

     "Works correctly", "is reliable" and "handles errors gracefully" never print, so no phase can
     close on them. Where the requester said one of those, move it below rather than sharpening it
     yourself — the sharpened version reads better and is not what they meant.

     Where a criterion names a raw observable — an HTTP status, a row count, a value round-tripped
     — the phase must show that literal value in its capture. A runner's `Passed: 7` is not the
     signal for a behaviour the spec spells out; a reviewer handed only the captures cannot tell
     that apart from an unproven claim. -->

## What it must respect

{{CONSTRAINTS}}

<!-- Constraints true only for this run. Anything true three runs from now is a guardrail and
     belongs in ARCHITECTURE.md instead. -->

## What I am not sure about

{{NOT_SURE}}

<!-- Every open question, in their words. Each becomes a phase-0 fact, answered by a command or by
     asking. "I don't know" is a complete answer and a useful one. -->
