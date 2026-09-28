"""The surface an agent calls. Every call returns a result; a refusal is a value, not an exception.

Three rules, inherited from the predecessor because they were right there:

* **A refusal is a result.** `code 1`, with the reason as the first line. You are reading a return
  value, so read it - do not wrap these in `try`.
* **Nothing defaults to the current directory.** The workspace is always an argument. A shell's
  working directory is not evidence of which tree a request meant, and scaffolding into the wrong
  one is invisible from inside the documents: they read as authoritative against a repository
  nobody meant.
* **Nothing half-completes.** State validates entirely in memory and is written whole or not at
  all.

Codes: `0` complete, `1` refused, `N` the defect count from a check.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path

from . import brief as brief_mod
from . import check as check_mod
from . import detect as detect_mod
from . import importer as importer_mod
from . import memory as memory_mod
from . import state as state_mod


@dataclass
class Outcome:
    """What a call reported, what it decided, and the same thing structured."""

    code: int
    report: str
    data: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.report

    def rows(self, containing: str = "") -> list:
        """Every markdown table row in the report, optionally filtered."""
        return [line for line in self.report.splitlines()
                if line.strip().startswith("|") and "---" not in line and containing in line]

    def json(self, indent: int = 2) -> str:
        import json as _json
        return _json.dumps(self.data, indent=indent, default=str)

    @property
    def out(self) -> str:
        """The report text, under the name the assertions use."""
        return self.report

    @property
    def ok(self) -> bool:
        """Complete, with nothing to fix. Any non-zero code is a defect count or a refusal."""
        return self.code == 0

    @property
    def refused(self) -> bool:
        return self.code == 1


def _refuse(reason: str) -> Outcome:
    text = str(reason)
    if text.startswith("refused: "):
        text = text[len("refused: "):]
    return Outcome(code=1, report="refused: " + text)


def show(outcome: Outcome) -> int:
    """Print the report and hand back the code, so a caller can branch on a number."""
    print(outcome.report)
    return outcome.code


def _today() -> str:
    return _dt.date.today().isoformat()


def workspace(value, what: str = "target") -> Path:
    if value is None or str(value).strip() == "":
        raise ValueError("the " + what + " is an argument, never the current directory")
    return Path(str(value)).expanduser().resolve()


def run_dir(target: Path, run: str) -> Path:
    return target / "runs" / run


# -- looking -------------------------------------------------------------------------------------


def detect(target=None) -> Outcome:
    """Inspect a workspace. Reads files, runs nothing, writes nothing."""
    try:
        root = workspace(target)
    except ValueError as exc:
        return _refuse(str(exc))
    if not root.is_dir():
        return _refuse("no directory at " + str(root))
    found = detect_mod.detect(root)
    data = {
        "workspace": str(root),
        "packs": found.active,
        "facts": [f.__dict__ for f in found.facts],
        "conflicts": [c.__dict__ for c in found.conflicts],
        "examined": found.examined,
        "unresolved": len(found.unresolved),
    }
    return Outcome(code=0 if found.clean else 3, report=detect_mod.format_report(found),
                   data=data)


def status(target=None) -> Outcome:
    """Where the run is, in one screen. Never the whole ledger."""
    try:
        root = workspace(target)
    except ValueError as exc:
        return _refuse(str(exc))
    try:
        state = state_mod.load(root)
    except FileNotFoundError as exc:
        return _refuse(str(exc))
    mem = memory_mod.load(root)
    lines = ["run " + state.run + " (" + (state.project or "-") + ")", ""]
    for phase in state.phases:
        mark = {"passed": "x", "in_progress": ">", "blocked": " "}.get(phase.status, "?")
        lines.append("  [" + mark + "] " + str(phase.id) + " " + phase.name)
    lines.append("")
    lines.append("  cursor: phase " + str(state.cursor.get("phase"))
                 + " - " + (state.cursor.get("next_action") or "-"))
    lines.append("  facts: " + str(len(state.facts)) + " (" + str(len(state.open_facts()))
                 + " open) | failures: " + str(len(state.unresolved_failures())) + " open")
    stopped = state.stopped()
    if stopped:
        lines.append("  STOP: " + str(len(stopped)) + " failure(s) hit the two-identical rule")
    lines.append("  memory: " + str(len(mem.rows)) + " row(s) this workspace already paid for")
    return Outcome(code=0, report="\n".join(lines), data=state.as_json())


def brief(target=None, phase: int = 0) -> Outcome:
    """What one phase is handed. This is what a phase pack tells an agent to run."""
    try:
        root = workspace(target)
    except ValueError as exc:
        return _refuse(str(exc))
    try:
        text = brief_mod.for_target(root, int(phase))
    except FileNotFoundError as exc:
        return _refuse(str(exc))
    size = brief_mod.size_of(text)
    if size > brief_mod.MAX_BYTES:
        return Outcome(code=1, report="refused: this brief is " + str(size) + " bytes, over the "
                       + str(brief_mod.MAX_BYTES) + "-byte ceiling. The slice has stopped being "
                       "a slice - narrow the phase's needs.", data={"bytes": size})
    return Outcome(code=0, report=text, data={"bytes": size})


# -- checking ------------------------------------------------------------------------------------


def check(target=None, run: str | None = None, checks=None) -> Outcome:
    """The checks. The code is the defect count, so a phase closes on a number."""
    try:
        root = workspace(target)
    except ValueError as exc:
        return _refuse(str(exc))
    try:
        state = state_mod.load(root)
    except FileNotFoundError as exc:
        return _refuse(str(exc))
    directory = run_dir(root, run or state.run)
    try:
        results = check_mod.run_all(root, directory, checks)
    except ValueError as exc:
        return _refuse(str(exc))
    text, defects = check_mod.report(results)
    return Outcome(code=defects, report=text,
                   data={"defects": defects,
                         "checks": {r.name: len(r.defects) for r in results}})


def selftest() -> Outcome:
    """Has every check been seen to reject its own bad input? Nothing else is proof."""
    result = check_mod.check_selftest(Path("."), Path("."))
    return Outcome(code=len(result.defects), report=result.report(),
                   data={"examined": result.examined})


# -- the run shape -------------------------------------------------------------------------------

#: Four fixed phases, and the slices between them. The predecessor ran 10 to 13 phases, of which
#: 7 produced no product code; each phase here survives because it catches a class the others do
#: not. `reconcile` merges cleanup and archive deliberately: a `git status --porcelain` read
#: against the spec is what found a named deliverable that had never been built, after nine green
#: phases and two blind reviewers ruling 9 PROVEN / 0 NOT PROVEN.
FIXED_PHASES = (
    (0, "preflight", "harness check --checks state,memory,ignore"),
    (1, "baseline", "the build and test commands, counts captured, red channel proved"),
)
CLOSING_PHASE = ("reconcile", "harness check && git status --porcelain")


def start_run(target=None, run: str | None = None, *, slices: int = 2,
              project: str = "") -> Outcome:
    """Scaffold a run: four fixed phases and `slices` build phases between them.

    Writes `state.json` and one capture file per phase, and refuses rather than half-completing.
    A capture file is created empty on purpose and the `state` check knows the difference: the
    predecessor wrote 818-byte templates reading "(nothing captured yet)" and its check asserted
    only that the file existed, so it passed on ten stubs.
    """
    try:
        root = workspace(target)
    except ValueError as exc:
        return _refuse(str(exc))
    if not run:
        return _refuse("a run needs a name")
    if not root.is_dir():
        return _refuse("no directory at " + str(root))
    if state_mod.path_for(root).is_file():
        return _refuse("a run is already in flight here - " + str(state_mod.path_for(root))
                       + " exists. Finish or archive it; two runs in one state file is not a state")
    if slices < 1:
        return _refuse("a run with no build phase builds nothing")

    state = state_mod.State(run=run, project=project or root.name)
    for number, name, test in FIXED_PHASES:
        state.phases.append(state_mod.Phase(id=number, name=name, test=test))
    for index in range(slices):
        number = 2 + index
        state.phases.append(state_mod.Phase(
            id=number, name="slice-" + str(index + 1),
            test="the slice's own command, red before green"))
    last = 2 + slices
    state.phases.append(state_mod.Phase(id=last, name=CLOSING_PHASE[0], test=CLOSING_PHASE[1]))

    state.phases[0].status = "in_progress"
    state.cursor = {"phase": 0,
                    "next_action": "Run `harness inherit`, then answer the open facts.",
                    "blocked_on": "every fact still open"}
    state.handoff = [_today() + " scaffolded " + str(len(state.phases)) + " phases"]

    directory = run_dir(root, run)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "captures").mkdir(exist_ok=True)
    root.joinpath(*state_mod.RAW_DIR).mkdir(parents=True, exist_ok=True)
    for phase in state.phases:
        phase.capture_ref = "captures/phase-" + str(phase.id) + ".md"
        path = directory / phase.capture_ref
        if not path.exists():
            path.write_text("", encoding="utf-8")

    try:
        state_mod.save(root, state)
    except ValueError as exc:
        return _refuse(str(exc))
    return Outcome(code=0, data=state.as_json(), report="\n".join([
        "scaffolded run " + run + " in " + str(root),
        "  phases: " + ", ".join(str(p.id) + " " + p.name for p in state.phases),
        "  state:  " + str(state_mod.path_for(root)),
        "",
        "Next: harness inherit   (what this workspace already paid for)",
        "      harness brief 0   (what phase 0 is handed)",
    ]))


def inherit(target=None) -> Outcome:
    """Adopt what a previous run proved; re-run what is cheap to re-run."""
    try:
        root = workspace(target)
    except ValueError as exc:
        return _refuse(str(exc))
    try:
        state = state_mod.load(root)
    except FileNotFoundError as exc:
        return _refuse(str(exc))
    notes = memory_mod.inherit(root, state)
    try:
        state_mod.save(root, state)
    except ValueError as exc:
        return _refuse(str(exc))
    if not notes:
        return Outcome(code=0, report="nothing in memory to inherit - this is the first run here.")
    return Outcome(code=0, data={"notes": notes}, report="\n".join(
        ["what this workspace already paid for:", ""] + ["  " + n for n in notes] + [
            "",
            "An inherited fact is a lead until its re-check runs. A cheap fact is never",
            "inherited: re-running it costs a second, and a version changes silently.",
        ]))


def archive(target=None) -> Outcome:
    """Fold this run into the workspace's memory, and render the human view."""
    try:
        root = workspace(target)
    except ValueError as exc:
        return _refuse(str(exc))
    try:
        state = state_mod.load(root)
    except FileNotFoundError as exc:
        return _refuse(str(exc))
    mem, added = memory_mod.archive(root, state, date=_today())
    try:
        memory_mod.save(root, mem)
    except ValueError as exc:
        return _refuse(str(exc))
    rendered = memory_mod.write_rendered(root, mem)
    return Outcome(code=0, data={"added": added}, report="\n".join(
        ["archived run " + state.run + ": " + str(len(added)) + " row(s) added",
         "  memory:   " + str(memory_mod.path_for(root)),
         "  rendered: " + str(rendered)]
        + ["  + " + a for a in added[:12]]))


def import_workspace(target=None, source=None) -> Outcome:
    """Read an old harness workspace's archive and lesson ledgers into memory.

    Nothing imported arrives as a signal: a fact with no recoverable command comes in as `cheap`,
    which here means re-derive every time. The archive is a lead.
    """
    try:
        root = workspace(target)
        old = workspace(source, "source")
    except ValueError as exc:
        return _refuse(str(exc))
    if not old.is_dir():
        return _refuse("no directory at " + str(old))
    mem, notes = importer_mod.into(root, old)
    try:
        memory_mod.save(root, mem)
    except ValueError as exc:
        return _refuse(str(exc))
    memory_mod.write_rendered(root, mem)
    return Outcome(code=0, data={"rows": len(mem.rows)}, report="\n".join(
        ["imported from " + str(old)] + ["  " + n for n in notes]
        + ["  memory now holds " + str(len(mem.rows)) + " row(s): "
           + str(len(mem.facts())) + " fact(s), " + str(len(mem.failures())) + " failure(s), "
           + str(len(mem.inheritable())) + " inheritable"]))


def render(target=None) -> Outcome:
    """Regenerate the read-only human views from the json."""
    try:
        root = workspace(target)
    except ValueError as exc:
        return _refuse(str(exc))
    mem = memory_mod.load(root)
    path = memory_mod.write_rendered(root, mem)
    return Outcome(code=0, report="wrote " + str(path), data={"rows": len(mem.rows)})


# -- the guardrails ------------------------------------------------------------------------------


def guard(target=None, *, execute: bool = True) -> Outcome:
    """Run the declared architectural rules, and count the rules against the checks.

    The coverage count is the point, not a footnote. The workspace that prompted this had ten
    rules and four checks, the other six declared unchecked because "TODO - no check written
    yet". A rule with nothing behind it is inherited by every later run as though somebody
    enforced it, so an unchecked rule is reprinted every single run, and a reason that merely
    defers the work is a defect rather than an exemption.
    """
    from . import guards as guards_mod
    try:
        root = workspace(target)
    except ValueError as exc:
        return _refuse(str(exc))
    try:
        result = guards_mod.run_guards(root, execute=execute)
    except guards_mod.GuardsError as exc:
        return _refuse(str(exc))
    return Outcome(code=len(result.defects), report=result.report(), data={
        "workspace": str(root),
        "examined": result.examined,
        "checked": result.checked,
        "unchecked": [r.rule for r in result.uncovered],
        "defects": list(result.defects),
        "advisories": list(result.advisories),
        "rules": [{"rule": r.rule, "check": r.check, "exit_code": r.exit_code,
                   "unchecked_because": r.unchecked_because} for r in result.rules],
    })


def list_packs() -> Outcome:
    """Every technology pack, and what triggers it."""
    from . import packs as packs_mod
    found = packs_mod.load_tech_packs()
    lines = ["tech packs (" + str(len(found)) + ")", ""]
    for name in sorted(found):
        pack = found[name]
        needs = ("  requires: " + ", ".join(pack.requires)) if pack.requires else ""
        lines.append("  " + name + " - " + pack.trigger_summary + needs)
        if pack.description:
            lines.append("      " + pack.description)
    lines.append("")
    lines.append("There is one run shape: 0 preflight, 1 baseline, 2..N slices, N+1 reconcile.")
    lines.append("A pack says what a tree is built with. It does not multiply the phases.")
    return Outcome(code=0, report="\n".join(lines), data={"packs": sorted(found)})


def scorecard(target=None) -> Outcome:
    """Grade this workspace against what this package can actually check."""
    from . import score as score_mod
    try:
        root = workspace(target)
    except ValueError as exc:
        return _refuse(str(exc))
    report, weak = score_mod.scorecard(root)
    return Outcome(code=weak, report=report, data={"weak": weak})
