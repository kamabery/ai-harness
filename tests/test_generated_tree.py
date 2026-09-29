"""Detection against the tree `template-projects` actually emits.

Found by examining that generator: a scaffolded solution is `.slnx`, and its MAUI head declares
`<TargetFrameworks>` (plural). The dotnet pack matched neither, so the solution file was invisible
to detection and the MAUI head's framework was never recorded at all - a `net9.0-android` would
have passed unseen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import detect, packs

FIXTURE = Path(__file__).parent / "fixtures" / "aspire-generated"


@pytest.fixture(scope="module")
def found():
    return detect.detect(FIXTURE)


def test_the_solution_file_is_seen(found):
    """A .slnx is a solution. `**/*.sln` does not match it."""
    evidence = " ".join(f.evidence for f in found.facts)
    assert ".slnx" in evidence, "the generated solution file was invisible to detection"


def test_the_single_target_framework_is_recorded(found):
    values = [f.value for f in found.facts if f.name == "target framework"]
    assert "net10.0" in values


def test_a_platform_suffixed_multi_target_is_recorded(found):
    """The MAUI head's frameworks must appear as a fact, not vanish."""
    values = " ".join(f.value for f in found.facts if f.name == "target framework")
    assert "net10.0-android" in values, "the MAUI head's frameworks were never recorded"


def test_a_platform_suffixed_net10_is_not_a_conflict(found):
    """net10.0-android IS .NET 10. Flagging it would be noise, and noise is worse than nothing."""
    names = [c.found for c in found.conflicts]
    assert not any("net10.0-android" in n for n in names), (
        "a legitimate MAUI multi-target was reported as a conflict: " + str(names))


def test_an_older_platform_target_is_still_a_conflict(tmp_path):
    """The rule is 'net10 and nothing earlier' - a net9 head must still be caught."""
    proj = tmp_path / "src" / "Old.Maui"
    proj.mkdir(parents=True)
    (proj / "Old.Maui.csproj").write_text(
        "<Project><PropertyGroup><TargetFrameworks>net9.0-android</TargetFrameworks>"
        "</PropertyGroup></Project>", encoding="utf-8")
    (tmp_path / "Old.slnx").write_text("<Solution />", encoding="utf-8")
    result = detect.detect(tmp_path)
    assert any("net9.0-android" in c.found for c in result.conflicts), (
        "an out-of-policy framework passed undetected")
