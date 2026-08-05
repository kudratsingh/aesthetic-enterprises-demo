# Runbook: the two-minute demo — DRAFT

> **Status: DRAFT.** The narrative below is the rehearsal target for the Phase
> 3/4/5 exit criteria. Steps marked **[UI pending]** depend on Phase 3 (royalty
> UI) and Phase 4 (dashboard/variance/traceability UI) screens that are not
> merged yet; until they land, those beats run via API calls. Update this
> script with exact clicks and screen names as the UI ships, then drop the
> DRAFT marker during Phase 5 hardening.

## Setup (before the audience arrives)

```sh
make demo-reset   # deterministic synthetic world, identical every time
make dev          # Postgres + API (:8100) + web (:5173)
```

All data is synthetic. Demo logins are in `docs/runbooks/local-dev.md`.

## The narrative (~2 minutes)

**Beat 1 — The operator reports its month (~30s).** Log in as an operator
(`operator-1@clinic-network-os.demo`). Open the current period, review gross
and refunds for the location, attest, and submit. Point out the lock: the
report is now immutable — corrections would create a new version, never edit
this one (invariant 2). **[UI pending — Phase 3 operator shell]**

**Beat 2 — HQ turns reports into money (~30s).** Log in as HQ
(`hq_admin@clinic-network-os.demo`). Run the royalty period: line items appear
per location — 7% of net base, minimums applied where the floor binds. Issue
invoices, show the aging view. Rerun the period to show idempotency: same
inputs, same version, no drift (invariant 3). **[UI pending — Phase 3 HQ
shell]**

**Beat 3 — The system catches the underreporter (~40s).** Open the variance
view. One location is flagged: **"Vista Glow Clinic — Chandler"** — the seeded
underreporter, reporting ~40% below its supply-implied floor. Walk the math on
screen: administrations in the period × average net ticket = expected floor;
reported net base sits far under it. The punchline: *royalties are computed on
self-reported revenue, but every treatment consumes product HQ shipped — the
supply ledger makes underreporting visible.* **[UI pending — Phase 4 variance
view]**

**Beat 4 — One-click recall (~20s).** From traceability, pick a lot and run
the recall query: every administration that used that lot, across the network,
in one view. Append-only ledger, so the answer is trustworthy by construction
(invariant 1). **[UI pending — Phase 4 traceability]**

## Optional encore — live integration proof (~30s)

With `GHL_WEBHOOK_SECRET` set, fire the signed webhook from
`docs/runbooks/integrations.md` twice in a row: first call creates the
lead/consult, second returns all-false flags and the row count doesn't move.
Idempotent ingestion, demonstrated live with curl. (Works today — no UI
required.)

## Fallbacks

- If the web app misbehaves, beats 1–2 run entirely via the API (Phase 2
  endpoints) — keep a terminal with the curl sequence ready.
- `make demo-reset` restores the exact same world in seconds; resetting
  mid-demo is safe and invisible.
