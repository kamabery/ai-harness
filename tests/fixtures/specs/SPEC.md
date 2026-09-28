# SPEC — a ledger the finance team can actually read

A fixture spec, written the way a requester would write one, so the scaffolder has something real to
copy. Nothing in a run rewrites this file.

## What I want

A small ledger service and one screen on top of it, so the two people who currently reconcile
invoices in a spreadsheet can see unpaid entries without exporting anything.

## Who uses it, and what they do on day one — by persona

- As an AR specialist, I open this to see which invoices went past 60 days unpaid, and chase them
  without exporting anything to a spreadsheet.
- As a project manager, I need to see which entries are blocked and on what, once a week.

## The use cases it has to fix

- See every unpaid entry older than 60 days, sorted by age, on the **Overdue** screen.
- Mark one entry as chased, with a note, from the **Entry detail** screen.
- See nothing alarming when there are no overdue entries — the **Overdue** screen's empty state.

## How we'll know it worked

- `GET /entries?overdue=true` returns only entries older than 60 days with no payment, and the count
  it returns equals `select count(*)` run independently against the same fixture data.
- Marking an entry chased writes a note the service's own log line reports by entry id, and the row
  read back by a separate query carries the same note.
- Each of the two screens renders at 390px and 1280px in both themes with no horizontal overflow,
  the accessibility engine reports 0 serious violations, and every class the markup emits resolves
  against the token file.

## What it must respect

- The shared database is read-only to this run; anything written goes to the local instance.

## What's out of scope

- Not rewriting the nightly import.
- Not touching the payments integration.

## What I'm not sure about

- Whether "unpaid" should mean no payment at all or a partial payment below the invoiced amount.
- Whether the AR specialists can reach the local instance from their machines.
