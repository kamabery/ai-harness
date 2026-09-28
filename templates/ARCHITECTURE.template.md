# ARCHITECTURE — {{ONE_LINE_TITLE}}

<!--
  The workspace's guardrails. Written once, inherited frozen by every run after.

  Auto-loaded into every session, so it has a 150-line ceiling. What does not fit here is not a
  guardrail; it is a decision for a run to make and record.

  ONE HARD RULE: A GUARDRAIL IS A DURABLE CONSTRAINT, NOT AN IMPLEMENTATION DECISION.
  The test for a borderline line: would this still be true three runs from now? If the honest
  answer is "only for this one", it belongs in SPEC.md.

  Name boundaries, layering, data ownership, the design system. Do not name phases or this run's
  commands. Delete a heading you have nothing to say under.
-->

## The shape of the system

{{THE_SHAPE}}

<!-- The pieces and the boundaries between them. What talks to what, and what may not. A paragraph
     is usually enough. "One console application, no services" is a real and useful answer, and it
     stops a later run inventing a topology nobody asked for. -->

## What it is built on

{{THE_STACK}}

<!-- Keep this short: it is a transcription, not a decision. Language and runtime version,
     framework, data store, test runner, deployment target. Say why only where the reason
     constrains something later. -->

## The rules a run may not break

{{THE_RULES}}

<!-- One line per rule. EVERY RULE GOES INTO docs/guards.json WITH THE CHECK THAT WATCHES FOR IT,
     or with the real reason there is none.

     A reason that defers the work is not a reason. The workspace that prompted this harness
     declared ten rules and wrote four checks; the other six said "TODO - no check written yet",
     and every run after inherited them as though somebody enforced them. `harness score` reports
     a deferred reason as a defect and refuses to count it as coverage.

     If a rule cannot have a check, say what does enforce it — a review step, an integration test
     that lives elsewhere, a person. "Nothing" is an answer too, and a truthful one. -->

## Where the design system is

{{THE_DESIGN_SYSTEM}}

<!-- Only if a person ever sees this system. The token file, the approved components, and the route
     that renders them.

     A raw colour or a class nothing defines passes every test and breaks the screen. A contrast
     check that resolves no colour pair has measured nothing and must fail rather than pass — that
     is the shape of every counting check here: assert the floor, not only the ceiling. -->

## What we are not sure about yet

{{THE_OPEN_QUESTIONS}}

<!-- Open questions the guardrails themselves raise. Each becomes a fact at the next run's
     phase 0, answered by a command or by asking. This is the only section allowed to be unsure. -->
