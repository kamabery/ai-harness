"""Read what the predecessor's workspaces already paid for, without trusting any of it.

Two workspaces and three runs exist under the old harness. Their archives and lesson ledgers hold
facts that cost a build, a browser, or an enumeration to establish, and failures whose cheaper
observable was written down. That is worth carrying. What is not worth carrying is the belief
that any of it is still true.

So nothing imported arrives as a signal. An imported fact whose archive named a command comes in
as `expensive` with that command, and the inherit gate will re-run it before a phase leans on it.
An imported fact with no recoverable command comes in as `cheap` with no command at all, which in
this harness means *always re-derive* - the archive is a lead, and a lead is not a status. The old
harness said exactly that about its own detection rows and then let its assumption table fill up
with them, which is the mistake being avoided here rather than repeated.

Failures import with their cheaper observable, because that column is the only part of a lesson
the next run can act on. A failure row with no cheaper observable is refused by
`memory.validate` - a lesson that names no cheaper way to have caught it is a story.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import memory as memory_mod

#: A markdown table row, split on unescaped pipes.
_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
#: A command worth re-running, as the old ledgers wrote them: inside backticks.
_CMD = re.compile(r"`([^`]{4,120})`")
#: A lesson id in the old ledger.
_LESSON_ID = re.compile(r"^L#\d+$")


def _cells(line: str) -> list:
    match = _ROW.match(line)
    if not match:
        return []
    return [c.strip() for c in match.group(1).split("|")]


def _is_rule(cells: list) -> bool:
    return all(set(c) <= {"-", ":"} and c for c in cells)


def tables(text: str) -> list:
    """Every markdown table in a document, as a list of row-lists."""
    found = []
    current = []
    for line in text.splitlines():
        cells = _cells(line)
        if cells:
            if not _is_rule(cells):
                current.append(cells)
        elif current:
            found.append(current)
            current = []
    if current:
        found.append(current)
    return found


def _command_in(*texts: str) -> str | None:
    for text in texts:
        for candidate in _CMD.findall(text or ""):
            if any(candidate.startswith(p) for p in
                   ("dotnet", "pwsh", "npm", "git", "uv ", "python", "aspire", "docker", "psql")):
                return candidate
    return None


def from_lessons(path: Path, run: str, date: str, start: int) -> list:
    """Failure rows out of a LESSONS.md lesson ledger.

    The old shape is six columns - id, the mechanism, the evidence, the cheaper observable, the
    phase it was carried into, and a status - and a workspace's LESSONS.md holds several tables
    keyed the same way. Only the six-column one is the ledger: the four-column table that follows
    it records which later phase used a lesson, so importing that too would double every row.
    The discriminator is the column count plus an `L#` id, because both tables say "Lesson".
    """
    rows = []
    text = path.read_text(encoding="utf-8", errors="replace")
    number = start
    seen = set()
    for table in tables(text):
        for cells in table:
            if len(cells) < 6 or not _LESSON_ID.match(cells[0]):
                continue
            mechanism, observable = cells[1], cells[3]
            if not observable or observable.strip("-— ") == "":
                continue
            if cells[0] in seen:
                continue
            seen.add(cells[0])
            rows.append(memory_mod.Row(
                id="M" + str(number), run=run, date=date, kind="failure",
                statement=mechanism[:900], evidence=path.name + " " + cells[0],
                mechanism=mechanism[:900], cheaper_observable=observable[:900]))
            number += 1
    return rows


def from_archive(path: Path, run: str, date: str, start: int) -> list:
    """Fact rows out of a docs/BUILD-HISTORY/<run>.md archive.

    Three columns: the fact, the value it settled on, and what confirmed it. The third is the
    only one that makes the row evidence rather than an assertion, so a row without it is not
    imported at all.
    """
    rows = []
    text = path.read_text(encoding="utf-8", errors="replace")
    number = start
    for table in tables(text):
        header = [c.lower() for c in table[0]]
        if not any(("fact" in c or "assumption" in c) for c in header):
            continue
        for cells in table[1:]:
            if len(cells) < 3:
                continue
            statement, value, confirmed = cells[0], cells[1], cells[2]
            if not statement or not confirmed or statement.lower().startswith("fact"):
                continue
            command = _command_in(confirmed, value)
            rows.append(memory_mod.Row(
                id="M" + str(number), run=run, date=date, kind="fact",
                statement=(statement + " -> " + value)[:900],
                evidence=path.name + " | " + confirmed[:200],
                # A command recovered from the archive can be re-run, so the gate may inherit it.
                # Without one this is a lead: cheap means re-derive, every time.
                cost="expensive" if command else "cheap",
                recheck_cmd=command, checksum=None))
            number += 1
    return rows


def scan(workspace: Path) -> tuple:
    """Every importable document in an old workspace, and the rows they yield."""
    rows = []
    notes = []
    number = 1

    for archive in sorted((workspace / "docs" / "BUILD-HISTORY").glob("*.md")):
        found = from_archive(archive, archive.stem, "imported", number)
        number += len(found)
        rows += found
        notes.append(str(archive.relative_to(workspace)) + ": " + str(len(found)) + " fact(s)")

    for lessons in sorted((workspace / "runs").glob("*/LESSONS.md")):
        run = lessons.parent.name
        found = from_lessons(lessons, run, "imported", number)
        number += len(found)
        rows += found
        notes.append(str(lessons.relative_to(workspace)) + ": " + str(len(found)) + " failure(s)")

    return rows, notes


def into(target: Path, workspace: Path) -> tuple:
    """Import one old workspace's memory into `target`, de-duplicating by statement."""
    memory = memory_mod.load(target)
    known = {(r.run, r.statement) for r in memory.rows}
    rows, notes = scan(workspace)
    added = 0
    for row in rows:
        if (row.run, row.statement) in known:
            continue
        row.id = memory.next_id()
        memory.rows.append(row)
        known.add((row.run, row.statement))
        added += 1
    return memory, notes + ["added " + str(added) + " new row(s)"]
