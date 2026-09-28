"""Shared fixtures.

The suite drives `harness.api` and asserts on the two fields an `Outcome` carries — what it reported
and what it decided — and on nothing else. `docs/TESTING.md` owns the reason: those two *are* the
contract, because the surface an agent calls is the only surface there is. A test that reached past
`out` and `code` into the implementation would be testing the implementation it was meant to hold
still.

This used to run the CLI out of process, back when there was one. The boundary moved when the
front door became a skill; what is asserted did not.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from harness import api

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@dataclass(frozen=True)
class Ran:
    """One out-of-process run of a gate: what it printed and what it exited with."""

    out: str
    code: int


@pytest.fixture(scope="session")
def run_gate():
    """Invoke an `harness.gate` call the way whatever runs it will.

    The gates are the only calls in this package that are commands, so they are the only ones the
    suite still runs as a process — a phase test and a hook are both handed to a shell, and a gate
    that exits 0 in-process but cannot be invoked is a gate nothing would notice was broken.

    With the source tree on the path, so the suite runs against the working tree rather than
    against whatever happens to be installed. An installed copy going stale is the way a green
    suite stops describing the code in front of you.
    """
    import os

    def invoke(script: str, cwd: Path | None = None, stdin: str | None = None) -> Ran:
        # `stdin` because a hook is handed its tool call as JSON on standard input — so a hook body
        # exercised without one is being run in a shape nothing will ever run it in.
        completed = subprocess.run(
            [sys.executable, "-c", script],
            input=stdin or "",
            capture_output=True,
            text=True,
            cwd=str(cwd or REPO),
            env={**os.environ, "PYTHONPATH": str(REPO / "src"), "PYTHONIOENCODING": "utf-8"},
        )
        return Ran(out=completed.stdout + completed.stderr, code=completed.returncode)

    return invoke


@pytest.fixture(scope="session")
def dotnet_react() -> Path:
    """A conforming workspace: .NET 10, React, TypeScript, Wolverine and Dapr. No Blazor."""
    return FIXTURES / "dotnet-react"


@pytest.fixture(scope="session")
def dotnet_blazor() -> Path:
    """A Blazor workspace that deliberately targets net9.0.

    It carries the conflict on purpose: this organisation builds on .NET 10, so a tree pinned lower
    is something detection has to say out loud rather than record as a fact.
    """
    return FIXTURES / "dotnet-blazor"


@pytest.fixture(scope="session")
def empty_workspace() -> Path:
    """A tree with nothing in it but a note. Only the always-on pack should apply."""
    return FIXTURES / "empty"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """An empty directory to scaffold into, thrown away after each test."""
    target = tmp_path / "ledger-sync"
    target.mkdir()
    return target


@pytest.fixture
def authored_spec(tmp_path: Path) -> Path:
    """A filled-in spec, copied so a test that mangles it cannot affect another."""
    destination = tmp_path / "SPEC.md"
    shutil.copyfile(FIXTURES / "specs" / "SPEC.md", destination)
    return destination


@pytest.fixture
def authored_architecture(tmp_path: Path) -> Path:
    """A filled-in set of guardrails."""
    destination = tmp_path / "ARCHITECTURE.md"
    shutil.copyfile(FIXTURES / "specs" / "ARCHITECTURE.md", destination)
    return destination


@pytest.fixture
def scaffolded(workspace, authored_spec, authored_architecture):
    """A workspace that has had its initial run scaffolded into it.

    Asserts the scaffold succeeded before handing it over: a test that fails five assertions later
    because setup quietly failed is a test that reports the wrong thing.
    """
    result = api.initial_run(workspace, authored_spec, authored_architecture)
    assert result.code == 0, result.out
    return workspace
