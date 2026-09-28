"""Where the markdown lives.

Everything ai-dlc emits comes from four directories of markdown and JSON. Finding them is one
question with two answers — a checkout, or an installed wheel — and it is asked in exactly one
place so a future third answer is one edit rather than a search.
"""

from __future__ import annotations

from pathlib import Path

#: Directories that ship with the package and are copied or rendered into a target.
ASSET_DIRS = ("docs", "templates", "phase-packs", "tech-packs", "skills", "design-packs")


def asset_root() -> Path:
    """Return the directory holding docs/, templates/, phase-packs/, tech-packs/ and skills/.

    Two layouts, checked in order:

    1. **An installed wheel** — the directories are packaged under ``harness/_assets/``.
    2. **A checkout** — they sit at the repository root, two levels above this file.

    Refuses rather than guessing. A wrong asset root produces a scaffold that looks complete and is
    built from somebody else's templates, which is the failure this whole system exists to prevent,
    arriving through the door marked convenience.
    """
    packaged = Path(__file__).resolve().parent / "_assets"
    if (packaged / "templates").is_dir():
        return packaged

    checkout = Path(__file__).resolve().parents[2]
    if (checkout / "templates").is_dir():
        return checkout

    raise FileNotFoundError(
        "refused: cannot find the ai-dlc assets (docs/, templates/, phase-packs/, tech-packs/). "
        f"Looked in {packaged} and {checkout}."
    )


def asset_dir(name: str) -> Path:
    """Return one asset directory by name, refusing if it is missing."""
    if name not in ASSET_DIRS:
        raise ValueError(f"refused: {name!r} is not an ai-dlc asset directory")
    path = asset_root() / name
    if not path.is_dir():
        raise FileNotFoundError(f"refused: the ai-dlc assets are incomplete — no {name}/ at {path}")
    return path
