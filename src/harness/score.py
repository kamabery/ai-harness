"""How this workspace grades itself, and what it refuses to grade.

Its predecessor's scorecard reported eight dimensions and scored 2 of 8 OK on a workspace whose
run had shipped. That was honest and it was misread, including by me at first: the two dimensions
that scored OK - red-then-green pairs, and tests that are not vacuous - are exactly the two a
machine can check about itself. The six that scored WEAK were architecture, UI and human review,
which CONTROLS.md was right to say "require someone to look".

Two changes follow, and they are the whole of this rewrite:

* **A dimension is computed or it is absent.** The predecessor counted a rule declared unchecked
  as a row it had measured, so six rules behind "TODO - no check written yet" read as coverage.
  Here an uncomputable dimension prints ABSENT and says what would make it computable. A score
  that includes unmeasured rows is worse than a missing score, because it looks like a number.
* **Every count prints its denominator.** "3 of 6 guards pass" is information; "3 guards pass" is
  the shape that let a nine-route sweep report zero problems over a blank page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import check as check_mod
from . import memory as memory_mod
from . import state as state_mod

OK = "OK"
WEAK = "WEAK"
ABSENT = "ABSENT"


@dataclass
class Dimension:
    name: str
    verdict: str
    summary: str
    notes: list = field(default_factory=list)


def _evidence(state: state_mod.State) -> Dimension:
    passed = [p for p in state.phases if p.status == "passed"]
    if not passed:
        return Dimension("evidence", ABSENT,
                         "no phase has closed, so no pair can be shown",
                         ["close a phase: a red capture and a pass capture of the same command"])
    paired = [p for p in passed if p.red_seen and p.capture_sha]
    verdict = OK if len(paired) == len(passed) else WEAK
    return Dimension("evidence", verdict,
                     str(len(paired)) + " of " + str(len(passed))
                     + " passed phase(s) show a red-then-green pair",
                     [str(p.id) + " " + p.name + ": no pair" for p in passed if p not in paired])


def _counts(state: state_mod.State) -> Dimension:
    passed = [p for p in state.phases if p.status == "passed"]
    if not passed:
        return Dimension("counts", ABSENT, "no phase has closed, so no count exists to compare",
                         ["the count is the signal: a suite that ran nothing exits 0"])
    counted = [p for p in passed if p.counts.executed]
    verdict = OK if len(counted) == len(passed) else WEAK
    return Dimension("counts", verdict,
                     str(len(counted)) + " of " + str(len(passed))
                     + " passed phase(s) recorded a non-zero executed count",
                     [str(p.id) + " " + p.name + ": no executed count"
                      for p in passed if p not in counted])


def _facts(state: state_mod.State) -> Dimension:
    if not state.facts:
        return Dimension("facts-confirmed", ABSENT, "this run has settled nothing yet",
                         ["run `harness inherit`, then answer the open facts"])
    still_open = state.open_facts()
    confirmed = len(state.facts) - len(still_open)
    verdict = OK if not still_open else WEAK
    return Dimension("facts-confirmed", verdict,
                     str(confirmed) + " of " + str(len(state.facts))
                     + " fact(s) carry evidence this run watched",
                     [f.id + ": " + ("inherited, not re-verified" if f.source == "inherited"
                                     else "open") for f in still_open[:6]])


def _architecture(target: Path) -> Dimension:
    """Computed only where the rules are declared. Never partially, and never from a TODO."""
    from . import guards as guards_mod
    try:
        rules, _ = guards_mod.load_declaration(target)
    except guards_mod.GuardsError as exc:
        return Dimension("architecture-enforced", ABSENT, str(exc).replace("refused: ", ""),
                         ["declare the rules in " + "/".join(guards_mod.GUARDS_FILE)])
    if not rules:
        return Dimension("architecture-enforced", ABSENT, "no rules are declared",
                         ["a workspace whose guardrails forbid nothing has not been graded"])
    checked = [r for r in rules if r.check]
    deferred = [r for r in rules
                if not r.check and guards_mod.is_placeholder(r.unchecked_because)]
    verdict = OK if len(checked) == len(rules) else WEAK
    notes = ["unchecked, and the reason defers the work: " + r.rule[:70] for r in deferred[:6]]
    if deferred:
        notes.append(str(len(deferred)) + " rule(s) are not counted as coverage - a rule behind a "
                     "TODO is unenforced, and every later run inherits it as though it was not")
    return Dimension("architecture-enforced", verdict,
                     str(len(checked)) + " of " + str(len(rules)) + " rule(s) have a check",
                     notes)


def _memory(target: Path, state: state_mod.State) -> Dimension:
    mem = memory_mod.load(target)
    if not mem.rows:
        return Dimension("memory", ABSENT, "nothing recorded; this is the first run here",
                         ["`harness archive` writes it at reconcile"])
    used = [f for f in state.facts if f.source == "inherited"]
    verdict = OK if used else WEAK
    return Dimension("memory", verdict,
                     str(len(mem.rows)) + " row(s) recorded, " + str(len(used))
                     + " inherited by this run",
                     [] if used else ["this run inherited nothing - run `harness inherit`"])


def _human_saw_it(state: state_mod.State) -> Dimension:
    """Did a person look at what a person will see?

    The predecessor scored ABSENT here on both completed runs - no phase in either workspace
    closed on someone having looked - and its screens shipped with defects and poor UX that
    manual testing later found. Every automated screen check it ran was an absence assertion,
    and a screen with nothing detectably wrong with it is not the same as a screen that is good.
    """
    visual = [p for p in state.phases if p.needs_human]
    if not visual:
        return Dimension("human-saw-it", ABSENT,
                         "no phase is marked as changing something a person sees",
                         ["if this run touches a screen, set needs_human on that phase - "
                          "otherwise nothing in this harness can notice bad UX"])
    signed = [p for p in visual if p.human_saw]
    verdict = OK if len(signed) == len(visual) else WEAK
    return Dimension("human-saw-it", verdict,
                     str(len(signed)) + " of " + str(len(visual))
                     + " screen-changing phase(s) carry a dated, attributed sign-off",
                     [str(p.id) + " " + p.name + ": nobody has said what they looked at"
                      for p in visual if not p.human_saw])


def _selftests() -> Dimension:
    result = check_mod.check_selftest(Path("."), Path("."))
    proven = result.examined - len(result.defects)
    verdict = OK if not result.defects else WEAK
    return Dimension("checks-proven", verdict,
                     str(proven) + " of " + str(result.examined)
                     + " check(s) have been seen to reject their own bad input",
                     list(result.defects))


NOT_MEASURED = (
    "whether the product is any good, or whether anyone would want it",
    "whether a phase test asserts what it claims - only whether it can go red",
    "whether a deliverable traces to SPEC.md; no parser tells invented scope from requested",
    "whether the architecture is the right architecture, only whether a rule has a check",
    "whether a capture was pasted or typed",
    "whether a human sign-off reflects a human having actually looked",
    "whether a screen is GOOD - only that six things are absent from it",
)


def scorecard(target: Path) -> tuple:
    """Every dimension, and how many read OK. Returns (report, count that did not)."""
    try:
        state = state_mod.load(target)
    except FileNotFoundError:
        state = state_mod.State(run="(none)")

    dimensions = [_evidence(state), _counts(state), _facts(state),
                  _architecture(target), _human_saw_it(state), _memory(target, state),
                  _selftests()]
    width = max(len(d.name) for d in dimensions)
    lines = ["harness scorecard - " + str(target), ""]
    for dimension in dimensions:
        lines.append("  " + dimension.name.ljust(width) + "  " + dimension.verdict.ljust(6)
                     + "  " + dimension.summary)
        for note in dimension.notes:
            lines.append("  " + " " * width + "          " + note)
    good = [d for d in dimensions if d.verdict == OK]
    lines.append("")
    lines.append("  " + str(len(good)) + " of " + str(len(dimensions)) + " dimension(s) read OK")
    lines.append("")
    lines.append("  Not measured here, and not therefore fine:")
    for item in NOT_MEASURED:
        lines.append("    - " + item)
    return "\n".join(lines), len(dimensions) - len(good)
