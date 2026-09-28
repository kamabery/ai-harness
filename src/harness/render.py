"""Rendering — token substitution and block splicing, with one definition of what a token is.

`TOKEN_RE` is that definition. Both readers of it — the scaffolder's post-render scan and the
render check — import it from here rather than each carrying a copy. docs/CONTROLS.md, *The token
contract*, records why: three copies kept in step by a comment diverged anyway, and a comment is
not a mechanism.
"""

from __future__ import annotations

import re
from pathlib import Path

#: The single definition of a scaffold token. A survivor in any rendered file is a defect, with no
#: advisory tier — it means the scaffolder did not have the value and wrote a placeholder where a
#: fact belongs.
TOKEN_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")


def surviving_tokens(text: str) -> list[str]:
    """Every token left in a rendered text, in order, without duplicates."""
    seen: list[str] = []
    for token in TOKEN_RE.findall(text):
        if token not in seen:
            seen.append(token)
    return seen


def substitute(text: str, values: dict[str, str]) -> str:
    """Replace `{{NAME}}` with values[NAME].

    Unknown tokens are left alone rather than blanked. A blanked token is invisible; a surviving one
    is caught by the post-render scan and refuses the whole render, which is the intended behaviour
    for a value the scaffolder did not have.
    """
    def replace(match: re.Match) -> str:
        key = match.group(0)[2:-2]
        return values.get(key, match.group(0))

    return TOKEN_RE.sub(replace, text)


def splice(text: str, region: str, body: str) -> str:
    """Replace the content between `<!-- REGION:BEGIN -->` and `<!-- REGION:END -->`.

    The markers stay. They are what makes a rendered document diffable against the template it came
    from, and what lets a later phase add a row in the right place.
    """
    pattern = re.compile(
        rf"(<!--\s*{re.escape(region)}:BEGIN\s*-->\n).*?(<!--\s*{re.escape(region)}:END\s*-->)",
        re.S,
    )
    if not pattern.search(text):
        raise ValueError(f"refused: no {region}:BEGIN/END region to splice into")

    body = body.rstrip("\n") + "\n"
    return pattern.sub(lambda m: m.group(1) + body + m.group(2), text)


def render(template: Path, values: dict[str, str], regions: dict[str, str] | None = None) -> str:
    """Render one template: splice its regions, then substitute its tokens.

    Regions first, deliberately. A spliced block carries tokens of its own — a phase pack's ledger
    rows name `{{PHASE_README}}` and the rest — and substituting before splicing would leave those
    unresolved in the very text the scan is about to reject.
    """
    text = template.read_text(encoding="utf-8")
    for region, body in (regions or {}).items():
        text = splice(text, region, body)
    return substitute(text, values)
