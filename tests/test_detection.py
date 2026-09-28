"""Detection — the evidence, and no writes.

These read as requirements, and they drive `harness.api` — the surface a skill calls: they assert on
what it reported and what it decided, and on nothing else. A test that reached inside the detector
would be testing the implementation it was meant to hold still.

Ported from the Pester suite this repository started with. Every requirement it held is here.
"""

from __future__ import annotations

import re

from harness import api


def _inventory(path):
    """Every file under a tree, with its size — the before-and-after picture for 'writes nothing'."""
    return sorted(f"{p}|{p.stat().st_size}" for p in path.rglob("*") if p.is_file())


class TestDetect:
    def test_writes_nothing_into_the_workspace_it_inspects(self, dotnet_react):
        before = _inventory(dotnet_react)
        api.detect(dotnet_react)
        assert _inventory(dotnet_react) == before

    def test_names_every_pack_the_workspace_triggers(self, dotnet_react):
        result = api.detect(dotnet_react)
        for pack in ("generic", "dotnet", "typescript", "react", "wolverine", "dapr"):
            assert re.search(rf"(?m)^\s*{pack}\b", result.out), f"{pack} was not named\n{result.out}"

    def test_does_not_trigger_a_pack_the_workspace_has_no_evidence_for(self, dotnet_react):
        result = api.detect(dotnet_react)
        # This tree is React. There is no .razor file and no Blazor package reference in it, and
        # the two UI choices are mutually exclusive in practice.
        triggered = result.out.split("packs with no evidence here")[0]
        assert not re.search(r"(?m)^\s*blazor\b", triggered), triggered

    def test_carries_a_file_and_line_evidence_reference_for_every_detected_fact(
        self, dotnet_react
    ):
        result = api.detect(dotnet_react)
        rows = result.rows(containing="DETECTED")
        assert rows, "no DETECTED rows at all — the check cannot pass vacuously"
        for row in rows:
            assert re.search(r"\S+:\d+", row), f"no path:line evidence in: {row}"
            # Relative, so the table means the same thing on another machine.
            assert str(dotnet_react) not in row, f"absolute path in evidence: {row}"

    def test_reads_the_target_framework_out_of_the_csproj_rather_than_assuming_one(
        self, dotnet_react
    ):
        result = api.detect(dotnet_react)
        assert "net10.0" in result.out
        assert re.search(r"Ledger\.Api\.csproj:\d+", result.out)

    def test_reports_a_build_or_test_command_as_unresolved_never_as_a_detected_fact(
        self, dotnet_react
    ):
        # Nothing is a command until it has been watched producing output. detect never runs one.
        result = api.detect(dotnet_react)
        rows = [r for r in result.rows() if re.search(r"(?i)\bcommand\b", r)]
        assert rows, "no command rows at all — the check cannot pass vacuously"
        for row in rows:
            assert "UNRESOLVED" in row, f"a command was reported as settled: {row}"

    def test_prints_the_count_of_unresolved_facts_and_exits_3_while_any_remain(
        self, dotnet_react
    ):
        result = api.detect(dotnet_react)
        assert re.search(r"(?m)^UNRESOLVED:\s*[1-9]\d*\b", result.out), result.out
        assert result.code == 3

    def test_cannot_pass_vacuously_because_it_prints_how_many_facts_it_examined(
        self, dotnet_react
    ):
        result = api.detect(dotnet_react)
        assert re.search(r"(?m)^examined [1-9]\d* facts?\b", result.out), result.out

    def test_detects_the_other_ui_choice_and_not_the_first(self, dotnet_blazor):
        result = api.detect(dotnet_blazor)
        triggered = result.out.split("packs with no evidence here")[0]
        for present in ("dotnet", "blazor"):
            assert re.search(rf"(?m)^\s*{present}\b", triggered), f"{present} missing\n{triggered}"
        for absent in ("react", "typescript", "wolverine", "dapr"):
            assert not re.search(rf"(?m)^\s*{absent}\b", triggered), f"{absent} fired\n{triggered}"

    def test_a_pack_whose_requirement_is_absent_does_not_fire(self, tmp_path):
        # blazor requires dotnet. A stray .razor file with no project around it is not a Blazor
        # workspace, and firing on it would put a hook in a tree that cannot run it.
        stray = tmp_path / "stray"
        stray.mkdir()
        (stray / "Orphan.razor").write_text("<h1>hello</h1>", encoding="utf-8")
        result = api.detect(stray)
        triggered = result.out.split("packs with no evidence here")[0]
        assert not re.search(r"(?m)^\s*blazor\b", triggered), triggered
        assert re.search(r"(?m)^\s*generic\b", triggered), triggered

    def test_the_always_on_pack_applies_to_a_workspace_with_nothing_in_it(
        self, empty_workspace
    ):
        result = api.detect(empty_workspace)
        triggered = result.out.split("packs with no evidence here")[0]
        assert re.search(r"(?m)^\s*generic\b", triggered), triggered
        for absent in ("dotnet", "blazor", "react", "typescript", "wolverine", "dapr"):
            assert not re.search(rf"(?m)^\s*{absent}\b", triggered), f"{absent} fired\n{triggered}"

    def test_reports_the_facts_structured_as_well_as_written_out(self, dotnet_react):
        data = api.detect(dotnet_react).data
        assert data["examined"] == len(data["facts"])
        assert data["unresolved"] > 0
        assert "dotnet" in data["packs"]


class TestConflictsWithWhatIsAlreadySettled:
    """A value contradicting a commitment already made is a finding, not an open question."""

    def test_reports_a_target_framework_below_the_one_this_organisation_builds_on(
        self, dotnet_blazor
    ):
        result = api.detect(dotnet_blazor)
        assert re.search(r"(?m)^CONFLICTS:\s*[1-9]\d*\b", result.out), result.out
        assert "net9.0" in result.out and "net10.0" in result.out

    def test_a_conflict_carries_the_file_and_line_that_evidences_it(self, dotnet_blazor):
        result = api.detect(dotnet_blazor)
        line = next(l for l in result.out.splitlines() if "net9.0" in l and "net10.0" in l)
        assert re.search(r"Ledger\.Web\.csproj:\d+", line), line

    def test_a_conforming_tree_reports_no_conflict(self, dotnet_react):
        result = api.detect(dotnet_react)
        assert re.search(r"(?m)^CONFLICTS:\s*0\b", result.out), result.out

    def test_a_conflict_is_not_a_status_on_a_fact(self, dotnet_blazor):
        # The table keeps two statuses and no third. A conflict is reported beside it, because it is
        # not something a Phase 0 row could settle by running anything.
        result = api.detect(dotnet_blazor)
        for row in result.rows():
            assert "CONFLICT" not in row, row

    def test_reports_conflicts_structured_as_well_as_written_out(self, dotnet_blazor):
        data = api.detect(dotnet_blazor).data
        assert len(data["conflicts"]) == 1
        assert data["conflicts"][0]["found"] == "net9.0"
        assert data["conflicts"][0]["expected"] == "net10.0"


class TestRefusals:
    def test_refuses_with_no_target_rather_than_defaulting_to_the_current_directory(self):
        result = api.detect()
        assert result.code == 1
        assert "refused" in result.out

    def test_refuses_a_target_that_is_not_a_directory(self, dotnet_react):
        result = api.detect(dotnet_react / "no-such-tree")
        assert result.code == 1
        assert "refused" in result.out


class TestListPacks:
    def test_lists_every_pack_in_tech_packs_with_what_triggers_it(self):
        result = api.list_packs()
        assert result.code == 0
        for pack in ("generic", "dotnet", "blazor", "react", "typescript", "wolverine", "dapr"):
            assert re.search(rf"(?m)^\s*{pack}\b", result.out), f"{pack} missing\n{result.out}"

    def test_offers_no_pack_for_a_technology_this_organisation_does_not_use(self):
        result = api.list_packs()
        for gone in ("java", "angular"):
            assert not re.search(rf"(?m)^\s*{gone}\b", result.out), f"{gone} is still offered"

    def test_says_what_each_pack_requires(self):
        result = api.list_packs()
        assert re.search(r"(?m)^\s*blazor\b.*requires: dotnet", result.out), result.out
        assert re.search(r"(?m)^\s*wolverine\b.*requires: dotnet", result.out), result.out

    def test_there_is_exactly_one_run_shape_and_a_pack_does_not_multiply_it(self):
        """The predecessor had two run shapes across seven packs and ran 10 to 13 phases.

        Seven of those produced no product code. One shape, four fixed phases, and the slices
        between them - a pack says what a tree is built with, never how many phases that costs.
        """
        result = api.list_packs()
        assert result.ok
        assert "one run shape" in result.out
        assert "does not multiply the phases" in result.out
        assert not hasattr(api, "list_run_shapes")

        from harness.api import CLOSING_PHASE, FIXED_PHASES
        assert [name for _, name, _ in FIXED_PHASES] == ["preflight", "baseline"]
        assert CLOSING_PHASE[0] == "reconcile"
