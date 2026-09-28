# ARCHITECTURE — the guardrails for the ledger workspace

A fixture set of guardrails, written once and inherited by every run after the initial one.

## The shape of the system

One HTTP service and one browser application. The browser application talks to the service over
HTTP and to nothing else.

## What it is built on

- .NET 10 for the service, and React for the browser application. Both were settled before this
  workspace existed; `docs/PLUMBING.md` carries the evidence.
- Postgres for storage. Not decided yet: whether the read model lives in the same database.

## The architectural philosophies this system commits to

- Event-driven at the boundary: the service publishes an entry-changed event rather than calling
  another service. Nothing here calls another service synchronously.
- The domain owns its vocabulary. An "entry" in the HTTP layer and an "entry" in the domain are the
  same word for the same thing, or one of them is renamed.

## The rules a run may not break

- Nothing in the domain project references the persistence project.
- The browser application never reads the database directly.
- Secrets come from the environment, never from a file in the tree.
- Schema changes are migrations in the tree, never applied by hand.

## The design system

None yet. Building one is the first UI phase's deliverable — the token file, the component
directory and a style guide route, all three named here once they exist.

## What this workspace deliberately does not do

- No mobile application.
- No direct integration with the payments provider.

## What we're not sure about yet

- Whether the read model belongs in the same database as the write model.
- Which environment the CI runner can actually reach.
