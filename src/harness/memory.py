"""What this workspace has already paid for - one file, read by the next run's first phase.

The predecessor split this in two and lost it. `docs/BUILD-HISTORY/<run>.md` held the expensive
facts and `docs/LESSONS-LEDGER.md` was to hold the failures; the archive phase was required to
write both and a check was required to read them. Neither workspace on record ever had a
LESSONS-LEDGER.md. Two files let one be dropped silently, so there is one file here.

The archive also carried the wrong subset. Its lessons section said: "Lessons that were APPLIED
within the run are in LESSONS.md, not repeated here" - so it kept 3 of 10. The render-readiness
family had been APPLIED inside the run, so it was excluded by design, and the next run in the
same repository re-derived it three days later across four of its eleven lessons. That reasoning
is wrong in one step: a lesson being applied inside one run does not mean the next run knows it.
APPLIED describes what that run did with it, not whether it is durable. So every row is carried
here regardless, and only the "which later phase used it" column is run-local.

The inherit-vs-recheck gate is the one part of Shopify's diff-based state model that transfers.
A fact whose re-check costs a second is always re-run; a fact that cost a build, a browser or an
enumeration of thirty-one CSS custom properties is inherited while its checksum matches.
Re-deriving what a previous run proved is a full scan where a checksum would have been a diff:
the measured waste is 36 archived facts against 36 fresh rows, of which 5 cited the archive.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .state import MAX_FACT_STATEMENT, MAX_STRING, Fact, State

MEMORY_FILE = (".harness", "memory.json")
RENDERED = ("docs", "MEMORY.md")

KINDS = ("fact", "failure")

#: A cell in the rendered table. Defined here so no module needs a backslash literal inline.
_PIPE = "|"
_PIPE_ESCAPED = chr(92) + "|"


def _cell(text: str, limit: int = 300) -> str:
    return (text or "-").replace(_PIPE, _PIPE_ESCAPED)[:limit]


@dataclass
class Row:
    """One thing this workspace learned, and what it costs to confirm it still holds."""

    id: str
    run: str
    date: str
    kind: str
    statement: str
    evidence: str = ""
    #: cheap = re-run it every time. expensive = inherit while the checksum matches.
    cost: str = "cheap"
    recheck_cmd: str | None = None
    checksum: str | None = None
    #: For a failure row: the mechanism, and the cheaper observable that would have caught it.
    mechanism: str = ""
    cheaper_observable: str = ""

    def as_json(self) -> dict:
        return {
            "id": self.id, "run": self.run, "date": self.date, "kind": self.kind,
            "statement": self.statement, "evidence": self.evidence, "cost": self.cost,
            "recheck_cmd": self.recheck_cmd, "checksum": self.checksum,
            "mechanism": self.mechanism, "cheaper_observable": self.cheaper_observable,
        }


@dataclass
class Memory:
    rows: list[Row] = field(default_factory=list)

    def facts(self) -> list[Row]:
        return [r for r in self.rows if r.kind == "fact"]

    def failures(self) -> list[Row]:
        return [r for r in self.rows if r.kind == "failure"]

    def inheritable(self) -> list[Row]:
        """Expensive facts a new run may adopt instead of re-deriving."""
        return [r for r in self.facts() if r.cost == "expensive"]

    def as_json(self) -> dict:
        return {"rows": [r.as_json() for r in self.rows]}

    def dumps(self) -> str:
        return json.dumps(self.as_json(), indent=2, ensure_ascii=False) + "\n"

    def next_id(self) -> str:
        used = {int(r.id[1:]) for r in self.rows if r.id[1:].isdigit()}
        return "M" + str(max(used, default=0) + 1)


def path_for(target: Path) -> Path:
    return target.joinpath(*MEMORY_FILE)


def load(target: Path) -> Memory:
    path = path_for(target)
    if not path.is_file():
        return Memory()
    data = json.loads(path.read_text(encoding="utf-8"))
    fields = Row.__dataclass_fields__
    return Memory(rows=[Row(**{k: v for k, v in r.items() if k in fields})
                        for r in data.get("rows", ())])


def save(target: Path, memory: Memory) -> Path:
    defects = validate(memory)
    if defects:
        raise ValueError("refused: memory would be invalid\n  " + "\n  ".join(defects))
    path = path_for(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(memory.dumps(), encoding="utf-8")
    return path


def validate(memory: Memory) -> list:
    defects = []
    seen = set()
    for row in memory.rows:
        if row.id in seen:
            defects.append("two memory rows share the id " + row.id)
        seen.add(row.id)
        if row.kind not in KINDS:
            defects.append("row " + row.id + " kind " + repr(row.kind) + " is not one of "
                           + str(KINDS))
        for name in ("statement", "mechanism", "cheaper_observable"):
            value = getattr(row, name) or ""
            if len(value) > MAX_STRING:
                defects.append("row " + row.id + " " + name + " is " + str(len(value))
                               + " chars, over " + str(MAX_STRING))
        if row.kind == "failure" and not row.cheaper_observable:
            defects.append(
                "row " + row.id + " is a failure with no cheaper observable - a lesson that "
                "names no cheaper way to have caught it is a story, not a lesson")
        if row.cost == "expensive" and not row.recheck_cmd:
            defects.append(
                "row " + row.id + " is expensive with no recheck_cmd - the next run can neither "
                "inherit it nor re-prove it")
    return defects


def archive(target: Path, state: State, *, date: str) -> tuple:
    """Fold a finished run into memory. A command, not an instruction to remember.

    The predecessor asked a phase pack to do this in prose, and the phase reported PASSED without
    doing it. Everything here is mechanical, so "the archive was skipped" is not a state this can
    reach while `reconcile` runs.
    """
    memory = load(target)
    known = {(r.run, r.statement) for r in memory.rows}
    added = []

    for fact in state.facts:
        if not fact.evidence or (state.run, fact.statement) in known:
            continue
        row = Row(id=memory.next_id(), run=state.run, date=date, kind="fact",
                  statement=fact.statement, evidence=fact.evidence, cost=fact.cost,
                  recheck_cmd=fact.recheck_cmd, checksum=fact.checksum)
        memory.rows.append(row)
        added.append(row.id + " fact " + fact.id)

    # Every failure, whatever the run did with it. This is the exclusion rule reversed.
    for failure in state.failures:
        if (state.run, failure.verbatim_first_line) in known:
            continue
        row = Row(id=memory.next_id(), run=state.run, date=date, kind="failure",
                  statement=failure.verbatim_first_line,
                  evidence="phase " + str(failure.phase),
                  mechanism=failure.resolution or "",
                  cheaper_observable=failure.changed_what or "")
        memory.rows.append(row)
        added.append(row.id + " failure at phase " + str(failure.phase))

    return memory, added


def inherit(target: Path, state: State) -> list:
    """Adopt what a previous run proved; re-run what is cheap to re-run.

    Returns one line per decision, for the phase-0 capture. A cheap fact is never inherited:
    re-running it costs a second, and a toolchain version is a fact that changes silently. An
    expensive fact is inherited only while its checksum matches, because an inherited fact that
    is no longer true is worse than an open question.
    """
    memory = load(target)
    notes = []
    for row in memory.inheritable():
        if any(f.statement == row.statement for f in state.facts):
            continue
        # A memory row may run to MAX_STRING; a fact in state is held to a tighter ceiling,
        # because state is read at every phase and memory only at phase 0. The full text stays
        # in memory.json, and the row id below is what leads back to it.
        statement = row.statement
        if len(statement) > MAX_FACT_STATEMENT:
            statement = statement[:MAX_FACT_STATEMENT - 12].rstrip() + " [" + row.id + "]"
        state.facts.append(Fact(
            id=state.next_fact_id(), statement=statement,
            evidence=row.evidence + " (inherited from run " + row.run + ", " + row.date + ")",
            cost=row.cost, recheck_cmd=row.recheck_cmd, checksum=row.checksum,
            source="inherited"))
        notes.append("inherited " + row.id + ": " + row.statement[:70]
                     + " - re-check with: " + str(row.recheck_cmd))
    rerun = [r for r in memory.facts() if r.cost == "cheap" and r.recheck_cmd]
    rederive = [r for r in memory.facts() if r.cost == "cheap" and not r.recheck_cmd]
    for row in rerun:
        notes.append("re-run (cheap, " + row.id + "): " + str(row.recheck_cmd))
    if rederive:
        notes.append(
            "re-derive from scratch: " + str(len(rederive)) + " row(s) name no command, so they "
            "are leads, not signals (" + ", ".join(r.id for r in rederive[:8])
            + ("..." if len(rederive) > 8 else "") + ")")
    return notes


def render(memory: Memory) -> str:
    """The human view. Read-only: `harness render` regenerates it from the json."""
    out = ["# What this workspace has already paid for", ""]
    out.append("Generated from `.harness/memory.json`. Do not edit - `harness render` overwrites")
    out.append("it, and the `memory` check fails on a stale copy.")
    out.append("")

    facts = memory.facts()
    out.append("## Facts (" + str(len(facts)) + ")")
    out.append("")
    if facts:
        out.append("| id | run | fact | how to confirm it still holds | inherit? |")
        out.append("|---|---|---|---|---|")
        for row in facts:
            gate = "inherit while checksum matches" if row.cost == "expensive" else "re-run always"
            cmd = "`" + (row.recheck_cmd or "-") + "`"
            out.append("| " + " | ".join(
                [row.id, row.run, _cell(row.statement), cmd, gate]) + " |")
    else:
        out.append("_Nothing yet._")
    out.append("")

    failures = memory.failures()
    out.append("## Failures, and the cheaper observable (" + str(len(failures)) + ")")
    out.append("")
    out.append("Carried whatever the run did with them. A lesson applied inside one run does not")
    out.append("mean the next run knows it.")
    out.append("")
    if failures:
        out.append("| id | run | the failure | the cheaper observable |")
        out.append("|---|---|---|---|")
        for row in failures:
            out.append("| " + " | ".join(
                [row.id, row.run, _cell(row.statement, 200),
                 _cell(row.cheaper_observable)]) + " |")
    else:
        out.append("_Nothing yet._")
    out.append("")
    return "\n".join(out)


def write_rendered(target: Path, memory: Memory) -> Path:
    path = target.joinpath(*RENDERED)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(memory), encoding="utf-8")
    return path
