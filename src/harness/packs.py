"""Tech packs — what a workspace is built with, read from `tech-packs/*/pack.json`.

Phase packs and hooks were deliberately dropped: the run shape is fixed (0 preflight,
1 baseline, 2..N slices, N+1 reconcile), so there is nothing for a pack to multiply.
Detection survives because a `path:line` behind every claimed fact is what makes a
`DETECTED:` row a lead rather than an assertion.

Originally: Loading the two kinds of pack.

**Tech packs** answer *what is this workspace built with*. **Phase packs** answer *what shape does
this run take*. They are orthogonal on purpose: detection contributes assumption rows, hooks and
evidence; the lifecycle contributes phases. Mixing them is how a pack ends up asserting that a
.NET workspace must have eight phases.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .assets import asset_dir


@dataclass(frozen=True)
class Trigger:
    """One reason a tech pack applies, and the evidence it would leave."""

    glob: str
    fact: str
    contains: str | None = None

    @classmethod
    def from_json(cls, data: dict) -> "Trigger":
        return cls(glob=data["glob"], fact=data.get("fact", ""), contains=data.get("contains"))

    def describe(self) -> str:
        return f"{self.glob} containing {self.contains!r}" if self.contains else self.glob


@dataclass(frozen=True)
class FactRule:
    """A value a pack can read out of a file — a lead, never a confirmation.

    ``capture`` names a regex whose first group is the value. ``value`` names a constant used when
    the file's mere existence is the fact. Exactly one of the two is meaningful.
    """

    name: str
    glob: str
    fact: str
    capture: str | None = None
    value: str | None = None
    contains: str | None = None
    #: The only value this organisation accepts. A captured value that is not this one is reported
    #: as a **conflict** rather than recorded as a fact — see detect.Detection.conflicts.
    expect: str | None = None
    #: A regex every item of a multi-valued capture must match, where exact equality
    #: would be wrong. A .NET MAUI head declares `net10.0-android;net10.0-ios`: each
    #: item is .NET 10 and none equals "net10.0", so exact comparison reports a
    #: conflict that is not one. Noise sent to a developer is worse than no finding at
    #: all, so the pack says how to compare rather than the detector guessing. Items
    #: are split on `;`. When set this decides; `expect` stays the readable statement.
    expect_each: str | None = None

    @classmethod
    def from_json(cls, data: dict) -> "FactRule":
        return cls(
            name=data["name"],
            glob=data["glob"],
            fact=data.get("fact", ""),
            capture=data.get("capture"),
            value=data.get("value"),
            contains=data.get("contains"),
            expect=data.get("expect"),
            expect_each=data.get("expect_each"),
        )

    @property
    def pattern(self) -> re.Pattern | None:
        return re.compile(self.capture) if self.capture else None


@dataclass(frozen=True)
class TechPack:
    """One technology this workspace may be built with, and what follows from that."""

    name: str
    description: str
    requires: tuple[str, ...]
    always: bool
    triggers: tuple[Trigger, ...]
    facts: tuple[FactRule, ...]
    commands: tuple[str, ...]
    assumptions: str

    @property
    def trigger_summary(self) -> str:
        if self.always:
            return "always"
        return ", ".join(t.describe() for t in self.triggers) or "—"


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_tech_pack(directory: Path) -> TechPack:
    """Load one tech pack from its directory.

    A pack whose ``pack.json`` names something other than its own directory is refused. The name is
    how every other file refers to it — a `requires:` entry, a `--pack` argument, a row in
    PLUMBING.md — so a pack answering to two names is a pack that resolves inconsistently.
    """
    manifest = directory / "pack.json"
    if not manifest.is_file():
        raise FileNotFoundError(f"refused: {directory.name} has no pack.json")

    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("name") != directory.name:
        raise ValueError(
            f"refused: {manifest} names the pack {data.get('name')!r} "
            f"but sits in {directory.name!r}"
        )

    assumptions_file = directory / "assumptions.md"

    return TechPack(
        name=data["name"],
        description=data.get("description", ""),
        requires=tuple(data.get("requires", ())),
        always=bool(data.get("always", False)),
        triggers=tuple(Trigger.from_json(t) for t in data.get("triggers", ())),
        facts=tuple(FactRule.from_json(f) for f in data.get("facts", ())),
        commands=tuple(data.get("commands", ())),
        assumptions=(
            assumptions_file.read_text(encoding="utf-8") if assumptions_file.is_file() else ""
        ),
    )


def load_tech_packs(root: Path | None = None) -> dict[str, TechPack]:
    """Load every tech pack, and refuse the set if any `requires:` names a pack that does not exist.

    Validated as a set rather than one at a time: a dangling requirement is only visible from the
    whole collection, and it fails at detection time — quietly, by contributing nothing — rather
    than at load time where somebody would see it.
    """
    root = root or asset_dir("tech-packs")
    packs = {
        d.name: load_tech_pack(d)
        for d in sorted(root.iterdir())
        if d.is_dir() and not d.name.startswith("_")
    }
    for pack in packs.values():
        for required in pack.requires:
            if required not in packs:
                raise ValueError(
                    f"refused: tech pack {pack.name!r} requires {required!r}, which does not exist"
                )
    return packs


# --- phase packs ------------------------------------------------------------------------------
#
# A phase pack is markdown with four delimited blocks the scaffolder splices into PLAN.md and
# LOOP-STATE.md. Nothing parses the prose around them: that is written for whoever reads the pack.
