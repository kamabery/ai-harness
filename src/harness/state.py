"""The run's state - typed, bounded, and written by this module alone.

Its predecessor kept the same information in a markdown ledger that a session read whole at
every phase and appended to at the end of it. Three measurements killed that design:

* One ledger reached 3,738 lines, of which the captured-output section was 92%.
* Evicting captures into captures/phase-<n>.md fixed that file and the growth RELOCATED: in the
  next workspace the cursor section became 420 of 620 lines, holding a retrospective of every
  phase, inside a section whose own rule read "Exactly one active phase and one next action at
  a time."
* Nothing enforced that rule. The checker had no size ceiling anywhere in 577 lines.

So a positional ceiling relocates the growth and a prose rule does not bind at all. The
constraints here are TYPED: `cursor` is one object with one `next_action`, which makes two
active phases unrepresentable rather than forbidden, and no string anywhere may hold a pasted
stream. Captures live on disk; this file holds a path and a sha256.

docs/STANDARDS.md, *What state may hold*, is the prose half of this module. The numbers below
are the only definition of the ceilings - both the writer and the `state` check import them,
for the reason render.TOKEN_RE exists: three copies kept in step by a comment diverged anyway.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

#: Where state lives, relative to the workspace root.
STATE_FILE = (".harness", "state.json")

#: Raw tool output: captured whole so a 1-of-N failure stays nameable, gitignored because it is
#: the dominant cost of a run, and never citable - a citation must resolve for someone else.
RAW_DIR = (".harness", "raw")

# -- the ceilings, defined once ------------------------------------------------------------------

#: The whole document. A state file needing more than this is holding evidence, not state.
MAX_STATE_BYTES = 64 * 1024
#: Any single string value. The anti-paste rule, and what a 92%-captures ledger fails on at its
#: first append.
MAX_STRING = 1_000
#: The handoff sentence. Long enough to name the next command, short enough to stay one action.
MAX_NEXT_ACTION = 200
#: Resolved facts. Two real runs settled 36 each; 40 leaves room without inviting a survey.
MAX_FACTS = 40
MAX_FACT_STATEMENT = 300
MAX_FAILURE_ROW = 500
#: A committed capture file. Bigger than this is a raw stream, which belongs in RAW_DIR.
MAX_CAPTURE_BYTES = 200 * 1024

STATUSES = ("blocked", "in_progress", "passed")
COSTS = ("cheap", "expensive")
SOURCES = ("derived", "inherited", "asked")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Counts:
    """What the runner said it executed. The count is the signal, never the exit code.

    A test command that exits 0 having run nothing is the most dangerous green available: at the
    exit code it is indistinguishable from a passing suite. `skipped` is here for the same
    reason - a skip count that rose between two phases had a check removed, not a bug fixed.
    """

    executed: int | None = None
    skipped: int | None = None
    baseline_executed: int | None = None
    baseline_skipped: int | None = None

    def as_json(self) -> dict:
        return {
            "executed": self.executed,
            "skipped": self.skipped,
            "baseline_executed": self.baseline_executed,
            "baseline_skipped": self.baseline_skipped,
        }


@dataclass
class Phase:
    """One phase: what proves it, and where the proof is."""

    id: int
    name: str
    test: str
    status: str = "blocked"
    #: The A# facts this phase depends on. `brief` emits these rows and no others, which is why
    #: they are ids rather than prose: the predecessor's plan named its facts only in sentences,
    #: so no slice could be computed from it.
    needs: list[str] = field(default_factory=list)
    capture_ref: str | None = None
    #: sha256 of the capture file as it stood when this phase closed. A committed evidence file
    #: whose sha moves with no phase row is the 30-of-38-overwritten-PNGs failure.
    capture_sha: str | None = None
    red_seen: bool = False
    counts: Counts = field(default_factory=Counts)

    def as_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "test": self.test,
            "status": self.status,
            "needs": list(self.needs),
            "capture_ref": self.capture_ref,
            "capture_sha": self.capture_sha,
            "red_seen": self.red_seen,
            "counts": self.counts.as_json(),
        }


@dataclass
class Fact:
    """A resolved assumption, and the command that would say whether it still holds.

    `cost` decides whether the next run re-runs this or inherits it, and that gate is the only
    part of Shopify's diff-based state model that transfers to a build harness: re-deriving
    something a previous run proved is a full scan where a checksum would have been a diff.
    """

    id: str
    statement: str
    evidence: str
    cost: str = "cheap"
    recheck_cmd: str | None = None
    checksum: str | None = None
    source: str = "derived"
    #: Has this run itself watched the re-check pass? An inherited fact arrives with a previous
    #: run's evidence, which is a lead. Until this is true the fact is open, and phase 0 cannot
    #: close over it - otherwise the inherit gate would let a stale fact in wearing a citation.
    reverified: bool = False

    def as_json(self) -> dict:
        return {
            "id": self.id,
            "statement": self.statement,
            "evidence": self.evidence,
            "cost": self.cost,
            "recheck_cmd": self.recheck_cmd,
            "checksum": self.checksum,
            "source": self.source,
            "reverified": self.reverified,
        }


@dataclass
class Failure:
    """A red signal, its count, and what changed because of it.

    `count` reaching 2 on the same first line is a stop: two identical failures means an
    upstream fact is wrong, and the next speculative fix is the third. `changed_what` and
    `changed_in_phase` are the whole of what the predecessor spread over five lesson tables.
    """

    verbatim_first_line: str
    phase: int
    count: int = 1
    resolution: str | None = None
    changed_what: str | None = None
    changed_in_phase: int | None = None

    def as_json(self) -> dict:
        return {
            "verbatim_first_line": self.verbatim_first_line,
            "phase": self.phase,
            "count": self.count,
            "resolution": self.resolution,
            "changed_what": self.changed_what,
            "changed_in_phase": self.changed_in_phase,
        }


@dataclass
class State:
    """A run, entire. One writer: this module."""

    run: str
    project: str = ""
    phases: list[Phase] = field(default_factory=list)
    #: One object, not a list. Two active phases are unrepresentable here rather than forbidden
    #: in prose - which is the difference between a constraint and a suggestion.
    cursor: dict = field(default_factory=lambda: {"phase": 0, "next_action": ""})
    facts: list[Fact] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)
    handoff: list[str] = field(default_factory=list)

    def phase(self, number: int) -> Phase | None:
        return next((p for p in self.phases if p.id == number), None)

    def fact(self, ident: str) -> Fact | None:
        return next((f for f in self.facts if f.id == ident), None)

    def next_fact_id(self) -> str:
        used = {int(f.id[1:]) for f in self.facts if f.id[1:].isdigit()}
        return "A" + str(max(used, default=0) + 1)

    def open_facts(self) -> list[Fact]:
        """Facts this run may not yet lean on.

        Two kinds: never answered, and inherited from a previous run without this run having
        watched the re-check pass. The second kind is the one the predecessor had no name for -
        it recorded 36 facts, 5 of which cited an archive, and treated a citation as a signal.
        """
        return [f for f in self.facts
                if not f.evidence or (f.source == "inherited" and not f.reverified)]

    def unresolved_failures(self) -> list[Failure]:
        return [f for f in self.failures if not f.resolution]

    def stopped(self) -> list[Failure]:
        """Failures that reached the two-identical threshold and must be escalated."""
        return [f for f in self.failures if f.count >= 2 and not f.resolution]

    def as_json(self) -> dict:
        return {
            "run": self.run,
            "project": self.project,
            "phases": [p.as_json() for p in self.phases],
            # Not coerced. A malformed cursor must reach validate() as the defect it is;
            # coercing it here would make the check crash instead of report, and a check
            # that cannot report is the failure class this harness exists to refuse.
            "cursor": dict(self.cursor) if isinstance(self.cursor, dict) else self.cursor,
            "facts": [f.as_json() for f in self.facts],
            "failures": [f.as_json() for f in self.failures],
            "handoff": list(self.handoff),
        }

    def dumps(self) -> str:
        return json.dumps(self.as_json(), indent=2, ensure_ascii=False) + "\n"


def _only(cls, row: dict) -> dict:
    return {k: v for k, v in row.items() if k in cls.__dataclass_fields__}


def from_json(data: dict) -> State:
    state = State(run=data.get("run", ""), project=data.get("project", ""))
    for row in data.get("phases", ()):
        counts = Counts(**_only(Counts, row.get("counts") or {}))
        phase = Phase(**_only(Phase, dict(row, counts=None)))
        phase.counts = counts
        state.phases.append(phase)
    cursor = data.get("cursor")
    state.cursor = dict(cursor) if isinstance(cursor, dict) else {"phase": None, "next_action": ""}
    state.facts = [Fact(**_only(Fact, r)) for r in data.get("facts", ())]
    state.failures = [Failure(**_only(Failure, r)) for r in data.get("failures", ())]
    state.handoff = list(data.get("handoff", ()))
    return state


def path_for(target: Path) -> Path:
    return target.joinpath(*STATE_FILE)


def load(target: Path) -> State:
    path = path_for(target)
    if not path.is_file():
        raise FileNotFoundError("no state at " + str(path))
    return from_json(json.loads(path.read_text(encoding="utf-8")))


def save(target: Path, state: State) -> Path:
    """Write state, or refuse. A defective state file is never written, not even partially.

    The validation is the same function the `state` check runs, so a file this module wrote
    cannot fail that check. That is the point: the ceilings bind when the write happens, not at
    a review nobody schedules.
    """
    defects = validate(state)
    if defects:
        raise ValueError("refused: state would be invalid\n  " + "\n  ".join(defects))
    path = path_for(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.dumps(), encoding="utf-8")
    return path


def _strings(obj, trail: str = "") -> list:
    """Every string in the document, with the path that reaches it."""
    found = []
    if isinstance(obj, str):
        found.append((trail, obj))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            found += _strings(value, trail + "." + str(key) if trail else str(key))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            found += _strings(value, trail + "[" + str(index) + "]")
    return found


def validate(state: State) -> list:
    """Every ceiling, as a list of defects. Empty means the state is writable."""
    defects = []
    document = state.as_json()

    size = len(state.dumps().encode("utf-8"))
    if size > MAX_STATE_BYTES:
        defects.append(
            "state.json is " + str(size) + " bytes, over the " + str(MAX_STATE_BYTES)
            + "-byte ceiling - it is holding evidence rather than state")

    for trail, value in _strings(document):
        if len(value) > MAX_STRING:
            defects.append(
                trail + " is " + str(len(value)) + " chars, over the " + str(MAX_STRING)
                + "-char ceiling - paste the stream into captures/ and cite it")

    if not isinstance(state.cursor, dict):
        defects.append("cursor must be one object, not a list - two active phases is not a state")
    else:
        unknown = set(state.cursor) - {"phase", "next_action", "blocked_on", "live_state"}
        if unknown:
            defects.append("cursor has keys that are not part of it: " + str(sorted(unknown)))
        action = state.cursor.get("next_action") or ""
        if len(action) > MAX_NEXT_ACTION:
            defects.append(
                "cursor.next_action is " + str(len(action)) + " chars, over "
                + str(MAX_NEXT_ACTION) + " - one action")

    ids = [p.id for p in state.phases]
    if len(ids) != len(set(ids)):
        defects.append("two phases share an id")
    for phase in state.phases:
        if phase.status not in STATUSES:
            defects.append("phase " + str(phase.id) + " status " + repr(phase.status)
                           + " is not one of " + str(STATUSES))
        if phase.status == "passed" and not phase.red_seen:
            defects.append(
                "phase " + str(phase.id) + " is passed with red_seen false - a green nobody has "
                "watched go red is the same document as a check that cannot fail")
        if phase.status == "passed" and not phase.capture_sha:
            defects.append("phase " + str(phase.id) + " is passed with no capture_sha")
        for need in phase.needs:
            if state.fact(need) is None:
                defects.append("phase " + str(phase.id) + " needs " + need
                               + ", which is not a fact")

    active = [p.id for p in state.phases if p.status == "in_progress"]
    if len(active) > 1:
        defects.append("phases " + str(active) + " are all in_progress - one at a time")

    if len(state.facts) > MAX_FACTS:
        defects.append(str(len(state.facts)) + " facts, over the " + str(MAX_FACTS) + " ceiling")
    seen = set()
    for fact in state.facts:
        if fact.id in seen:
            defects.append("two facts share the id " + fact.id)
        seen.add(fact.id)
        if len(fact.statement) > MAX_FACT_STATEMENT:
            defects.append(
                "fact " + fact.id + " statement is " + str(len(fact.statement)) + " chars, over "
                + str(MAX_FACT_STATEMENT) + " - a fact, not a paragraph")
        if fact.cost not in COSTS:
            defects.append("fact " + fact.id + " cost " + repr(fact.cost) + " is not one of "
                           + str(COSTS))
        if fact.source not in SOURCES:
            defects.append("fact " + fact.id + " source " + repr(fact.source)
                           + " is not one of " + str(SOURCES))
        if fact.cost == "expensive" and not fact.recheck_cmd:
            defects.append(
                "fact " + fact.id + " is expensive with no recheck_cmd - the next run can "
                "neither inherit it nor re-prove it")

    for failure in state.failures:
        row = len(failure.verbatim_first_line) + len(failure.resolution or "")
        if row > MAX_FAILURE_ROW:
            defects.append("a failure row is " + str(row) + " chars, over "
                           + str(MAX_FAILURE_ROW))
        if failure.changed_what and failure.changed_in_phase is None:
            defects.append(
                "failure " + repr(failure.verbatim_first_line[:40]) + " changed something but "
                "names no phase it changed it in")

    return defects
