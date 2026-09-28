"""The guardrail checks — what `ARCHITECTURE.md` forbids, and whether anything watches for it.

This module exists because of a specific, observed failure. A workspace whose `ARCHITECTURE.md`
named six rules a run may not break shipped with checks for **two** of them — and the two were the
local, single-file-scan rules. Every rule that defined the architecture itself (no service reads
another service's database, no service calls another's HTTP API, only the owning persona may write
a field) got nothing. Nothing anywhere reported the gap, so the next run inherited an architecture
that was documented, cited in reviews, and unenforced. Its Phase 2 then re-ran the *design* check
under the name "the guardrail check", and closed green.

The failure was not laziness: that run kept real checks in its tree and its plan was meticulous. It
was that **writing a check per rule was a prompt, and nothing ever counted the rules against the
checks.** So this module does exactly two things the prose could not:

1. **It runs the declared checks**, as processes, and reports each one's exit code. A guardrail
   whose check nobody can invoke is a guardrail with a check nobody has ever run.
2. **It counts coverage, and names the uncovered rules every single time.** An unchecked rule is
   not a defect — sometimes no static check is possible and an integration test is the honest
   answer — but it must be *declared* unchecked, with a reason, and it is reprinted on every run so
   it cannot fade into the background the way those four did.

What it deliberately does not do is read `ARCHITECTURE.md` for structure. That file is the
workspace's own prose, copied byte for byte, and `check_render` refuses to impose headings on it for
the same reason. The rules are **transcribed** into `docs/guards.json` by the initial run, and the
only tie back to the prose is that each transcribed rule must still appear in it verbatim — which
catches a rule invented here, and a rule amended there and forgotten here.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

from .dotnet_guards import BUILTINS as _STRUCTURAL
from .ui_guards import UI_BUILTINS as _UI

#: Every shipped guard, structural and visual, under one namespace.
BUILTINS = {**_STRUCTURAL, **_UI}
from pathlib import Path

#: Where the transcribed rules live. Authored by the initial run's guardrail phase.
GUARDS_FILE = ("docs", "guards.json")

#: How long any one guardrail check may take before it is reported as a defect rather than waited
#: on. A check that hangs is a check that stops being run.
TIMEOUT_SECONDS = 300

#: Written out rather than escaped inline, so a report string cannot be broken by a stray editor.
NEWLINE = chr(10)


class GuardsError(Exception):
    """A refusal: the declaration is missing or malformed. Nothing was run."""


@dataclass
class Rule:
    """One rule from `ARCHITECTURE.md`, and whatever watches for it."""

    rule: str
    check: str | None = None
    unchecked_because: str = ""
    #: Filled in by `run_guards`; None where the rule declares no check.
    exit_code: int | None = None
    output: str = ""

    @property
    def is_checked(self) -> bool:
        return bool(self.check)

    @property
    def failed(self) -> bool:
        return self.exit_code is not None and self.exit_code != 0


BUILTIN_PREFIX = "builtin:"

#: A declared reason that is really a deferral. The workspace that prompted this module shipped
#: six of ten rules behind "TODO - no check written yet": an unenforced rule wearing an exemption,
#: which every later run inherits as though somebody enforced it. A genuine reason ("the only
#: observable is an integration test we do not run here") still exempts a rule. These do not.
PLACEHOLDER_REASONS = ("todo", "tbd", "fixme", "no check written", "not written yet",
                       "later", "wip", "xxx", "none", "n/a", "-")


def is_placeholder(reason: str) -> bool:
    """Is this reason a deferral dressed as an explanation?"""
    text = (reason or "").strip().lower()
    if not text:
        return True
    return any(mark in text for mark in PLACEHOLDER_REASONS)



@dataclass
class GuardResult:
    """What the guardrail pass examined, and every defect it found."""

    name: str = "guards"
    rules: list[Rule] = field(default_factory=list)
    defects: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.defects

    @property
    def examined(self) -> int:
        return len(self.rules)

    @property
    def checked(self) -> int:
        return sum(1 for r in self.rules if r.is_checked)

    @property
    def uncovered(self) -> list[Rule]:
        return [r for r in self.rules if not r.is_checked]

    def report(self) -> str:
        lines: list[str] = []

        for rule in self.rules:
            if not rule.is_checked:
                verdict = "UNCHECKED"
            elif rule.failed:
                verdict = f"FAIL({rule.exit_code})"
            else:
                verdict = "pass"
            lines.append(f"  {verdict:<10} {_short(rule.rule)}")

        # The uncovered rules are reprinted, always, even when nothing is wrong. This is the whole
        # point of the module: the four rules that went unchecked in the run that prompted it were
        # never *denied*, they were simply never mentioned again.
        if self.uncovered:
            lines.append("")
            lines.append(
                f"  {len(self.uncovered)} rule(s) have no check. Each is declared unchecked, with a "
                "reason — they are listed here every run so the list cannot go quiet:"
            )
            for rule in self.uncovered:
                lines.append(f"    - {' '.join(rule.rule.split())}")
                lines.append(
                    f"      because: {rule.unchecked_because}" if rule.unchecked_because
                    else "      because: — NO REASON GIVEN"
                )

        for defect in self.defects:
            lines.append(f"  DEFECT  {defect}")
        for advisory in self.advisories:
            lines.append(f"  advisory {advisory}")

        verdict = "PASS" if self.passed else "FAIL"
        lines.append(
            f"ai-dlc check (guards): {verdict} — {len(self.defects)} defect(s), "
            f"examined {self.examined} rule(s), {self.checked} checked, "
            f"{len(self.uncovered)} unchecked"
        )
        return "\n".join(lines)


def _short(text: str, width: int = 78) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


def load_declaration(target: Path) -> tuple[list[Rule], dict[str, str]]:
    """Read the transcribed rules, refusing rather than treating an absent file as zero rules.

    Zero rules and no file are different facts, and only one of them is a workspace that decided
    something. A missing declaration is refused; a declaration holding an empty list is a defect
    reported by `run_guards`, because a workspace whose `ARCHITECTURE.md` forbids nothing has not
    written guardrails.
    """
    path = target.joinpath(*GUARDS_FILE)
    if not path.is_file():
        raise GuardsError(
            f"refused: no {'/'.join(GUARDS_FILE)} at {path}. The guardrail phase transcribes every "
            "rule in ARCHITECTURE.md into it, each with the check that watches for it or the reason "
            "there is none. Without it nothing counts the rules against the checks, which is how an "
            "architecture ends up documented and unenforced."
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GuardsError(f"refused: {path} is not valid JSON — {error}") from error

    if not isinstance(document, dict) or not isinstance(document.get("rules"), list):
        raise GuardsError(f"refused: {path} must be an object with a 'rules' array")

    services = document.get("services") or {}
    if not isinstance(services, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in services.items()
    ):
        raise GuardsError(f"refused: {path} 'services' must map a service name to its directory")

    rules: list[Rule] = []
    for index, entry in enumerate(document["rules"]):
        if not isinstance(entry, dict) or not str(entry.get("rule", "")).strip():
            raise GuardsError(f"refused: {path} rule #{index + 1} names no rule")
        rules.append(
            Rule(
                rule=str(entry["rule"]).strip(),
                check=(str(entry["check"]).strip() or None) if entry.get("check") else None,
                unchecked_because=str(entry.get("unchecked_because", "")).strip(),
            )
        )
    return rules, services


def _run_check(command: str, cwd: Path) -> tuple[int, str]:
    """Run one guardrail check as a process, from the workspace root.

    As a process, and not as a function call, for the reason `harness.gate` gives: a reviewer who was
    not in the session has to be able to re-run it, and its exit code is the verdict.

    It is handed to the **shell, exactly as written**, because that is what it is — the same command
    line a person types and `gate.command()` renders. Splitting it into an argv array first was the
    original implementation here and it was wrong in the most dangerous available way: on Windows,
    `shlex.split(..., posix=False)` keeps the outer quotes, so `pwsh -Command "...; exit 1"` reached
    pwsh as a quoted *string literal*, which it evaluated, echoed and exited **0** for. The check
    reported `pass`. A check that cannot fail and a check that passed print the same thing, which is
    the failure this whole package exists to catch — found here by running a check that was supposed
    to go red and watching it come back green.
    """
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return 127, f"the check could not be run — no such command: {command}"
    except subprocess.TimeoutExpired:
        return 124, f"the check did not finish within {TIMEOUT_SECONDS}s: {command}"
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def run_guards(target: Path, *, execute: bool = True) -> GuardResult:
    """Run every declared guardrail check and report coverage over the rules.

    `execute=False` reports coverage without running anything, which is what a scaffold-time or
    read-only caller wants. The coverage half is the half that caught the failure this module was
    written for; the execution half is what makes a green mean something.
    """
    result = GuardResult()
    result.rules, services = load_declaration(target)

    for rule in result.rules:
        if rule.check and rule.check.startswith(BUILTIN_PREFIX):
            name = rule.check[len(BUILTIN_PREFIX):]
            if name not in BUILTINS:
                raise GuardsError(
                    f"refused: no builtin guard {name!r}. Available: {', '.join(sorted(BUILTINS))}. "
                    "A name that does not resolve would otherwise be a check that never ran."
                )
            if not services:
                raise GuardsError(
                    f"refused: {rule.check} needs a 'services' block in docs/guards.json saying "
                    "where each service's directory is. A boundary check with no boundaries "
                    "declared passes over every tree."
                )

    if not result.rules:
        result.defects.append(
            "docs/guards.json declares no rules — a workspace whose architecture forbids nothing "
            "has not written guardrails"
        )
        return result

    architecture = target / "docs" / "ARCHITECTURE.md"
    prose = architecture.read_text(encoding="utf-8") if architecture.is_file() else None
    if prose is None:
        result.defects.append("docs/ARCHITECTURE.md is missing — the rules transcribe from nothing")

    unexplained: list[Rule] = []

    for rule in result.rules:
        # Each transcribed rule must still be in the prose. This is the only tie between the two
        # files, and it is deliberately a substring test rather than a schema: it catches a rule
        # invented here and a rule amended there, without imposing structure on a document that is
        # the workspace's own words.
        if prose is not None and _normalise(rule.rule) not in _normalise(prose):
            result.defects.append(
                f"guards.json names a rule that is not in ARCHITECTURE.md: {_short(rule.rule)}"
            )

        if not rule.is_checked:
            if rule.unchecked_because and is_placeholder(rule.unchecked_because):
                result.defects.append(
                    "rule " + _short(rule.rule, 60) + " is declared unchecked because "
                    + repr(rule.unchecked_because.strip()) + ", which defers the work rather "
                    "than explaining it - write the check or write the real reason")
            if not rule.unchecked_because:
                unexplained.append(rule)
            continue

        if not execute:
            continue

        if (rule.check or "").startswith(BUILTIN_PREFIX):
            report = BUILTINS[rule.check[len(BUILTIN_PREFIX):]](target, services)
            rule.exit_code, rule.output = report.code, report.output
        else:
            rule.exit_code, rule.output = _run_check(rule.check or "", target)
        if rule.failed:
            # The last line is the verdict - a builtin ends with its violation count, and most
            # checks end with their summary. Showing the *first* line reported a passing service
            # under a FAIL heading, which is worse than showing nothing.
            body = [l.strip() for l in rule.output.splitlines() if l.strip()]
            shown = list(dict.fromkeys(body[-1:] + body[:3])) if body else []
            result.defects.append(
                f"guardrail check failed (exit {rule.exit_code}) for: {_short(rule.rule)}"
                + NEWLINE + f"            $ {rule.check}"
                + "".join(NEWLINE + "            " + l[:150] for l in shown)
            )

    if unexplained:
        # One defect, naming them all. An unchecked rule is allowed — sometimes an integration test
        # is the honest answer — but the reason is what separates "no static check is possible" from
        # "nobody got to it", and only the first is a decision.
        result.defects.append(
            f"{len(unexplained)} rule(s) have neither a check nor a reason for having none:"
            + "".join(
                NEWLINE + f"            - {' '.join(r.rule.split())}" for r in unexplained
            )
            + NEWLINE
            + "            An unchecked rule is allowed; an unexplained one is how seven of "
            "nine went quiet in the workspace that prompted this check."
        )

    if result.checked == 0:
        result.defects.append(
            f"none of the {len(result.rules)} rule(s) has a check — every one is declared "
            "unchecked, which is an architecture nothing in this tree can notice being broken"
        )
    elif result.uncovered and result.checked < len(result.rules) / 2:
        # Advisory, not a defect: the honest answer is sometimes an integration test. But the run
        # that prompted this module had 2 of 6, and nobody said so.
        result.advisories.append(
            f"only {result.checked} of {len(result.rules)} rules have a check. The rules that go "
            "unchecked are usually the structural ones, because they are the hardest to write a "
            "check for and the most expensive to get wrong."
        )

    return result


def _normalise(text: str) -> str:
    """Compare on words alone, so wrapping, bullets and emphasis do not decide the match."""
    return " ".join(text.replace("*", "").replace("`", "").replace("-", " ").split()).casefold()
