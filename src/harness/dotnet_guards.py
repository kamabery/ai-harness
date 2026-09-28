"""The shipped structural guards — the rules that go uncovered because they are hard to write.

`guards.py` counts rules against checks. This module exists because counting was never the whole
problem: the rules that went uncovered in the workspace that prompted all of this were uncovered
for a reason. "No domain value that is configuration is a C# enum" is a scan of one file at a time
and a run writes it in ten minutes. "No service reads or writes another service's database" is a
question about the **shape of the tree**, it takes real care to get right, and a run that has to
invent it inside a phase that is also authoring the architecture will skip it — not from laziness,
but because it is the expensive one and nothing was counting.

So these three ship. They are parameterised by the `services` block in `docs/guards.json` — the one
place a workspace says where its boundaries actually are — and a run references them by name rather
than reinventing them::

    {"rule": "...", "check": "builtin:no-cross-service-reference"}

**What is deliberately not shipped here: a cross-service HTTP check.** "No service calls another
service's HTTP API" is not statically decidable — a base address arrives from configuration, a
typed client is registered three layers from where it is used, and every heuristic that catches the
real case also fires on a legitimate one. A gate that fires on something legitimate teaches the next
session to disable the set, and the useful ones go with it (`docs/CONTROLS.md`). That rule stays
`unchecked_because`, named in every report, and handed to the reviewer — which is the honest
position rather than a check that looks like cover.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: A csproj's references to other projects.
PROJECT_REFERENCE_RE = re.compile(r'<ProjectReference\s+Include\s*=\s*"([^"]+)"', re.I)

#: A class declaring itself an EF context. Matches `: DbContext` and `: IdentityDbContext<...>`.
DBCONTEXT_DECL_RE = re.compile(
    r"(?m)^\s*(?:public|internal)?\s*(?:sealed\s+|abstract\s+|partial\s+)*"
    r"class\s+(\w+)\s*:\s*[^{\r\n]*\bDbContext\b"
)

#: Where a .NET host starts. `Program.cs` covers both the classic and top-level-statement shapes.
ENTRYPOINT_NAMES = ("Program.cs",)

#: Directories that are never part of a service's own sources.
IGNORED_DIRS = {"bin", "obj", "node_modules", ".git", ".vs", "TestResults"}


@dataclass(frozen=True)
class GuardReport:
    """One builtin guard's verdict. `code` is the verdict, exactly as a process's would be."""

    code: int
    output: str


def _sources(root: Path, suffix: str) -> list[Path]:
    return [
        p for p in root.rglob("*" + suffix)
        if not any(part in IGNORED_DIRS for part in p.parts)
    ]


def _owning_service(path: Path, services: dict[str, Path]) -> str | None:
    """Which declared service a file belongs to, by longest matching root.

    Longest-match because a nested service root is a legitimate layout, and the shallower one would
    otherwise claim every file under it.
    """
    best: tuple[int, str] | None = None
    for name, root in services.items():
        try:
            path.relative_to(root)
        except ValueError:
            continue
        depth = len(root.parts)
        if best is None or depth > best[0]:
            best = (depth, name)
    return best[1] if best else None


def _resolve_services(target: Path, declared: dict[str, str]) -> tuple[dict[str, Path], list[str]]:
    resolved: dict[str, Path] = {}
    missing: list[str] = []
    for name, relative in declared.items():
        root = (target / relative).resolve()
        if root.is_dir():
            resolved[name] = root
        else:
            missing.append(name + " -> " + relative)
    return resolved, missing


def _missing_note(missing: list[str]) -> list[str]:
    # A declared service whose directory is absent counts as a violation rather than being skipped.
    # Skipping it would let a rule pass by naming a boundary that does not exist.
    return ["  declared service directory does not exist: " + entry for entry in missing]


def no_cross_service_reference(target: Path, declared: dict[str, str]) -> GuardReport:
    """No project inside one service may reference a project inside another.

    A shared project outside every declared service root is fine and is the normal way contracts
    travel. What this refuses is service A compiling service B's code, which is the first step of
    two services becoming one and the step nothing else notices.
    """
    services, missing = _resolve_services(target, declared)
    lines: list[str] = []
    violations = 0

    for csproj in _sources(target, ".csproj"):
        owner = _owning_service(csproj, services)
        if owner is None:
            continue
        body = csproj.read_text(encoding="utf-8", errors="replace")
        for include in PROJECT_REFERENCE_RE.findall(body):
            referenced = (csproj.parent / include.replace("\\", "/")).resolve()
            other = _owning_service(referenced, services)
            if other is not None and other != owner:
                violations += 1
                lines.append(
                    "  {} references {}: {} -> {}".format(
                        owner, other, csproj.relative_to(target), include
                    )
                )

    lines += _missing_note(missing)
    lines.append(
        "no-cross-service-reference: {} violation(s) over {} declared service(s)".format(
            violations, len(services)
        )
    )
    return GuardReport(code=violations + len(missing), output="\n".join(lines))


def one_entrypoint_per_service(target: Path, declared: dict[str, str]) -> GuardReport:
    """Each declared service has exactly one host entrypoint — no more, and no fewer.

    Two boundaries sharing one host is the monolith this rule exists to name. **Zero is a violation
    too**, and it is the one worth having: a service the architecture names and the tree has never
    built reads, from every other check in this package, exactly like a service that is finished.
    """
    services, missing = _resolve_services(target, declared)
    lines: list[str] = []
    violations = 0

    for name, root in sorted(services.items()):
        found = [p for p in _sources(root, ".cs") if p.name in ENTRYPOINT_NAMES]
        if len(found) == 1:
            lines.append("  {}: 1 entrypoint — {}".format(name, found[0].relative_to(target)))
            continue
        violations += 1
        if not found:
            lines.append("  {}: NO entrypoint — this service is named but not built".format(name))
        else:
            lines.append("  {}: {} entrypoints — {}".format(
                name, len(found), ", ".join(str(p.relative_to(target)) for p in found)))

    for entry in missing:
        lines.append("  {}: declared service directory does not exist — not built".format(entry))

    lines.append(
        "one-entrypoint-per-service: {} violation(s) over {} declared service(s)".format(
            violations + len(missing), len(declared)
        )
    )
    return GuardReport(code=violations + len(missing), output="\n".join(lines))


def no_shared_dbcontext(target: Path, declared: dict[str, str]) -> GuardReport:
    """A DbContext declared inside one service is named by no other service's sources.

    Data ownership is the rule that decays first and most quietly: reaching into another service's
    context compiles, passes every test, and is indistinguishable from owning the data — until the
    two services need to deploy separately.
    """
    services, missing = _resolve_services(target, declared)
    lines: list[str] = []
    violations = 0

    owners: dict[str, str] = {}
    for path in _sources(target, ".cs"):
        owner = _owning_service(path, services)
        if owner is None:
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        for context in DBCONTEXT_DECL_RE.findall(body):
            owners.setdefault(context, owner)

    if owners:
        lines.append("  contexts: " + ", ".join(
            "{} ({})".format(c, o) for c, o in sorted(owners.items())))

    word = {c: re.compile(r"\b" + re.escape(c) + r"\b") for c in owners}
    for path in _sources(target, ".cs"):
        user = _owning_service(path, services)
        if user is None:
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        for context, owner in owners.items():
            if user != owner and word[context].search(body):
                violations += 1
                lines.append("  {} names {}'s {}: {}".format(
                    user, owner, context, path.relative_to(target)))

    lines += _missing_note(missing)
    lines.append(
        "no-shared-dbcontext: {} violation(s) over {} context(s) in {} declared service(s)".format(
            violations, len(owners), len(services)
        )
    )
    return GuardReport(code=violations + len(missing), output="\n".join(lines))


#: The guards a `docs/guards.json` rule may name as `builtin:<name>`.
BUILTINS = {
    "no-cross-service-reference": no_cross_service_reference,
    "one-entrypoint-per-service": one_entrypoint_per_service,
    "no-shared-dbcontext": no_shared_dbcontext,
}
