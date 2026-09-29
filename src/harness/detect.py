"""Detection — read the workspace, name what it is built with, and prove every claim.

Three rules, and each is here because the alternative is a table that reads authoritative and is
partly invented:

1. **It writes nothing.** Detection is an observation. A detector that also fixes things cannot be
   run on a tree you do not own yet.
2. **Every DETECTED fact carries `path:line`**, relative to the workspace so the table is portable.
   A fact with no evidence is a guess wearing a status, and three sessions later the two are the
   same row.
3. **A command is never a detected fact.** Reading a manifest executes nothing: a `scripts.build`
   entry, a CI job name and a README line are three claims about a command, and all three drift.
   Every command comes back `UNRESOLVED` no matter how obvious it looks.

**And it stays small on purpose.** The technology choices are already applied to the workspace by
the time this runs, so there is nothing here to decide — only to confirm, loudly enough that the
run's *architectural* choices are made against the right tree. Detection exists to answer three
questions and no more: which packs apply, which section 1 rows and hooks follow from them, and
whether anything in the tree **conflicts with a commitment this organisation has already made**.
A survey of everything readable would be effort spent where no decision is pending.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .packs import TechPack, load_tech_packs

#: Directories that are build output or vendored dependencies. Scanning them is slow and produces
#: evidence pointing at generated files, which is worse than slow.
SKIP_DIRS = {
    ".git", ".vs", ".idea", ".venv", "venv", "__pycache__", "node_modules",
    "bin", "obj", "dist", "build", "out", "target", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "packages", ".next", ".nuxt", ".angular",
}

#: Refuse to read anything huge. A 40MB lockfile has nothing to say that its first megabyte did not.
MAX_READ_BYTES = 2 * 1024 * 1024

DETECTED = "DETECTED"
UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class Conflict:
    """A value in the tree that contradicts a commitment already made.

    Not a status on a fact — a **finding**. `net9.0` in a workspace committed to .NET 10 is not an
    open question a Phase 0 row could settle by running something; it is a thing that is wrong now
    and will be inherited by every run in this tree until somebody changes it.
    """

    name: str
    found: str
    expected: str
    evidence: str

    def __str__(self) -> str:
        return f"{self.name} is {self.found}, and this organisation builds on {self.expected} ({self.evidence})"


@dataclass(frozen=True)
class Fact:
    """One row of the detection table.

    ``status`` is DETECTED or UNRESOLVED and there is no third value. DETECTED means *a file said
    so* — it is a lead, and it becomes a fact only when a §1 row carries captured output behind it.
    """

    pack: str
    name: str
    value: str
    status: str
    evidence: str
    note: str = ""

    @property
    def is_unresolved(self) -> bool:
        return self.status == UNRESOLVED


def _walk(root: Path):
    """Yield every file under root, skipping build output and vendored trees."""
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def _read(path: Path) -> str | None:
    """Read a file as text, or None if it is too big or not text at all."""
    try:
        if path.stat().st_size > MAX_READ_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _matches(path: Path, root: Path, pattern: str) -> bool:
    """Match a pack's glob against a workspace-relative path.

    ``Path.match`` does not treat a leading ``**/`` as "at any depth including the root", which is
    exactly what a pack means by it, so that case is handled explicitly.
    """
    rel = path.relative_to(root)
    if pattern.startswith("**/"):
        return rel.match(pattern) or rel.match(pattern[3:])
    return rel.match(pattern)


def _rel(path: Path, root: Path, line: int) -> str:
    """Evidence, as `<workspace-relative path>:<line>` with forward slashes.

    Relative and forward-slashed so the table means the same thing on another machine. An absolute
    path in a committed document is evidence nobody else can follow.
    """
    return f"{path.relative_to(root).as_posix()}:{line}"


def _line_of(text: str, needle: str) -> int:
    """The 1-based line a substring first appears on, or 1 if it does not."""
    index = text.find(needle)
    if index < 0:
        return 1
    return text.count("\n", 0, index) + 1


def triggered_packs(root: Path, packs: dict[str, TechPack]) -> dict[str, str]:
    """Return {pack name: evidence} for every pack this workspace has evidence for.

    A pack whose `requires:` is unsatisfied is dropped: `blazor` without `dotnet` would be a
    claim about a stack that does not exist. Dropping happens after all direct triggers are
    resolved, so ordering in the directory does not change the answer.
    """
    found: dict[str, str] = {}

    for pack in packs.values():
        if pack.always:
            found[pack.name] = "always applies"

    files = list(_walk(root))
    for pack in packs.values():
        if pack.name in found:
            continue
        for trigger in pack.triggers:
            for path in files:
                if not _matches(path, root, trigger.glob):
                    continue
                if trigger.contains is None:
                    found[pack.name] = _rel(path, root, 1)
                    break
                text = _read(path)
                if text and trigger.contains in text:
                    found[pack.name] = _rel(path, root, _line_of(text, trigger.contains))
                    break
            if pack.name in found:
                break

    # Drop anything whose requirements are not present. Repeat until stable: a pack can require a
    # pack that was itself dropped.
    changed = True
    while changed:
        changed = False
        for name in list(found):
            for required in packs[name].requires:
                if required not in found:
                    del found[name]
                    changed = True
                    break

    return found



def _contradicts(rule, found: str) -> bool:
    """Does a captured value contradict what this organisation settled on?

    `expect_each` decides when present: every item of a multi-valued capture must match it, which
    is how `net10.0-android;net10.0-ios` stays a fact rather than becoming a conflict while
    `net9.0-android` still becomes one. Without it, exact equality against `expect`.
    """
    if rule.expect_each:
        items = [i.strip() for i in found.split(";") if i.strip()]
        return not items or any(re.match(rule.expect_each, i) is None for i in items)
    return rule.expect is not None and found != rule.expect


def collect_facts(
    root: Path, packs: dict[str, TechPack], active: dict[str, str]
) -> tuple[list[Fact], list[Conflict]]:
    """Every fact the active packs can read, the conflicts they raise, and the commands none may claim.

    The command rows are appended last and always `UNRESOLVED`. They are the rows a plan invents
    rather than asking, and they are the reason this function cannot return an all-green table.
    """
    facts: list[Fact] = []
    conflicts: list[Conflict] = []
    files = list(_walk(root))

    for name in sorted(active):
        pack = packs[name]

        # An always-on pack contributes no "in use" row. Its presence is a property of ai-dlc's
        # configuration, not a fact about this tree, and a DETECTED row with nothing behind it is
        # exactly the shape this table exists to make impossible.
        if not pack.always:
            facts.append(
                Fact(
                    pack=name,
                    name=f"{name} in use",
                    value=name,
                    status=DETECTED,
                    evidence=active[name],
                    note=pack.description,
                )
            )

        for rule in pack.facts:
            for path in sorted(files):
                if not _matches(path, root, rule.glob):
                    continue

                if rule.value is not None and rule.capture is None:
                    facts.append(
                        Fact(pack=name, name=rule.name, value=rule.value, status=DETECTED,
                             evidence=_rel(path, root, 1), note=rule.fact)
                    )
                    continue

                text = _read(path)
                if text is None:
                    continue
                if rule.contains and rule.contains not in text:
                    continue

                pattern = rule.pattern
                if pattern is None:
                    facts.append(
                        Fact(pack=name, name=rule.name, value=rule.fact or "present",
                             status=DETECTED, evidence=_rel(path, root, 1), note=rule.fact)
                    )
                    continue

                match = pattern.search(text)
                if match:
                    line = text.count("\n", 0, match.start()) + 1
                    found = match.group(1)
                    evidence = _rel(path, root, line)
                    # A value that contradicts a commitment already made is a finding, not a fact
                    # with a worse status: no Phase 0 row settles it by running anything.
                    if _contradicts(rule, found):
                        conflicts.append(
                            Conflict(name=rule.name, found=found, expected=rule.expect,
                                     evidence=evidence)
                        )
                    facts.append(
                        Fact(pack=name, name=rule.name, value=found,
                             status=DETECTED, evidence=evidence, note=rule.fact)
                    )

    # Commands. Never detected, however plainly a manifest declares them.
    seen: set[str] = set()
    for name in sorted(active):
        for command in packs[name].commands:
            label = f"`{command}` command"
            if label in seen:
                continue
            seen.add(label)
            facts.append(
                Fact(pack=name, name=label, value=UNRESOLVED, status=UNRESOLVED, evidence="—",
                     note="nothing is a command until it has been watched producing output")
            )

    for label, note in (
        ("test count command", "how many tests the test command executes — the count, not the exit code"),
        ("red-channel command", "whether the test command can report a failure at all"),
        ("log stream", "where this code's own output goes, and whether the tests can read it"),
    ):
        facts.append(
            Fact(pack="generic", name=label, value=UNRESOLVED, status=UNRESOLVED, evidence="—",
                 note=note)
        )

    return facts, conflicts


@dataclass(frozen=True)
class Detection:
    """The whole result of looking at a workspace, and nothing that required running anything."""

    root: Path
    packs: dict[str, TechPack]
    active: dict[str, str]
    facts: list[Fact]
    conflicts: list[Conflict]

    @property
    def clean(self) -> bool:
        """Nothing open and nothing wrong. Both have to be true."""
        return not self.unresolved and not self.conflicts

    @property
    def unresolved(self) -> list[Fact]:
        return [f for f in self.facts if f.is_unresolved]

    @property
    def examined(self) -> int:
        return len(self.facts)


def detect(root: Path, packs: dict[str, TechPack] | None = None) -> Detection:
    """Inspect a workspace. Reads files; runs nothing; writes nothing."""
    packs = packs or load_tech_packs()
    active = triggered_packs(root, packs)
    facts, conflicts = collect_facts(root, packs, active)
    return Detection(root=root, packs=packs, active=active, facts=facts, conflicts=conflicts)


def format_table(detection: Detection) -> str:
    """The detection table, as the markdown that goes into `docs/PLUMBING.md`."""
    lines = [
        "| Pack | Fact | Value | Status | Evidence |",
        "|---|---|---|---|---|",
    ]
    for fact in detection.facts:
        lines.append(
            f"| {fact.pack} | {fact.name} | {fact.value} | {fact.status} | {fact.evidence} |"
        )
    return "\n".join(lines)


def format_report(detection: Detection) -> str:
    """The human-readable report `ai-dlc detect` prints. stdout is the contract; keep it stable."""
    out = [f"workspace: {detection.root}", "", "packs triggered:"]
    for name in sorted(detection.active):
        out.append(f"  {name:<12} {detection.active[name]}")

    inactive = sorted(set(detection.packs) - set(detection.active))
    if inactive:
        out.append("")
        out.append("packs with no evidence here: " + ", ".join(inactive))

    out += ["", format_table(detection), ""]

    if detection.conflicts:
        out.append("CONFLICTS - the tree contradicts a commitment already made:")
        for conflict in detection.conflicts:
            out.append(f"  {conflict}")
        out.append("")
        out.append(
            "A conflict is not an open question. No Phase 0 row settles it by running "
            "something: it is wrong now, and every run in this tree inherits it until "
            "somebody changes it."
        )
        out.append("")

    out.append(f"examined {detection.examined} facts")
    out.append(f"CONFLICTS: {len(detection.conflicts)}")
    out.append(f"UNRESOLVED: {len(detection.unresolved)}")

    if detection.unresolved:
        out.append("")
        out.append(
            "Every row above marked DETECTED is a lead, not a confirmation: a file said so, and "
            "nothing was run. Each UNRESOLVED row is Phase 0's work, answered with captured output."
        )
    return "\n".join(out)
