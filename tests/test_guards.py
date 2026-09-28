"""The guardrail pass — does anything in this tree watch for what ARCHITECTURE.md forbids?

These names are requirements. The module they cover exists because a real workspace named nine
rules, shipped checks for two, and nothing anywhere reported the gap.
"""

from __future__ import annotations

import json

import pytest

from harness import api
from harness.guards import GUARDS_FILE, run_guards

ARCHITECTURE = """# ARCHITECTURE

## The rules a run may not break

- No service reads or writes another service's database.
- Every screen is composed from the design system.
- Only the owning persona may write a field.
"""


def write_guards(target, rules):
    path = target.joinpath(*GUARDS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rules": rules}, indent=2), encoding="utf-8")


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ARCHITECTURE.md").write_text(ARCHITECTURE, encoding="utf-8")
    return tmp_path


PASSES = "python -c \"raise SystemExit(0)\""
FAILS = "python -c \"raise SystemExit(1)\""


class TestCoverage:
    def test_a_workspace_with_no_declaration_is_refused_rather_than_read_as_zero_rules(self, workspace):
        outcome = api.guard(workspace)
        assert outcome.refused
        assert "guards.json" in outcome.out

    def test_it_reports_how_many_rules_have_a_check_and_how_many_do_not(self, workspace):
        write_guards(workspace, [
            {"rule": "No service reads or writes another service's database.", "check": PASSES},
            {"rule": "Every screen is composed from the design system.",
             "unchecked_because": "covered by the browser suite"},
        ])
        outcome = api.guard(workspace)
        assert outcome.data["examined"] == 2
        assert outcome.data["checked"] == 1
        assert outcome.data["unchecked"] == ["Every screen is composed from the design system."]

    def test_an_unchecked_rule_is_allowed_when_it_says_why(self, workspace):
        write_guards(workspace, [
            {"rule": "No service reads or writes another service's database.", "check": PASSES},
            {"rule": "Only the owning persona may write a field.",
             "unchecked_because": "enforced by integration tests; no static check is possible"},
        ])
        assert api.guard(workspace).ok

    def test_an_unchecked_rule_with_no_reason_is_a_defect(self, workspace):
        write_guards(workspace, [
            {"rule": "No service reads or writes another service's database.", "check": PASSES},
            {"rule": "Only the owning persona may write a field."},
        ])
        outcome = api.guard(workspace)
        assert not outcome.ok
        assert "neither a check nor a reason" in outcome.out

    def test_every_unchecked_rule_is_named_in_the_report_every_run_even_when_nothing_is_wrong(self, workspace):
        write_guards(workspace, [
            {"rule": "No service reads or writes another service's database.", "check": PASSES},
            {"rule": "Only the owning persona may write a field.",
             "unchecked_because": "enforced by integration tests"},
        ])
        outcome = api.guard(workspace)
        # The failure this module was written for was silence, not a wrong answer.
        assert outcome.ok
        assert "Only the owning persona may write a field." in outcome.out

    def test_a_tree_where_every_rule_is_unchecked_is_a_defect_however_well_explained(self, workspace):
        write_guards(workspace, [
            {"rule": "No service reads or writes another service's database.",
             "unchecked_because": "hard"},
            {"rule": "Only the owning persona may write a field.", "unchecked_because": "hard"},
        ])
        outcome = api.guard(workspace)
        assert not outcome.ok
        assert "none of the" in outcome.out

    def test_declaring_no_rules_at_all_is_a_defect(self, workspace):
        write_guards(workspace, [])
        outcome = api.guard(workspace)
        assert not outcome.ok
        assert "declares no rules" in outcome.out


class TestTheTieToTheProse:
    def test_a_rule_that_is_not_in_architecture_md_is_a_defect(self, workspace):
        write_guards(workspace, [
            {"rule": "Services may share a database when it is convenient.", "check": PASSES},
        ])
        outcome = api.guard(workspace)
        assert not outcome.ok
        assert "not in ARCHITECTURE.md" in outcome.out

    def test_a_rule_is_matched_on_its_words_so_wrapping_and_emphasis_do_not_decide_it(self, workspace):
        write_guards(workspace, [
            {"rule": "No service reads or writes\n  another **service's** database.", "check": PASSES},
        ])
        assert api.guard(workspace).ok


class TestRunningTheChecks:
    def test_a_declared_check_is_run_as_a_process_and_its_exit_code_is_the_verdict(self, workspace):
        write_guards(workspace, [
            {"rule": "No service reads or writes another service's database.", "check": FAILS},
        ])
        outcome = api.guard(workspace)
        assert not outcome.ok
        assert "exit 1" in outcome.out
        assert outcome.data["rules"][0]["exit_code"] == 1

    def test_a_check_quoted_for_a_shell_is_run_by_the_shell_and_can_still_go_red(self, workspace):
        # The original implementation split this into argv and the outer quotes survived, so the
        # interpreter echoed the command and exited 0. A check that cannot fail reads as a pass.
        write_guards(workspace, [
            {"rule": "No service reads or writes another service's database.",
             "check": "python -c \"print('violation found'); raise SystemExit(1)\""},
        ])
        outcome = api.guard(workspace)
        assert not outcome.ok, "a check written with quotes must still be able to report failure"
        assert outcome.data["rules"][0]["exit_code"] == 1

    def test_a_check_that_cannot_be_run_at_all_is_a_defect_not_a_pass(self, workspace):
        write_guards(workspace, [
            {"rule": "No service reads or writes another service's database.",
             "check": "definitely-not-a-real-command-here --please"},
        ])
        assert not api.guard(workspace).ok

    def test_execute_false_reports_coverage_without_running_anything(self, workspace):
        write_guards(workspace, [
            {"rule": "No service reads or writes another service's database.", "check": FAILS},
        ])
        outcome = api.guard(workspace, execute=False)
        assert outcome.ok, "coverage is readable without running the checks"
        assert outcome.data["rules"][0]["exit_code"] is None


class TestRefusals:
    def test_a_declaration_that_is_not_valid_json_is_refused_rather_than_ignored(self, workspace):
        path = workspace.joinpath(*GUARDS_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        assert api.guard(workspace).refused

    def test_a_rule_entry_that_names_no_rule_is_refused(self, workspace):
        write_guards(workspace, [{"check": PASSES}])
        assert api.guard(workspace).refused

    def test_the_code_is_the_defect_count_so_a_phase_can_close_on_it(self, workspace):
        write_guards(workspace, [
            {"rule": "No service reads or writes another service's database.", "check": FAILS},
            {"rule": "Every screen is composed from the design system.", "check": FAILS},
        ])
        assert api.guard(workspace).code == 2
