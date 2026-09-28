"""The shipped structural guards — the boundary rules a run would otherwise have to invent.

These names are requirements. They exist because a real workspace named nine rules, wrote checks
for the two easiest, and left every structural one uncovered.
"""

from __future__ import annotations

import json

import pytest

from harness import api
from harness.dotnet_guards import (
    no_cross_service_reference, no_shared_dbcontext, one_entrypoint_per_service,
)

SERVICES = {"worker": "src/worker", "billing": "src/billing"}


def csproj(path, references=()):
    body = ["<Project Sdk=\"Microsoft.NET.Sdk\">", "  <ItemGroup>"]
    body += ["    <ProjectReference Include=\"{}\" />".format(r) for r in references]
    body += ["  </ItemGroup>", "</Project>"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body), encoding="utf-8")


def cs(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture
def tree(tmp_path):
    """Two services, each with its own host and its own context. The shape the rules describe."""
    csproj(tmp_path / "src" / "worker" / "Worker.csproj")
    csproj(tmp_path / "src" / "billing" / "Billing.csproj")
    cs(tmp_path / "src" / "worker" / "Program.cs", "var app = 1;")
    cs(tmp_path / "src" / "billing" / "Program.cs", "var app = 1;")
    cs(tmp_path / "src" / "worker" / "WorkerDbContext.cs",
       "public class WorkerDbContext : DbContext { }")
    cs(tmp_path / "src" / "billing" / "BillingDbContext.cs",
       "public sealed class BillingDbContext : DbContext { }")
    return tmp_path


class TestCrossServiceReference:
    def test_a_clean_tree_reports_no_violation(self, tree):
        assert no_cross_service_reference(tree, SERVICES).code == 0

    def test_one_service_referencing_another_s_project_is_a_violation(self, tree):
        csproj(tree / "src" / "worker" / "Worker.csproj", ["../billing/Billing.csproj"])
        report = no_cross_service_reference(tree, SERVICES)
        assert report.code == 1
        assert "worker references billing" in report.output

    def test_a_shared_project_outside_every_service_is_allowed(self, tree):
        csproj(tree / "src" / "shared" / "Contracts.csproj")
        csproj(tree / "src" / "worker" / "Worker.csproj", ["../shared/Contracts.csproj"])
        csproj(tree / "src" / "billing" / "Billing.csproj", ["../shared/Contracts.csproj"])
        assert no_cross_service_reference(tree, SERVICES).code == 0


class TestEntrypoints:
    def test_one_host_per_service_reports_no_violation(self, tree):
        assert one_entrypoint_per_service(tree, SERVICES).code == 0

    def test_two_services_sharing_one_host_is_a_violation(self, tree):
        (tree / "src" / "billing" / "Program.cs").unlink()
        report = one_entrypoint_per_service(tree, SERVICES)
        assert report.code == 1
        assert "NO entrypoint" in report.output

    def test_a_service_the_architecture_names_and_the_tree_never_built_is_a_violation(self, tree):
        # The finding this whole guard exists for: a service that was deferred reads, from every
        # other check, exactly like a service that is finished.
        services = dict(SERVICES, portfolio="src/portfolio")
        report = one_entrypoint_per_service(tree, services)
        assert report.code == 1
        assert "not built" in report.output

    def test_two_hosts_inside_one_service_is_a_violation(self, tree):
        cs(tree / "src" / "worker" / "second" / "Program.cs", "var app = 2;")
        assert one_entrypoint_per_service(tree, SERVICES).code == 1


class TestSharedDbContext:
    def test_each_service_owning_its_own_context_reports_no_violation(self, tree):
        assert no_shared_dbcontext(tree, SERVICES).code == 0

    def test_one_service_naming_another_s_context_is_a_violation(self, tree):
        cs(tree / "src" / "billing" / "Report.cs",
           "public class Report { WorkerDbContext db; }")
        report = no_shared_dbcontext(tree, SERVICES)
        assert report.code == 1
        assert "billing names worker's WorkerDbContext" in report.output

    def test_a_name_that_merely_contains_a_context_name_is_not_a_violation(self, tree):
        cs(tree / "src" / "billing" / "Report.cs",
           "public class Report { MyWorkerDbContextFactory f; }")
        assert no_shared_dbcontext(tree, SERVICES).code == 0


class TestThroughTheDeclaration:
    def write(self, target, rules, services=None):
        (target / "docs").mkdir(parents=True, exist_ok=True)
        (target / "docs" / "ARCHITECTURE.md").write_text(
            "# A\n\n- No service reads or writes another service's database.\n", encoding="utf-8")
        (target / "docs" / "guards.json").write_text(
            json.dumps({"services": services if services is not None else SERVICES,
                        "rules": rules}, indent=2), encoding="utf-8")

    def test_a_rule_may_name_a_builtin_instead_of_reinventing_it(self, tree):
        self.write(tree, [{"rule": "No service reads or writes another service's database.",
                           "check": "builtin:no-shared-dbcontext"}])
        assert api.guard(tree).ok

    def test_a_builtin_that_finds_a_violation_fails_the_rule(self, tree):
        cs(tree / "src" / "billing" / "Report.cs",
           "public class Report { WorkerDbContext db; }")
        self.write(tree, [{"rule": "No service reads or writes another service's database.",
                           "check": "builtin:no-shared-dbcontext"}])
        outcome = api.guard(tree)
        assert not outcome.ok
        assert outcome.data["rules"][0]["exit_code"] == 1

    def test_a_builtin_name_that_does_not_exist_is_refused_not_skipped(self, tree):
        self.write(tree, [{"rule": "No service reads or writes another service's database.",
                           "check": "builtin:no-such-guard"}])
        outcome = api.guard(tree)
        assert outcome.refused
        assert "no builtin guard" in outcome.out

    def test_a_boundary_check_with_no_boundaries_declared_is_refused(self, tree):
        # It would otherwise pass over every tree, which is the vacuous green this package exists
        # to refuse.
        self.write(tree, [{"rule": "No service reads or writes another service's database.",
                           "check": "builtin:no-shared-dbcontext"}], services={})
        outcome = api.guard(tree)
        assert outcome.refused
        assert "services" in outcome.out
