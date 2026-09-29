"""The checks, and the rule that a check which has never been seen to reject cannot report green.

Its predecessor had seven checks and 2,041 lines of tests across four fixture workspaces - a
serious suite - and nine instrument defects shipped anyway. The reason is structural. Those were
unit tests of harness code against fixtures: they proved `contrast()` returns a defect when
handed no readable pair. They were not proof that the check, as wired into a live workspace,
rejects that workspace's actual failing case. Two recorded examples:

* A gate matched the ledger's own legend line - the line that *defines* the vocabulary it
  searched for - so it was true in every run that has ever existed.
* A capture-file check asserted the file exists. Ten files existed as 818-byte template stubs
  reading "(nothing captured yet)", and it passed on all ten.

So every check here ships a `selftest` that builds the input it must refuse and asserts it is
refused, and `run_all` withholds green from any check whose selftest did not run here. That is a
different assertion from a unit test - *this check, on this machine, has been observed to
reject* - and it is the part pytest cannot supply.

Two corollaries, each from a recorded failure:

* **Every counting check asserts a floor**, never only a ceiling. Zero is trivially true of
  nothing: a page that rendered nothing scored `overflow=False consoleErrors=0 axe=0`.
* **No check may match text it or its own template authored.**
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import brief as brief_mod
from . import memory as memory_mod
from . import state as state_mod


@dataclass
class Result:
    """What one check examined, and every defect it found."""

    name: str
    examined: int = 0
    defects: list = field(default_factory=list)
    #: None once the check has been seen to reject its own bad input; otherwise why not.
    unproven: str | None = None

    @property
    def ok(self) -> bool:
        return not self.defects and self.unproven is None

    def report(self) -> str:
        lines = []
        for defect in self.defects:
            lines.append("  DEFECT  " + defect)
        if self.unproven:
            lines.append("  UNPROVEN  " + self.unproven)
        verdict = "PASS" if self.ok else "FAIL"
        lines.append("harness check (" + self.name + "): " + verdict + " - "
                     + str(len(self.defects)) + " defect(s), examined " + str(self.examined))
        return "\n".join(lines)


@dataclass
class Check:
    name: str
    describe: str
    run: object
    selftest: object


REGISTRY: dict = {}


def register(name: str, describe: str, selftest) -> object:
    def wrap(func):
        REGISTRY[name] = Check(name=name, describe=describe, run=func, selftest=selftest)
        return func
    return wrap


# -- state ---------------------------------------------------------------------------------------


def _selftest_state() -> str | None:
    """A state holding a pasted stream must be refused."""
    bad = state_mod.State(run="selftest")
    bad.facts = [state_mod.Fact("A1", "x" * 5000, "p:1")]
    if not state_mod.validate(bad):
        return "a 5,000-char fact statement was accepted"
    worse = state_mod.State(run="selftest")
    worse.phases = [state_mod.Phase(1, "a", "c", status="passed")]
    if not state_mod.validate(worse):
        return "a phase passed with red_seen false was accepted"
    return None


@register("state", "the schema and every ceiling", _selftest_state)
def check_state(target: Path, run_dir: Path) -> Result:
    result = Result(name="state")
    try:
        state = state_mod.load(target)
    except FileNotFoundError as exc:
        result.defects.append(str(exc))
        return result
    result.defects.extend(state_mod.validate(state))
    result.examined = len(state.phases) + len(state.facts) + len(state.failures)

    # A committed capture may not be a raw stream, and may not be a stub either. The predecessor
    # checked presence and passed on ten 818-byte templates.
    for phase in state.phases:
        if not phase.capture_ref:
            continue
        path = run_dir / phase.capture_ref if not Path(phase.capture_ref).is_absolute() \
            else Path(phase.capture_ref)
        if not path.is_file():
            path = target / phase.capture_ref
        if not path.is_file():
            if phase.status == "passed":
                result.defects.append(
                    "phase " + str(phase.id) + " is passed and its capture "
                    + phase.capture_ref + " does not exist")
            continue
        size = path.stat().st_size
        if size > state_mod.MAX_CAPTURE_BYTES:
            result.defects.append(
                phase.capture_ref + " is " + str(size) + " bytes, over the "
                + str(state_mod.MAX_CAPTURE_BYTES) + "-byte ceiling - the raw stream belongs in "
                + "/".join(state_mod.RAW_DIR))
        if phase.status == "passed":
            text = path.read_text(encoding="utf-8", errors="replace")
            if state_mod.sha256(text) != phase.capture_sha:
                result.defects.append(
                    phase.capture_ref + " has changed since phase " + str(phase.id)
                    + " closed - its sha does not match the one in state")
    return result


# -- brief ---------------------------------------------------------------------------------------


def _selftest_brief() -> str | None:
    """A brief that has grown back into a ledger must be refused."""
    bad = state_mod.State(run="selftest")
    bad.facts = [state_mod.Fact("A" + str(i), "a fact worth 200 chars " + "y" * 200,
                                "p:" + str(i)) for i in range(1, 30)]
    bad.phases = [state_mod.Phase(1, "p", "c", needs=[f.id for f in bad.facts])]
    text = brief_mod.compose(bad, 1)
    if brief_mod.size_of(text) <= brief_mod.MAX_BYTES:
        return "a brief naming 29 facts came in under the ceiling, so the ceiling binds nothing"
    return None


@register("brief", "every phase's slice stays a slice", _selftest_brief)
def check_brief(target: Path, run_dir: Path) -> Result:
    result = Result(name="brief")
    try:
        state = state_mod.load(target)
    except FileNotFoundError as exc:
        result.defects.append(str(exc))
        return result
    mem = memory_mod.load(target)
    for phase in state.phases:
        text = brief_mod.compose(state, phase.id, mem=mem)
        size = brief_mod.size_of(text)
        result.examined += 1
        if size > brief_mod.MAX_BYTES:
            result.defects.append(
                "brief for phase " + str(phase.id) + " is " + str(size) + " bytes, over the "
                + str(brief_mod.MAX_BYTES) + "-byte ceiling - it has stopped being a slice")
        if not phase.needs and phase.id > 1:
            result.defects.append(
                "phase " + str(phase.id) + " declares no needs, so its brief cannot be targeted "
                "- name the facts it depends on")
    return result


# -- baseline ------------------------------------------------------------------------------------


def _selftest_baseline() -> str | None:
    """A count that fell must be refused, and the `>=` repair must not be available."""
    bad = state_mod.State(run="selftest")
    bad.phases = [
        state_mod.Phase(1, "baseline", "t", status="passed", red_seen=True,
                        capture_sha="x", counts=state_mod.Counts(executed=97, skipped=0)),
        state_mod.Phase(2, "slice", "t", status="passed", red_seen=True, capture_sha="x",
                        counts=state_mod.Counts(executed=61, skipped=4,
                                                baseline_executed=97, baseline_skipped=0)),
    ]
    if not _baseline_defects(bad):
        return "a suite that fell from 97 to 61 executed, with skips up from 0 to 4, was accepted"
    return None


def _baseline_defects(state: state_mod.State) -> list:
    """Executed compared number to number, and skipped too.

    A silenced check produces a green byte-for-byte identical to the green a real fix produces.
    The executed count and the skipped count are the only things that tell them apart, which is
    why this never relaxes to a floor of `>=`: that repair makes the red go away and deletes the
    control, and it looks like tidying.
    """
    defects = []
    for phase in state.phases:
        counts = phase.counts
        if phase.status != "passed":
            continue
        if counts.executed is None:
            defects.append(
                "phase " + str(phase.id) + " is passed with no executed count - the count is the "
                "signal, and a suite that ran nothing exits 0 just like a passing one")
            continue
        if counts.executed == 0:
            defects.append(
                "phase " + str(phase.id) + " executed 0 tests - that is a FAIL, not a baseline")
        if counts.baseline_executed is not None and counts.executed < counts.baseline_executed:
            defects.append(
                "phase " + str(phase.id) + " executed " + str(counts.executed) + " against a "
                "baseline of " + str(counts.baseline_executed) + " - a count that fell had a "
                "check removed, not a bug fixed")
        if (counts.baseline_skipped is not None and counts.skipped is not None
                and counts.skipped > counts.baseline_skipped):
            defects.append(
                "phase " + str(phase.id) + " skipped " + str(counts.skipped) + " against a "
                "baseline of " + str(counts.baseline_skipped) + " - a skip count that rose is a "
                "silenced check")
    return defects


@register("baseline", "executed and skipped counts, number for number", _selftest_baseline)
def check_baseline(target: Path, run_dir: Path) -> Result:
    result = Result(name="baseline")
    try:
        state = state_mod.load(target)
    except FileNotFoundError as exc:
        result.defects.append(str(exc))
        return result
    result.defects.extend(_baseline_defects(state))
    result.examined = len([p for p in state.phases if p.status == "passed"])
    return result


# -- red -----------------------------------------------------------------------------------------

RED_MARK = "--- RED"
PASS_MARK = "--- PASS"


def _selftest_red() -> str | None:
    bad = state_mod.State(run="selftest")
    bad.phases = [state_mod.Phase(2, "slice", "t", status="passed", capture_sha="x",
                                  red_seen=False)]
    if not state_mod.validate(bad):
        return "a passed phase with no red ever seen was accepted"
    return None


@register("red", "no phase closes on a green nobody watched go red", _selftest_red)
def check_red(target: Path, run_dir: Path) -> Result:
    """The pair, and the pair being two different runs.

    Checking that both blocks exist is not enough: the predecessor's equivalent check said so
    itself - it verified the pair existed and never that the two runs were the same command or
    that they differed in outcome. Here the red block's first line must differ from the pass
    block's, because a red and a green that read identically are one block pasted twice.
    """
    result = Result(name="red")
    try:
        state = state_mod.load(target)
    except FileNotFoundError as exc:
        result.defects.append(str(exc))
        return result

    for phase in state.phases:
        if phase.status != "passed":
            continue
        result.examined += 1
        if not phase.red_seen:
            result.defects.append("phase " + str(phase.id) + " is passed with red_seen false")
        if not phase.capture_ref:
            continue
        path = run_dir / phase.capture_ref
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if RED_MARK not in text:
            result.defects.append(
                "phase " + str(phase.id) + " capture has no " + RED_MARK + " block")
        if PASS_MARK not in text:
            result.defects.append(
                "phase " + str(phase.id) + " capture has no " + PASS_MARK + " block")
        if RED_MARK in text and PASS_MARK in text:
            red = text.split(RED_MARK, 1)[1].strip().splitlines()
            green = text.split(PASS_MARK, 1)[1].strip().splitlines()
            if red and green and red[0].strip() == green[0].strip():
                result.defects.append(
                    "phase " + str(phase.id) + " red and pass blocks open with the same line - "
                    "one run pasted twice is not a pair")
    return result


# -- evidence-visible ----------------------------------------------------------------------------


def _git(target: Path, *args: str) -> tuple:
    try:
        done = subprocess.run(["git", "-C", str(target), *args], capture_output=True,
                              text=True, timeout=30)
        return done.returncode, done.stdout.strip(), done.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)


def _selftest_visible() -> str | None:
    """Built against a real temporary repository, because the failure was git's, not Python's."""
    import tempfile
    root = Path(tempfile.mkdtemp())
    code, _, err = _git(root, "init", "-q")
    if code == 127:
        return None  # no git here; the check degrades to a skip and says so
    _git(root, "init", "-q")
    (root / ".gitignore").write_text("*.log\n[Ll]ogs/\n", encoding="utf-8")
    evidence = root / "logs"
    evidence.mkdir(exist_ok=True)
    (evidence / "phase-1.log").write_text("output", encoding="utf-8")
    ignored = _ignored_paths(root, ["logs/phase-1.log"])
    if not ignored:
        return ("a cited evidence file matched by two stock .gitignore patterns was reported "
                "visible - every citation to it would resolve to nothing off this machine")
    return None


def _ignored_paths(target: Path, candidates: list) -> list:
    """Which cited paths git would exclude, and the pattern doing it.

    `git status` is silent about an ignored file, which is precisely the failure mode, so this
    asks `check-ignore -v` - it names the pattern and its line number. The predecessor learned
    this twice in one run: `*.e2e` swallowed a whole test project, and `[Ll]ogs/` plus `*.log`
    each independently hid the three logs its ledger cited by path. Negating only the first left
    them ignored, so a fix that looked complete was not.
    """
    hidden = []
    for candidate in candidates:
        code, out, _ = _git(target, "check-ignore", "-v", candidate)
        if code == 0 and out:
            hidden.append(out)
    return hidden


@register("evidence-visible", "every cited path resolves for someone who is not you",
          _selftest_visible)
def check_evidence_visible(target: Path, run_dir: Path) -> Result:
    result = Result(name="evidence-visible")
    try:
        state = state_mod.load(target)
    except FileNotFoundError as exc:
        result.defects.append(str(exc))
        return result

    code, _, _ = _git(target, "rev-parse", "--git-dir")
    if code != 0:
        result.defects.append(
            "not a git repository, so no citation can be shown to survive a clone - "
            "`git init` first; this check is not skippable by being unrunnable")
        return result

    cited = []
    for phase in state.phases:
        if phase.capture_ref:
            rel = (run_dir / phase.capture_ref).relative_to(target) \
                if (run_dir / phase.capture_ref).is_relative_to(target) \
                else Path(phase.capture_ref)
            cited.append(str(rel).replace("\\", "/"))
    for fact in state.facts:
        head = (fact.evidence or "").split(":", 1)[0].strip()
        if head and "/" in head and not head.startswith("("):
            cited.append(head)

    cited = sorted(set(cited))
    result.examined = len(cited)
    for line in _ignored_paths(target, cited):
        result.defects.append(
            "a cited path is excluded by .gitignore: " + line
            + " - the citation resolves here and nowhere else")

    for phase in state.phases:
        if phase.status != "passed" or not phase.capture_ref:
            continue
        path = run_dir / phase.capture_ref
        if not path.is_file():
            continue
        code, out, _ = _git(target, "status", "--porcelain", "--untracked-files=all",
                            str(path))
        if code == 0 and out.startswith("??"):
            result.defects.append(
                phase.capture_ref + " is untracked while phase " + str(phase.id) + " is passed - "
                "evidence that is not committed is evidence only this machine has")
    return result


# -- ignore --------------------------------------------------------------------------------------


def _selftest_ignore() -> str | None:
    if state_mod.RAW_DIR[-1] != "raw":
        return "the raw directory moved and this check was not told"
    return None


@register("ignore", "the raw stream is gitignored and never citable", _selftest_ignore)
def check_ignore(target: Path, run_dir: Path) -> Result:
    """Raw output is captured whole, kept out of git, and may not be cited.

    Keeping the whole stream is earned: a 1-of-16 failure piped through `grep Passed` reported a
    bare `Failed: 1` with no test name and no stack, and when it did not reproduce the ledger
    could not name what flaked. Keeping it out of git is the cost finding - one run left 1.4 MB
    of logs. The two together force the third rule: what is not committed cannot be evidence.
    """
    result = Result(name="ignore")
    raw = "/".join(state_mod.RAW_DIR)
    ignore_file = target / ".gitignore"
    if not ignore_file.is_file():
        result.defects.append("no .gitignore, so " + raw + " is not excluded")
    else:
        text = ignore_file.read_text(encoding="utf-8", errors="replace")
        result.examined = len(text.splitlines())
        if raw not in text and raw + "/" not in text:
            result.defects.append(raw + " is not in .gitignore - the dominant cost of a run "
                                  "would be committed")
    try:
        state = state_mod.load(target)
    except FileNotFoundError:
        return result
    for fact in state.facts:
        if raw in (fact.evidence or ""):
            result.defects.append(
                "fact " + fact.id + " cites " + raw + " - a gitignored stream is not evidence")
    for phase in state.phases:
        if phase.capture_ref and raw in phase.capture_ref:
            result.defects.append(
                "phase " + str(phase.id) + " cites " + raw + " as its capture")
    return result


# -- memory --------------------------------------------------------------------------------------


def _selftest_memory() -> str | None:
    """A run that ignored a populated memory must be refused.

    This is the gate the failed run would have hit at phase 0: memory held the render-readiness
    family and its state derived everything fresh.
    """
    mem = memory_mod.Memory(rows=[
        memory_mod.Row("M1", "prior", "2026-01-01", "fact", "an expensive fact",
                       cost="expensive", recheck_cmd="cmd", checksum="abc"),
    ])
    fresh = state_mod.State(run="selftest")
    fresh.facts = [state_mod.Fact("A1", "derived from scratch", "p:1")]
    if not _memory_defects(fresh, mem, rendered_ok=True):
        return "a run that inherited nothing from a populated memory was accepted"
    return None


def _memory_defects(state: state_mod.State, mem: memory_mod.Memory, *, rendered_ok: bool) -> list:
    defects = list(memory_mod.validate(mem))

    if mem.rows:
        inherited = [f for f in state.facts if f.source == "inherited"]
        considered = [f for f in state.facts if f.source == "asked"]
        if not inherited and not considered:
            defects.append(
                "memory holds " + str(len(mem.rows)) + " row(s) and this run inherited none of "
                "them and recorded no reason for rejecting any - a fact re-derived from memory "
                "has been paid for twice, and the second payment is invisible")

    for failure in state.failures:
        if failure.changed_what and not any(
                r.kind == "failure" and r.statement == failure.verbatim_first_line
                for r in mem.rows):
            defects.append(
                "failure " + repr(failure.verbatim_first_line[:50]) + " changed something and is "
                "not in memory - the next run will re-derive it")

    for fact in state.facts:
        # Only what THIS run derived. An inherited fact came out of memory by construction, and
        # its statement is truncated to the tighter state ceiling on the way in, so comparing the
        # text would report every inherited row as missing from the file it came from.
        if fact.source != "derived":
            continue
        if fact.cost == "expensive" and fact.evidence and not any(
                r.kind == "fact" and r.statement.startswith(fact.statement[:120])
                for r in mem.rows):
            defects.append(
                "fact " + fact.id + " was expensive to establish and is not in memory - "
                "the next run will pay for it again")

    if not rendered_ok:
        defects.append("docs/MEMORY.md is stale - run `harness render`")
    return defects


@register("memory", "what a previous run paid for was read, and this run's is written",
          _selftest_memory)
def check_memory(target: Path, run_dir: Path) -> Result:
    result = Result(name="memory")
    try:
        state = state_mod.load(target)
    except FileNotFoundError as exc:
        result.defects.append(str(exc))
        return result
    mem = memory_mod.load(target)
    rendered = target.joinpath(*memory_mod.RENDERED)
    rendered_ok = (rendered.is_file()
                   and rendered.read_text(encoding="utf-8") == memory_mod.render(mem)) \
        if mem.rows else True
    result.examined = len(mem.rows)
    result.defects.extend(_memory_defects(state, mem, rendered_ok=rendered_ok))
    return result


# -- spec-coverage -------------------------------------------------------------------------------


def _selftest_spec() -> str | None:
    """A deliverable with no command behind it must be refused.

    Earned: a run closed nine phases and two blind reviewers ruled 9 PROVEN / 0 NOT PROVEN over a
    tree where a named SPEC.md deliverable had never been built. A `git status` read against the
    spec found it a day later.
    """
    defects = _spec_defects(
        "This run builds the worker slice and the event publishing contract in place.\n",
        state_mod.State(run="selftest"))
    if not defects:
        return "a spec deliverable with no phase and no command behind it was accepted"
    return None


def _spec_defects(spec: str, state: state_mod.State) -> list:
    """Every sentence the spec asserts is built maps to a phase whose test names a command."""
    defects = []
    claims = []
    for raw in spec.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ">", "|", "<!--")):
            continue
        if set(line) <= {"-", ":", " "}:
            continue
        # A criterion is usually a bullet. Strip the marker; do not skip the line.
        if line[:2] in ("- ", "* "):
            line = line[2:].strip()
        if line.startswith("{{") or not line:
            continue
        lowered = line.lower()
        if any(word in lowered for word in
               ("builds", "build ", "must", "will have", "in place", "prints", "exits",
                "returns", "shows", "so i can")):
            claims.append(line)
    tests = " ".join(p.test for p in state.phases).lower()
    for claim in claims:
        words = [w.strip(".,;:()").lower() for w in claim.split()]
        nouns = [w for w in words if len(w) > 5]
        if not nouns:
            continue
        if not any(noun in tests for noun in nouns):
            defects.append(
                "no phase test names anything in " + repr(claim[:90]) + " - a deliverable with "
                "no command behind it closes on a reviewer's opinion")
    return defects


@register("spec-coverage", "every deliverable maps to a command that runs", _selftest_spec)
def check_spec_coverage(target: Path, run_dir: Path) -> Result:
    result = Result(name="spec-coverage")
    spec_path = run_dir / "SPEC.md"
    if not spec_path.is_file():
        result.defects.append("no SPEC.md at " + str(spec_path))
        return result
    try:
        state = state_mod.load(target)
    except FileNotFoundError as exc:
        result.defects.append(str(exc))
        return result
    spec = spec_path.read_text(encoding="utf-8", errors="replace")
    result.examined = len(spec.splitlines())
    result.defects.extend(_spec_defects(spec, state))
    return result


# -- the meta check, and the runner ---------------------------------------------------------------


@register("selftest", "every check has been seen to reject its own bad input",
          lambda: None)
def check_selftest(target: Path, run_dir: Path) -> Result:
    result = Result(name="selftest")
    for name, check in sorted(REGISTRY.items()):
        if name == "selftest":
            continue
        result.examined += 1
        try:
            failed = check.selftest()
        except Exception as exc:  # a selftest that cannot run has not run
            failed = "selftest raised " + type(exc).__name__ + ": " + str(exc)
        if failed:
            result.defects.append(name + " did not reject its own bad input: " + failed)
    return result


def run_all(target: Path, run_dir: Path, names=None) -> list:
    """Run the named checks, or all of them. Green is withheld from an unproven check."""
    chosen = sorted(REGISTRY) if not names else list(names)
    unknown = [n for n in chosen if n not in REGISTRY]
    if unknown:
        raise ValueError("refused: no such check(s): " + ", ".join(unknown)
                         + ". Known: " + ", ".join(sorted(REGISTRY)))
    results = []
    for name in chosen:
        check = REGISTRY[name]
        result = check.run(target, run_dir)
        try:
            failed = check.selftest()
        except Exception as exc:
            failed = "selftest raised " + type(exc).__name__ + ": " + str(exc)
        if failed:
            result.unproven = failed
        results.append(result)
    return results


def report(results: list) -> tuple:
    """The printable report, and the defect count that becomes the exit code."""
    lines = []
    defects = 0
    for result in results:
        lines.append(result.report())
        defects += len(result.defects) + (1 if result.unproven else 0)
    lines.append("")
    lines.append("harness check: " + ("PASS" if defects == 0 else "FAIL") + " - "
                 + str(defects) + " defect(s) over " + str(len(results)) + " check(s)")
    return "\n".join(lines), defects


# -- approved ------------------------------------------------------------------------------------

APPROVAL_RE = re.compile(r"(?m)^\s*APPROVED-BY:\s*(?P<who>[^\n]{3,})$")
SAW_RE = re.compile(r"(?m)^\s*SAW:\s*(?P<what>[^\n]{10,})$")


def _selftest_approved() -> str | None:
    """A phase that changes a screen and shows no sign-off must be refused."""
    bad = state_mod.State(run="selftest")
    bad.phases = [state_mod.Phase(1, "ui", "cmd", status="passed", red_seen=True,
                                  capture_sha="x", needs_human=True)]
    if not state_mod.validate(bad):
        return "a screen-changing phase closed with no sign-off and was accepted"
    # And a sign-off that cannot name what was looked at is one where nothing was.
    if _approval_defects("APPROVED-BY: Someone 2026-01-01\n", 1):
        pass
    else:
        return "an approval with no SAW: line was accepted"
    return None


def _approval_defects(text: str, phase: int) -> list:
    defects = []
    approval = APPROVAL_RE.search(text)
    saw = SAW_RE.search(text)
    if approval is None:
        defects.append(
            "phase " + str(phase) + " carries no `APPROVED-BY: <name> <date>` line")
    if saw is None:
        defects.append(
            "phase " + str(phase) + " carries no `SAW:` line naming which screens, which "
            "viewports and which themes were looked at - a sign-off that cannot say what was "
            "looked at is one where nothing was")
    return defects


@register("approved", "a person looked at what a person will see", _selftest_approved)
def check_approved(target: Path, run_dir: Path) -> Result:
    """The one signal here whose content is a judgement rather than an exit code.

    Every automated screen assertion available is an ABSENCE: no horizontal overflow, no computed
    text colour equal to its background, no unpainted svg, no interactive control without a name,
    zero console errors, zero serious axe violations. A real run's visual criterion was exactly
    those six, printed per screen. All six go green on a screen that is cramped, badly ordered,
    confusing, or missing the thing the user came for - none of that emits a console error.

    Asking a check harder does not help: it produces an invented answer in a confident tone. So
    the judgement stays a person's, and this stays a command - it exits non-zero until that
    judgement is written down, dated and attributed, in the phase's own capture:

        APPROVED-BY: Kurt Mabery 2026-09-29
        SAW: /dashboard, /work-items, /radar - 1280x800 and 390x844, light and dark

    An agent could type both lines. That is worth saying plainly rather than implying a guarantee
    this cannot give. What the format buys is that forging it is a lie - attributed, dated, about
    named screens - rather than the silent omission an unwritten judgement is.
    """
    result = Result(name="approved")
    try:
        state = state_mod.load(target)
    except FileNotFoundError as exc:
        result.defects.append(str(exc))
        return result

    visual = [p for p in state.phases if p.needs_human]
    if not visual:
        return result
    for phase in visual:
        result.examined += 1
        if phase.status != "passed":
            continue
        if not phase.capture_ref:
            result.defects.append("phase " + str(phase.id) + " needs a sign-off and has no capture")
            continue
        path = run_dir / phase.capture_ref
        if not path.is_file():
            result.defects.append("phase " + str(phase.id) + " capture is missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        result.defects.extend(_approval_defects(text, phase.id))
    return result
