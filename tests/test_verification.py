"""The plan's acceptance criteria, run against the only ground truth there is.

Three runs exist under the predecessor harness, two of which shipped and one of which was
abandoned. Every claim this harness makes about being better than that one is checkable against
them, so it is checked here rather than asserted in a README.

The historical trees are not in this repository. Where they are absent these tests skip and say
so - a skipped test is honest; a test that passes because its input was missing is the vacuous
green this whole harness exists to refuse.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import api, brief, check, importer, memory, state

WHATS_NEXT = Path(r"D:\code\Scratchpad\whats-next")
SAMPLE = Path(r"D:\code\SampleProject")

#: The ledger sections that defeated the predecessor, by measurement.
SAMPLE_LEDGER = SAMPLE / "runs" / "initial-setup" / "LOOP-STATE.md"
WN_LEDGER = WHATS_NEXT / "runs" / "initial-setup" / "LOOP-STATE.md"


def _need(path: Path):
    if not path.exists():
        pytest.skip("historical tree absent: " + str(path))


# -- 1. the selftest gate ------------------------------------------------------------------------


def test_every_check_rejects_its_own_bad_input():
    """No check may report green until it has been seen to refuse something."""
    result = check.check_selftest(Path("."), Path("."))
    assert result.defects == [], result.defects
    assert result.examined == len(check.REGISTRY) - 1


def test_a_check_with_a_broken_selftest_is_unproven(tmp_path):
    """The gate itself must bite. A check whose selftest fails may not pass."""
    original = check.REGISTRY["ignore"].selftest
    try:
        check.REGISTRY["ignore"].selftest = lambda: "deliberately broken"
        (tmp_path / ".harness").mkdir()
        state.save(tmp_path, state.State(run="t"))
        results = check.run_all(tmp_path, tmp_path, ["ignore"])
        assert results[0].unproven == "deliberately broken"
        assert not results[0].ok
        _, defects = check.report(results)
        assert defects >= 1
    finally:
        check.REGISTRY["ignore"].selftest = original


# -- 2. the lesson family the old archive excluded by design -------------------------------------


def test_import_carries_the_family_the_old_archive_dropped(tmp_path):
    """The archive kept only CARRIED lessons, so the render-readiness family was excluded.

    Those are the lessons `dashboard-crud` then re-derived three days later in the same
    repository. Importing must carry them, or this harness repeats the defect it was built for.
    """
    _need(WHATS_NEXT)
    mem, _ = importer.into(tmp_path, WHATS_NEXT)
    memory.save(tmp_path, mem)

    observables = " ".join(r.cheaper_observable for r in mem.failures())
    # The two APPLIED lessons the old BUILD-HISTORY excluded by rule.
    assert "post-change invariant" in observables, "theme-settling lesson lost"
    assert "assignedSlot" in observables, "shadow-DOM walk-up lesson lost"
    # And the lesson the next run had to learn again about waiting on an absence.
    assert "positive contract" in observables or "NetworkIdle" in observables


def test_import_does_not_double_count_lessons(tmp_path):
    """A LESSONS.md holds several tables keyed 'Lesson'. Only the six-column one is the ledger."""
    _need(WHATS_NEXT)
    path = WHATS_NEXT / "runs" / "initial-setup" / "LESSONS.md"
    rows = importer.from_lessons(path, "initial-setup", "imported", 1)
    ids = [r.evidence for r in rows]
    assert len(ids) == len(set(ids)), "a lesson was imported twice"
    assert 8 <= len(rows) <= 12, "expected ten lessons, got " + str(len(rows))


def test_every_imported_failure_names_a_cheaper_observable(tmp_path):
    """A lesson that names no cheaper way to have caught it is a story, not a lesson."""
    _need(WHATS_NEXT)
    mem, _ = importer.into(tmp_path, WHATS_NEXT)
    assert memory.validate(mem) == [], memory.validate(mem)


# -- 3. the gate that would have caught the real failure -----------------------------------------


def test_a_run_that_ignores_populated_memory_fails_at_phase_zero(tmp_path):
    """`dashboard-crud` derived 36 facts fresh with an archive sitting beside it.

    Five of its rows cited that archive. This is the check that makes that unreachable.
    """
    _need(WHATS_NEXT)
    mem, _ = importer.into(tmp_path, WHATS_NEXT)
    memory.save(tmp_path, mem)
    memory.write_rendered(tmp_path, mem)

    fresh = state.State(run="dashboard-crud")
    fresh.phases = [state.Phase(0, "preflight", "harness check")]
    fresh.facts = [state.Fact("A1", "derived from scratch", "captures/phase-0.md")]
    state.save(tmp_path, fresh)

    result = check.check_memory(tmp_path, tmp_path / "runs" / "dashboard-crud")
    assert result.defects, "a run that inherited nothing from a populated memory passed"
    assert any("paid for twice" in d for d in result.defects)


def test_inheriting_clears_that_gate(tmp_path):
    """And the gate opens when the run actually reads what was paid for."""
    _need(WHATS_NEXT)
    mem, _ = importer.into(tmp_path, WHATS_NEXT)
    memory.save(tmp_path, mem)
    memory.write_rendered(tmp_path, mem)

    fresh = state.State(run="r")
    fresh.phases = [state.Phase(0, "preflight", "harness check")]
    state.save(tmp_path, fresh)
    memory.inherit(tmp_path, fresh)
    state.save(tmp_path, fresh)

    result = check.check_memory(tmp_path, tmp_path / "runs" / "r")
    assert not any("paid for twice" in d for d in result.defects), result.defects


def test_an_inherited_fact_is_open_until_this_run_reverifies_it(tmp_path):
    """A citation is not a signal. The predecessor treated one as the other."""
    _need(WHATS_NEXT)
    mem, _ = importer.into(tmp_path, WHATS_NEXT)
    memory.save(tmp_path, mem)
    fresh = state.State(run="r")
    state.save(tmp_path, fresh)
    memory.inherit(tmp_path, fresh)

    inherited = [f for f in fresh.facts if f.source == "inherited"]
    assert inherited, "nothing was inheritable, so this proves nothing"
    assert all(f in fresh.open_facts() for f in inherited)
    inherited[0].reverified = True
    assert inherited[0] not in fresh.open_facts()


# -- 4. the ceilings, fed the real shapes that defeated the predecessor ---------------------------


def _section(text: str, heading: str) -> str:
    """One `## N. HEADING` section, up to the next `## `."""
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find("\n## ")
    return rest if end < 0 else rest[:end]


def test_the_captures_section_that_was_92_percent_of_a_ledger_is_refused():
    """SampleProject's section 3 held 3,451 of 3,738 lines - 195,816 chars of pasted output.

    It is refused here at the first append, by the per-string ceiling rather than by a rule about
    which section output belongs in. A positional rule is what relocated the growth last time.
    """
    _need(SAMPLE_LEDGER)
    text = SAMPLE_LEDGER.read_text(encoding="utf-8", errors="replace")
    captures = _section(text, "## 3. CAPTURED OUTPUTS")
    assert len(captures) > 100_000, "the historical section is smaller than recorded; check input"

    bad = state.State(run="sampleproject")
    bad.failures = [state.Failure(captures, 3)]
    defects = state.validate(bad)
    assert any("over the" in d and "char ceiling" in d for d in defects), defects


def test_the_cursor_that_became_a_retrospective_is_unrepresentable():
    """whats-next's cursor section reached 420 of 620 lines, holding every phase's result.

    Its own rule said "Exactly one active phase and one next action at a time" and nothing
    enforced it. Here the cursor is one object with one action, so the retrospective has nowhere
    to go: it fails as an over-long action and as keys that are not part of a cursor.
    """
    _need(WN_LEDGER)
    text = WN_LEDGER.read_text(encoding="utf-8", errors="replace")
    cursor = _section(text, "## 2. CURRENT CURSOR")
    assert len(cursor.splitlines()) > 300, "the historical section is smaller than recorded"

    bad = state.State(run="whats-next")
    bad.cursor = {"phase": 10, "next_action": cursor}
    defects = state.validate(bad)
    assert any("next_action" in d for d in defects), defects

    worse = state.State(run="whats-next")
    worse.cursor = {"phase": 10, "next_action": "x", "phase_9_result": "...",
                    "phase_8_result": "..."}
    assert any("not part of it" in d for d in state.validate(worse))


def test_a_cursor_cannot_be_a_list_of_active_phases():
    bad = state.State(run="r")
    bad.cursor = [{"phase": 1}, {"phase": 2}]
    assert any("not a list" in d for d in state.validate(bad))


def test_a_stub_capture_does_not_satisfy_a_passed_phase(tmp_path):
    """Ten 818-byte templates reading "(nothing captured yet)" passed the predecessor's check.

    It asserted the file existed. Here a passed phase's capture must hash to what state recorded,
    so a template cannot stand in for evidence.
    """
    run = tmp_path / "runs" / "r"
    (run / "captures").mkdir(parents=True)
    stub = run / "captures" / "phase-1.md"
    stub.write_text("# Phase 1 captures\n\n_(nothing captured yet)_\n", encoding="utf-8")

    st = state.State(run="r")
    st.phases = [state.Phase(1, "slice", "cmd", status="passed", red_seen=True,
                             capture_ref="captures/phase-1.md",
                             capture_sha=state.sha256("the real output"),
                             counts=state.Counts(executed=7))]
    state.save(tmp_path, st)
    result = check.check_state(tmp_path, run)
    assert any("does not match" in d for d in result.defects), result.defects


# -- 5. the brief stays a slice -------------------------------------------------------------------


def test_a_brief_over_a_run_with_thirty_six_facts_stays_under_the_ceiling(tmp_path):
    """The measured shape: both real runs settled 36 facts. A phase needs three of them."""
    st = state.State(run="r")
    st.facts = [state.Fact("A" + str(i), "a settled fact, number " + str(i), "p:" + str(i))
                for i in range(1, 37)]
    st.phases = [state.Phase(0, "preflight", "c"),
                 state.Phase(1, "baseline", "c", counts=state.Counts(executed=97)),
                 state.Phase(2, "slice-1", "c", needs=["A3", "A7", "A12"])]
    for phase in st.phases:
        text = brief.compose(st, phase.id)
        assert brief.size_of(text) <= brief.MAX_BYTES, (phase.id, brief.size_of(text))
    # And the slice is actually a slice: three facts named, not thirty-six.
    text = brief.compose(st, 2)
    assert "A3" in text and "A7" in text
    assert "A20" not in text and "A31" not in text


def test_a_phase_that_needs_everything_is_refused(tmp_path):
    """If a phase names every fact, the brief has become the ledger again."""
    st = state.State(run="r")
    st.facts = [state.Fact("A" + str(i), "a fact with real prose in it, number " + str(i) + " " +
                           "z" * 120, "p:" + str(i)) for i in range(1, 37)]
    st.phases = [state.Phase(2, "slice-1", "c", needs=[f.id for f in st.facts])]
    state.save(tmp_path, st)
    result = check.check_brief(tmp_path, tmp_path / "runs" / "r")
    assert any("stopped being a slice" in d for d in result.defects), result.defects


# -- 6. regressions found by running this harness against itself ----------------------------------


def test_spec_coverage_reads_bullets_and_so_cannot_pass_by_finding_nothing():
    """Found by running the check against a real spec: it passed having examined no claims.

    The claim filter skipped every line starting with "-", and a "what done means" criterion is
    almost always a bullet. So the claim list came back empty and the check reported PASS - the
    vacuity it exists to catch, occurring inside it. Silence wins unless a check can fail on
    omission, which is why this asserts the claims are found, not merely that defects appear.
    """
    spec = "## What done means\n\n- The run builds a greeting command that prints a greeting.\n"
    empty = state.State(run="t")
    defects = check._spec_defects(spec, empty)
    assert defects, "a bulleted criterion with no command behind it was accepted"

    backed = state.State(run="t")
    backed.phases = [state.Phase(2, "slice", "python greeting_test.py")]
    assert not check._spec_defects(spec, backed)


def test_validate_reports_a_malformed_cursor_instead_of_raising():
    """A check that crashes on bad input is a check that cannot report.

    Found by the cursor-as-a-list test: `as_json` coerced the cursor with `dict()` and raised
    before validation could name the defect.
    """
    bad = state.State(run="t")
    bad.cursor = [{"phase": 1}, {"phase": 2}]
    defects = state.validate(bad)  # must not raise
    assert any("not a list" in d for d in defects)


def test_a_placeholder_reason_does_not_exempt_an_architectural_rule():
    """Six of ten rules sat behind "TODO - no check written yet" and were counted as coverage."""
    from harness import guards
    assert guards.is_placeholder("TODO - no check written yet")
    assert guards.is_placeholder("")
    assert guards.is_placeholder("WIP")
    assert not guards.is_placeholder(
        "the only observable is an integration test we do not run here")


def test_the_report_survives_content_it_did_not_choose():
    """A report that dies on an arrow is a report that fails on its own output.

    Found on a cp1252 console: an imported archive row containing U+2192 killed the command after
    it had done its work.
    """
    outcome = api.Outcome(code=0, report="inherited: a → b — done")
    assert "→" in str(outcome)
    assert outcome.rows() == []
