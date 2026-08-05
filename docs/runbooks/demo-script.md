# Runbook: the two-minute demo

The rehearsed script for the MVP showpiece. Every beat runs in the browser
against the seed world; the exact same flow works on the live deployment
(README has the URL) or locally.

## Setup (before the audience arrives)

```sh
make demo-reset   # deterministic synthetic world, identical every time
make dev          # Postgres + API (:8100) + web (:5173)
```

For the live deployment, reset with the owner URL instead:
`MIGRATIONS_DATABASE_URL=<neon-owner-url> uv run python -m scripts.seed` (from
`api/`). All data is synthetic. Demo logins are in
`docs/runbooks/local-dev.md`. Free-tier note: hit the live API once before the
demo so it's warm.

## The narrative (~2 minutes)

**Beat 1 — The operator reports its month (~30s).** Sign in as
`operator-1@clinic-network-os.demo`. **Monthly reports** → the six locked
months are on screen. In *New report*, pick the location, month `2026-08`,
enter gross and refunds, **Create draft**. Check the attestation box, click
**Submit & attest** — the badge flips to `locked`. Say the line: *this row is
now immutable at the database; corrections create a successor version, never an
edit* (invariant 2). Click **Create correction** if asked to prove it.

**Beat 2 — HQ turns reports into money (~30s).** Sign in as
`hq_admin@clinic-network-os.demo`. **Royalty runs** → month `2026-07` →
**Run royalty period**. Twenty line items appear with org/location, base, rate
(7% — note the grandfathered 5% rows), minimum-applied badges, and the total
due. Click **Run royalty period** again: *"Inputs unchanged — returned existing
v1 (idempotent)"* (invariant 3). Click **Issue invoices** (net-30), then open
**Invoices & aging**: 15 invoices, all current, bucketed 0–30.

**Beat 3 — The system catches the underreporter (~40s).** Open **Variance** →
month `2026-07` → **Compute variance**. Exactly one row appears: **Vista Glow
Clinic — Chandler**, with the math spelled out across the columns —
administrations × avg net ticket = expected floor, reported net far beneath it,
ratio ~0.58 against a 0.75 threshold. The punchline: *royalties are computed on
self-reported revenue, but every treatment consumes product HQ shipped — the
supply ledger makes underreporting visible.* Resolve it live with a reason to
show the review workflow.

**Beat 4 — One-click recall (~20s).** Open **Traceability**, pick a lot in the
recall dropdown: every administration that used that lot, across the whole
network, instantly (~365 rows for LOT-2026-001). Append-only ledger, so the
answer is trustworthy by construction (invariants 1; ADR-0003).

## Optional encore — live integration proof (~30s)

With `GHL_WEBHOOK_SECRET` set, fire the signed webhook from
`docs/runbooks/integrations.md` twice in a row: first call creates the
lead/consult, second is a no-op replay. Idempotent ingestion, demonstrated
live with curl. The HQ dashboard's lead count ticks up by exactly one.

## Fallbacks

- Any beat also runs via the API alone — keep a terminal with the curl
  sequences from `docs/runbooks/integrations.md` handy.
- `make demo-reset` restores the exact same world in seconds; resetting
  mid-demo is safe and invisible.
- If the audience wants the invariants proven rather than narrated:
  `make test-api` runs all of them, named, against real Postgres.
