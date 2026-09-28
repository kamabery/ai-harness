"""The UI quality guards — the mechanical half of "it should look professionally designed".

These names are requirements. Each one is a tell that styling took the path of least resistance,
and each was chosen because it is checkable; the ones that are not checkable are the prototype
gate's, and `docs/DESIGN.md` says which is which.
"""

from __future__ import annotations

import pytest

from harness.ui_guards import (
    contrast, contrast_ratio, default_theme, focus_visible, placeholder_copy,
    raw_values, view_states,
)

TOKENS = """
:root {
  --neutral-0: #ffffff;
  --neutral-900: #18181b;
  --bg: var(--neutral-0);
  --bg-raised: var(--neutral-0);
  --fg: var(--neutral-900);
  --fg-muted: #52525b;
  --fg-subtle: #71717a;
  --accent: #7b2d8e;
  --fg-on-accent: #ffffff;
  --border-strong: #767676;
  --space-4: 1rem;
}
:where(a, button):focus-visible { outline: 2px solid var(--accent); }
"""


@pytest.fixture
def app(tmp_path):
    (tmp_path / "styles").mkdir()
    (tmp_path / "styles" / "tokens.css").write_text(TOKENS, encoding="utf-8")
    (tmp_path / "Page.razor").write_text(
        "<div class='card'>Overdue invoices</div>", encoding="utf-8")
    return tmp_path


DECL = {"tokens": "styles/tokens.css"}


class TestContrast:
    def test_the_ratio_is_the_wcag_one(self):
        assert round(contrast_ratio("#000000", "#ffffff"), 2) == 21.0
        assert round(contrast_ratio("#ffffff", "#ffffff"), 2) == 1.0

    def test_a_system_whose_roles_all_meet_aa_reports_no_violation(self, app):
        assert contrast(app, DECL).code == 0

    def test_a_role_pair_below_aa_is_a_violation_naming_the_measured_ratio(self, app):
        css = TOKENS.replace("--fg-muted: #52525b;", "--fg-muted: #b0b0b0;")
        (app / "styles" / "tokens.css").write_text(css, encoding="utf-8")
        report = contrast(app, DECL)
        assert report.code == 1
        assert "--fg-muted on --bg" in report.output
        assert ":1" in report.output

    def test_a_token_that_resolves_through_var_is_still_measured(self, app):
        # --bg is var(--neutral-0). A checker that gave up on the indirection would measure nothing
        # and report a clean zero, which is the vacuous green this package refuses everywhere.
        assert "0 violation(s) over 6 readable pair(s)" in contrast(app, DECL).output

    def test_a_system_that_names_its_roles_differently_fails_loudly_rather_than_measuring_nothing(self, app):
        (app / "styles" / "tokens.css").write_text(
            ":root { --colour-text: #111; --colour-page: #fff; }", encoding="utf-8")
        report = contrast(app, DECL)
        assert report.code == 1
        assert "nothing was actually measured" in report.output


class TestDefaultTheme:
    def test_a_product_with_its_own_palette_reports_no_violation(self, app):
        assert default_theme(app, DECL).code == 0

    def test_a_framework_default_left_in_place_is_a_violation(self, app):
        (app / "Page.razor").write_text("<a style='color:#0d6efd'>Go</a>", encoding="utf-8")
        report = default_theme(app, DECL)
        assert report.code == 1
        assert "Bootstrap" in report.output

    def test_shipping_the_seed_accent_unchanged_is_the_same_omission(self, app):
        # The seed exists to make the good path cheap, not to be the answer.
        (app / "styles" / "brand.css").write_text("a { color: #3b76f6; }", encoding="utf-8")
        report = default_theme(app, DECL)
        assert report.code == 1
        assert "seed" in report.output


class TestRawValues:
    def test_a_literal_in_the_token_file_is_where_literals_belong(self, app):
        assert raw_values(app, DECL).code == 0

    def test_a_raw_colour_in_a_component_is_a_violation(self, app):
        (app / "Page.razor").write_text("<div style='color:#ff0000'>x</div>", encoding="utf-8")
        assert raw_values(app, DECL).code == 1

    def test_a_raw_length_in_a_component_is_a_violation(self, app):
        (app / "Page.razor").write_text("<div style='padding:13px'>x</div>", encoding="utf-8")
        assert raw_values(app, DECL).code == 1

    def test_a_hairline_border_is_not_worth_flagging(self, app):
        (app / "Page.razor").write_text("<div style='border-width:1px'>x</div>", encoding="utf-8")
        assert raw_values(app, DECL).code == 0

    def test_a_declared_design_system_file_may_hold_literals_too(self, app):
        (app / "styles" / "base.css").write_text("body { margin: 13px; }", encoding="utf-8")
        assert raw_values(app, DECL).code == 1
        widened = dict(DECL, design_system=["styles/*.css"])
        assert raw_values(app, widened).code == 0


class TestFocusVisible:
    def test_a_defined_focus_style_reports_no_violation(self, app):
        assert focus_visible(app, DECL).code == 0

    def test_a_tree_with_no_focus_style_anywhere_is_a_violation(self, app):
        (app / "styles" / "tokens.css").write_text(":root { --bg: #fff; }", encoding="utf-8")
        report = focus_visible(app, DECL)
        assert report.code == 1
        assert "no :focus-visible style" in report.output

    def test_suppressing_the_outline_with_nothing_replacing_it_is_a_violation(self, app):
        (app / "styles" / "bad.css").write_text("button { outline: none; }", encoding="utf-8")
        assert focus_visible(app, DECL).code == 1

    def test_suppressing_it_and_replacing_it_is_not(self, app):
        (app / "styles" / "ok.css").write_text(
            "button:focus-visible { outline: none; box-shadow: 0 0 0 2px blue; }", encoding="utf-8")
        assert focus_visible(app, DECL).code == 0


class TestPlaceholderCopy:
    def test_real_copy_reports_no_violation(self, app):
        assert placeholder_copy(app, DECL).code == 0

    def test_lorem_ipsum_shipped_as_product_copy_is_a_violation(self, app):
        (app / "Page.razor").write_text("<p>Lorem ipsum dolor sit amet</p>", encoding="utf-8")
        assert placeholder_copy(app, DECL).code >= 1

    def test_a_generated_list_of_item_1_item_2_is_a_violation(self, app):
        (app / "Page.razor").write_text("<li>Item 1</li><li>Item 2</li>", encoding="utf-8")
        assert placeholder_copy(app, DECL).code >= 1

    def test_the_placeholder_attribute_is_legitimate_and_is_not_flagged(self, app):
        # An earlier version fired on this. A guard that cries wolf is how a whole set gets
        # disabled, and the useful ones go with it.
        (app / "Page.razor").write_text(
            '<input placeholder="Search invoices" />', encoding="utf-8")
        assert placeholder_copy(app, DECL).code == 0

    def test_the_placeholder_pseudo_element_is_legitimate_too(self, app):
        (app / "styles" / "x.css").write_text(
            "input::placeholder { color: var(--fg-subtle); }", encoding="utf-8")
        assert placeholder_copy(app, DECL).code == 0


class TestViewStates:
    def test_a_component_set_naming_all_three_states_reports_no_violation(self, app):
        (app / "States.razor").write_text(
            "@if (loading) {<Spinner/>} else if (error) {<Err/>} else if (empty) {<Empty/>}",
            encoding="utf-8")
        assert view_states(app, DECL).code == 0

    def test_a_build_with_only_its_happy_path_is_a_violation(self, app):
        report = view_states(app, DECL)
        assert report.code == 3
        assert "empty state" in report.output

    def test_todo_as_a_domain_noun_is_not_a_code_marker(self, app):
        # A kanban board has a Todo column. An earlier version matched case-insensitively and
        # reported 36 violations in one, every one of them a legitimate name.
        (app / "TodoColumn.razor").write_text(
            "<div class='todo-column'>Todo</div>", encoding="utf-8")
        assert placeholder_copy(app, DECL).code == 0

    def test_an_uppercase_todo_marker_shipped_in_markup_still_is_one(self, app):
        (app / "Page.razor").write_text("<p>TODO: wire this up</p>", encoding="utf-8")
        assert placeholder_copy(app, DECL).code == 1
