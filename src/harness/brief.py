"""What one phase is handed - a slice, not the document.

This is the single idea worth taking from Shopify's harness, and it needed re-pointing to get
here. Their partitioning groups files so each agent gets 20-30% of a window; a build harness has
no files to partition, because the artifact does not exist yet. What does transfer is the shape
underneath it: state that is keyed and selectively retrieved rather than prose read from the top.

The predecessor read its whole ledger at every phase. Measured, that is 507,703 tokens of
re-reading across a twelve-phase run, and the file is heaviest exactly when the agent has least
budget left. Nothing here reads state whole. A phase pack says "run `harness brief N`", and this
emits:

  1. phase N, and phase N-1 for the baseline it is compared against
  2. the cursor - one line
  3. only the facts phase N's `needs` names
  4. failures still open, and any that reached the two-identical stop
  5. the baseline counts

Phase 0 additionally gets what the workspace already paid for, because that is the phase where
re-deriving a known fact is cheapest to avoid.

The ceiling is the point. A brief over 4 KB means the slice has stopped being a slice, and the
`brief` check fails rather than letting it grow back into a ledger.
"""

from __future__ import annotations

from pathlib import Path

from . import memory as memory_mod
from .state import State

#: What a phase should be handed. Over the hard ceiling the `brief` check fails.
TARGET_BYTES = 2 * 1024
MAX_BYTES = 4 * 1024


def compose(state: State, phase_number: int, *, mem: memory_mod.Memory | None = None) -> str:
    out = []
    phase = state.phase(phase_number)
    out.append("# brief - run " + state.run + ", phase " + str(phase_number))
    out.append("")

    if phase is None:
        out.append("There is no phase " + str(phase_number) + " in this run.")
        return "\n".join(out) + "\n"

    out.append("## This phase")
    out.append("")
    out.append("- **" + str(phase.id) + " " + phase.name + "** - " + phase.status)
    out.append("- Test: `" + phase.test + "`")
    if phase.capture_ref:
        out.append("- Captures: " + phase.capture_ref)
    out.append("- Red seen: " + ("yes" if phase.red_seen else "**not yet** - capture it first"))
    out.append("")

    out.append("## Cursor")
    out.append("")
    action = state.cursor.get("next_action") or "-"
    out.append("- Next action: " + action)
    if state.cursor.get("blocked_on"):
        out.append("- Blocked on: " + str(state.cursor["blocked_on"]))
    if state.cursor.get("live_state"):
        out.append("- Live state: " + str(state.cursor["live_state"]))
    out.append("")

    previous = state.phase(phase_number - 1)
    baseline = phase.counts.baseline_executed
    if baseline is None and previous is not None:
        baseline = previous.counts.executed
    out.append("## Counts")
    out.append("")
    out.append("- Baseline executed: " + str(baseline)
               + " / skipped: " + str(phase.counts.baseline_skipped))
    out.append("- This phase executed: " + str(phase.counts.executed)
               + " / skipped: " + str(phase.counts.skipped))
    out.append("- The count is the signal, not the exit code. A suite that ran nothing exits 0.")
    out.append("")

    needed = [state.fact(i) for i in phase.needs]
    needed = [f for f in needed if f is not None]
    out.append("## Facts this phase needs (" + str(len(needed)) + " of "
               + str(len(state.facts)) + ")")
    out.append("")
    if needed:
        for fact in needed:
            value = fact.statement if fact.evidence else "**OPEN - ask, do not guess**"
            out.append("- **" + fact.id + "** " + value)
            out.append("  - evidence: " + (fact.evidence or "none yet")
                       + " | " + fact.source + " | re-check: `" + str(fact.recheck_cmd) + "`")
    else:
        out.append("_This phase declares no `needs`. If that is wrong, the slice is wrong._")
    out.append("")

    open_failures = state.unresolved_failures()
    stopped = state.stopped()
    if open_failures:
        out.append("## Failures still open (" + str(len(open_failures)) + ")")
        out.append("")
        for failure in open_failures:
            mark = " **STOP - two identical failures, escalate**" if failure.count >= 2 else ""
            out.append("- phase " + str(failure.phase) + ", count " + str(failure.count)
                       + ": " + failure.verbatim_first_line[:200] + mark)
        out.append("")
    if stopped:
        out.append("**" + str(len(stopped)) + " failure(s) reached the two-identical stop. "
                   "Surface the captures; do not make another speculative fix.**")
        out.append("")

    if phase_number == 0:
        mem = mem if mem is not None else memory_mod.Memory()
        inheritable = mem.inheritable()
        cheap = [r for r in mem.facts() if r.cost == "cheap"]
        out.append("## What this workspace already paid for")
        out.append("")
        if not mem.rows:
            out.append("_Nothing recorded. This is the first run here._")
        else:
            out.append("- " + str(len(inheritable)) + " expensive fact(s) inheritable, "
                       + str(len(cheap)) + " cheap fact(s) to re-run, "
                       + str(len(mem.failures())) + " recorded failure(s).")
            out.append("- Run `harness inherit` before deriving anything. Re-deriving a recorded")
            out.append("  fact pays for it twice, and the second payment is invisible.")
            for row in mem.failures()[:6]:
                if row.cheaper_observable:
                    out.append("- was: " + row.statement[:90])
                    out.append("  do: " + row.cheaper_observable[:150])
        out.append("")

    return "\n".join(out) + "\n"


def size_of(text: str) -> int:
    return len(text.encode("utf-8"))


def for_target(target: Path, phase_number: int) -> str:
    from . import state as state_mod
    state = state_mod.load(target)
    mem = memory_mod.load(target) if phase_number == 0 else None
    return compose(state, phase_number, mem=mem)
