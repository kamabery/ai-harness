"""The UI quality guards — the mechanical half of "it should look professionally designed".

Styling is the path of least resistance in every build, and that is a statement about economics
rather than about care. At the moment the first screen is written, composing from a design system
costs more than typing a hex value, so the hex value wins; using the framework's default theme
costs nothing, so the default theme ships; writing an empty state costs a component nobody asked
for, so the list renders blank. Each decision is locally cheapest and the sum is a product that
looks generated.

Two things change that, and only one of them is in this file.

The first is the seed in `design-packs/seed/tokens.css`: a real vocabulary, copied in **before**
the first screen, so that composing from the system becomes the cheap path and a raw value becomes
the deviation. That is the larger lever and it is not a check.

The second is here — the checks that notice the specific tells. They are deliberately mechanical
and they are deliberately not the whole job:

    checkable here                          not checkable, ever, and the prototype gate's job
    ------------------------------------    ------------------------------------------------
    every value resolves to a token         does the hierarchy match the task
    the type scale is the declared one      does it look considered
    contrast meets AA, computed             is the density right for this user
    the framework default theme is gone     is the microcopy any good
    focus-visible exists
    empty / loading / error states exist
    no placeholder copy shipped

`docs/DESIGN.md` owns the doctrine. This file owns what a command can decide about it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .dotnet_guards import IGNORED_DIRS, GuardReport

#: Files that carry markup or styling, whatever the stack.
MARKUP_SUFFIXES = (".css", ".scss", ".razor", ".tsx", ".jsx", ".vue", ".svelte", ".html", ".cshtml")

#: A literal colour anywhere it should not be.
RAW_COLOUR_RE = re.compile(
    r"(?<![\w-])(#[0-9a-fA-F]{3,8}\b|rgba?\s*\([^)]*\)|hsla?\s*\([^)]*\))"
)

#: A literal length. `0` and unitless numbers are fine; a `12px` in a component is not.
RAW_LENGTH_RE = re.compile(r"(?<![\w.-])(\d*\.?\d+)(px|rem|em)\b")

#: Lengths that are never worth flagging: hairlines, and the zero case.
ALLOWED_LENGTHS = {"0px", "1px", "2px", "0rem", "0em", "100px"}

#: Copy a person would never have written on purpose.
PLACEHOLDER_RE = re.compile(
    r"\b(lorem ipsum|dolor sit amet|foo ?bar|Item [0-9]|Row [0-9]|Sample [A-Z]|"
    # TODO and FIXME are matched case-SENSITIVELY, as the code markers they are. Lower-cased,
    # "todo" is an ordinary domain noun — a kanban board has a Todo column — and an earlier version
    # of this guard reported 36 violations in one, every single one of them a legitimate name.
    r"Test [0-9]|(?-i:TODO|FIXME)|Your text here|Lorem)\b",
    re.I,
)

#: `placeholder="..."` is a real attribute and `::placeholder` a real pseudo-element. An earlier
#: version of this guard matched the bare word and fired on both, in a file that had done nothing
#: wrong. A guard that cries wolf is how a whole set gets disabled — docs/CONTROLS.md — so the word
#: counts as placeholder copy only when it is neither of those.
LEGITIMATE_PLACEHOLDER_RE = re.compile(
    r"placeholder\s*=|::placeholder|placeholder-shown", re.I)

#: Framework palettes shipped unchanged. The single clearest signal that the design phase was
#: skipped: each of these is a default nobody chose, and they are exact strings.
FRAMEWORK_DEFAULTS = {
    "#0d6efd": "Bootstrap 5 default primary",
    "#0dcaf0": "Bootstrap 5 default info",
    "#6c757d": "Bootstrap default secondary",
    "#594ae2": "MudBlazor default primary",
    "#ff4081": "MudBlazor default secondary",
    "#1976d2": "MUI default primary",
    "#3f51b5": "Material default indigo",
    "#3b76f6": "the ai-dlc seed accent, unchanged",
    "#2a5ce0": "the ai-dlc seed accent, unchanged",
}

#: The states a data view has to have somewhere. A list with only its happy path is the commonest
#: UX omission in a generated build, and it is invisible to every functional test that seeds data.
REQUIRED_STATES = ("empty", "loading", "error")


def _files(root: Path) -> list[Path]:
    return [
        p for p in root.rglob("*")
        if p.suffix.lower() in MARKUP_SUFFIXES
        and p.is_file()
        and not any(part in IGNORED_DIRS for part in p.parts)
    ]


def _system_files(target: Path, declared) -> set[Path]:
    """The design system's own files, which are where literals are supposed to live.

    The token file always counts. A workspace whose system spans more than one file names them in
    `guards.json` as `design_system`, because a check that flagged the vocabulary for containing
    values would be flagging it for being a vocabulary.
    """
    system: set[Path] = set()
    tokens = _token_file(target, declared)
    if tokens is not None:
        system.add(tokens.resolve())
    for pattern in (declared.get("design_system") or []):
        system.update(p.resolve() for p in target.glob(pattern) if p.is_file())
    return system


def _token_file(target: Path, declared: dict[str, str]) -> Path | None:
    named = declared.get("tokens")
    if named:
        candidate = (target / named).resolve()
        return candidate if candidate.is_file() else None
    for path in _files(target):
        if path.suffix == ".css" and "--" in path.read_text(encoding="utf-8", errors="replace")[:4000]:
            if re.search(r"(?m)^\s*--[\w-]+\s*:", path.read_text(encoding="utf-8", errors="replace")):
                return path
    return None


# -- colour, and whether a person could read it --------------------------------------------------


def _parse_hex(value: str) -> tuple[int, int, int] | None:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) not in (6, 8):
        return None
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return None


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float | None:
    """WCAG 2.1 contrast ratio, or None where either colour is not a literal we can read."""
    fg, bg = _parse_hex(foreground), _parse_hex(background)
    if fg is None or bg is None:
        return None
    light, dark = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _declarations(css: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"(?m)^\s*(--[\w-]+)\s*:\s*([^;]+);", css)}


def _resolve(name: str, declarations: dict[str, str], depth: int = 0) -> str:
    """Follow a token through its var() chain to a literal. Depth-capped against a cycle."""
    value = declarations.get(name, "")
    if depth > 10:
        return ""
    match = re.fullmatch(r"var\(\s*(--[\w-]+)\s*\)", value.strip())
    return _resolve(match.group(1), declarations, depth + 1) if match else value.strip()


#: The role pairs that have to be legible. Foreground, background, and the AA threshold for the
#: kind of text the pair carries.
CONTRAST_PAIRS = (
    ("--fg", "--bg", 4.5),
    ("--fg", "--bg-raised", 4.5),
    ("--fg-muted", "--bg", 4.5),
    ("--fg-subtle", "--bg", 3.0),
    ("--fg-on-accent", "--accent", 4.5),
    ("--border-strong", "--bg", 3.0),
)


def contrast(target: Path, declared: dict[str, str]) -> GuardReport:
    """Every role pair meets AA, computed rather than eyeballed.

    A colour that reads better to the eye lands under the threshold routinely, which is why this is
    arithmetic. 4.5:1 for text, 3:1 for large text and for anything that is only a boundary.
    """
    tokens = _token_file(target, declared)
    if tokens is None:
        return GuardReport(1, "contrast: no token file found — declare it as 'tokens' in guards.json")

    declarations = _declarations(tokens.read_text(encoding="utf-8", errors="replace"))
    lines, violations, checked = [], 0, 0

    for fg_name, bg_name, threshold in CONTRAST_PAIRS:
        fg, bg = _resolve(fg_name, declarations), _resolve(bg_name, declarations)
        ratio = contrast_ratio(fg, bg)
        if ratio is None:
            continue
        checked += 1
        if ratio < threshold:
            violations += 1
            lines.append(
                "  {} on {} is {:.2f}:1, below {}:1 ({} on {})".format(
                    fg_name, bg_name, ratio, threshold, fg, bg))

    lines.append("contrast: {} violation(s) over {} readable pair(s)".format(violations, checked))
    if checked == 0:
        lines.append(
            "  no role pair resolved to a literal colour — nothing was actually measured. This "
            "reads the role names the seed uses ({}). A system naming its roles differently should "
            "map them, or declare this rule unchecked with that as the reason — a contrast check "
            "that silently measures nothing is worse than none.".format(
                ", ".join(sorted({n for pair in CONTRAST_PAIRS for n in pair[:2]}))))
        return GuardReport(1, "\n".join(lines))
    return GuardReport(violations, "\n".join(lines))


# -- the path of least resistance itself ---------------------------------------------------------


def default_theme(target: Path, declared: dict[str, str]) -> GuardReport:
    """No framework's default palette, and no unchanged seed, survives into the product.

    This is the check this module exists for. Every other tell here is a mistake; this one is the
    absence of a decision, and it is the single clearest evidence that the design phase produced a
    document rather than a design. The seed's own accent is on the list deliberately — shipping it
    unchanged is the same omission wearing this package's colours.
    """
    lines, violations = [], 0
    for path in _files(target):
        body = path.read_text(encoding="utf-8", errors="replace")
        for value, what in FRAMEWORK_DEFAULTS.items():
            if value.lower() in body.lower():
                violations += 1
                lines.append("  {} — {}: {}".format(value, what, path.relative_to(target)))

    lines.append("default-theme: {} unchanged default(s) found".format(violations))
    if violations:
        lines.append("  a default palette is not a choice; it is the absence of one")
    return GuardReport(violations, "\n".join(lines))


def raw_values(target: Path, declared: dict[str, str]) -> GuardReport:
    """No literal colour, radius, shadow or spacing step outside the token file.

    A raw colour has exactly one value, so it breaks whichever theme it was not picked for, and a
    literal length drifts the moment one component is restyled. Neither errors, neither warns, and
    no functional test has an opinion.
    """
    system = _system_files(target, declared)
    lines, violations = [], 0

    for path in _files(target):
        if path.resolve() in system:
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        for match in RAW_COLOUR_RE.finditer(body):
            violations += 1
            lines.append("  raw colour {} in {}".format(
                match.group(1)[:32], path.relative_to(target)))
        for match in RAW_LENGTH_RE.finditer(body):
            if (match.group(1) + match.group(2)) in ALLOWED_LENGTHS:
                continue
            violations += 1
            lines.append("  raw length {} in {}".format(
                match.group(0), path.relative_to(target)))

    lines = lines[:40] + (["  ... and more"] if len(lines) > 40 else [])
    lines.append("raw-values: {} literal(s) outside the token file".format(violations))
    return GuardReport(violations, "\n".join(lines))


def focus_visible(target: Path, declared: dict[str, str]) -> GuardReport:
    """A visible keyboard focus style is defined somewhere, and never suppressed without one.

    `outline: none` with nothing replacing it is the single most common accessibility regression in
    a styled build, and it is invisible to anyone testing with a mouse.
    """
    lines, violations = [], 0
    defined = False

    for path in _files(target):
        body = path.read_text(encoding="utf-8", errors="replace")
        if ":focus-visible" in body:
            defined = True
        for match in re.finditer(r"outline\s*:\s*(none|0)\s*[;}]", body):
            window = body[max(0, match.start() - 400): match.end() + 400]
            if ":focus-visible" not in window and "box-shadow" not in window:
                violations += 1
                lines.append("  focus suppressed with nothing replacing it: {}".format(
                    path.relative_to(target)))

    if not defined:
        violations += 1
        lines.append("  no :focus-visible style is defined anywhere")

    lines.append("focus-visible: {} violation(s)".format(violations))
    return GuardReport(violations, "\n".join(lines))


def placeholder_copy(target: Path, declared: dict[str, str]) -> GuardReport:
    """No lorem ipsum, no "Item 1", no TODO shipped as product copy.

    Placeholder copy is the tell that a screen was built to be demonstrated rather than used, and
    it survives because it renders perfectly.
    """
    lines, violations = [], 0
    for path in _files(target):
        body = path.read_text(encoding="utf-8", errors="replace")
        for match in PLACEHOLDER_RE.finditer(body):
            line_start = body.rfind(chr(10), 0, match.start()) + 1
            line_end = body.find(chr(10), match.end())
            line = body[line_start: line_end if line_end != -1 else len(body)]
            if LEGITIMATE_PLACEHOLDER_RE.search(line):
                continue
            violations += 1
            lines.append("  {!r} in {}".format(match.group(0), path.relative_to(target)))
    lines = lines[:30] + (["  ... and more"] if len(lines) > 30 else [])
    lines.append("placeholder-copy: {} placeholder(s) in shipped markup".format(violations))
    return GuardReport(violations, "\n".join(lines))


def view_states(target: Path, declared: dict[str, str]) -> GuardReport:
    """Somewhere in the component set, an empty, a loading and an error state exist.

    A list that renders only its happy path is the commonest omission in a generated build, and it
    is invisible to every functional test — because the test seeds data first. This is a coarse
    check by design: it reads that the vocabulary exists at all, which is the difference between a
    build that thought about it and one that did not.
    """
    corpus = "".join(
        path.read_text(encoding="utf-8", errors="replace").lower() for path in _files(target)
    )
    missing = [state for state in REQUIRED_STATES
               if not re.search(r"\b{}\b".format(state), corpus)]
    lines = ["  no component or markup anywhere names a {} state".format(state)
             for state in missing]
    lines.append("view-states: {} of {} required states present".format(
        len(REQUIRED_STATES) - len(missing), len(REQUIRED_STATES)))
    return GuardReport(len(missing), "\n".join(lines))


#: The guards a `docs/guards.json` rule may name as `builtin:<name>`.
UI_BUILTINS = {
    "ui-contrast": contrast,
    "ui-default-theme": default_theme,
    "ui-raw-values": raw_values,
    "ui-focus-visible": focus_visible,
    "ui-placeholder-copy": placeholder_copy,
    "ui-view-states": view_states,
}
