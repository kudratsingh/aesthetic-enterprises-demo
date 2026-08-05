# Runbook: presenter notes — narrative, talking points, and the concepts behind them

Companion to `demo-script.md` (which has the exact clicks). This is the *why to
say* and the plain-English theory for follow-up questions.

## The setup: 30 seconds before touching the screen

> "This company licenses clinics. Their revenue is a 7% royalty on what each
> clinic reports about itself — so there's a built-in incentive to underreport.
> But HQ controls one thing the clinics can't fake: **the product supply**.
> Every treatment consumes a vial HQ shipped. I built a system where the
> royalty ledger and the supply ledger check each other."

Everything clicked afterward is proof of that sentence. Add one scope line:
"Everything you'll see is synthetic data, deployed live — this isn't localhost."

## Beat 1 — Operator reports their month

**Say:** "The operator attests their numbers — and the moment they submit, the
row becomes immutable *at the database level*, not just in the app. Mistakes
are fixed by filing a correction: a new linked version. The original never
changes."

**Concept — immutability by trigger.** In most apps "you can't edit this" is an
`if` statement in application code, and any bug or admin script can bypass it.
Here Postgres itself runs a trigger (a small program executed automatically on
every update attempt) that rejects changes to locked rows — no exceptions, not
even HQ. Financial records work like accounting books: never erase a line,
write a correcting line (the `supersedes` link).

## Beat 2 — HQ turns reports into money

**Say:** "One click computes royalties for the whole network — 7% of net base
or the contractual minimum, whichever is higher. Rates live in data, not code:
that row is a grandfathered 5% agreement. And watch — running it again
duplicates nothing. Same inputs, same version."

**Concept — idempotency.** An operation is idempotent when doing it twice
equals doing it once. Real systems retry things (timeouts, double-clicks,
duplicate cron fires); for money, retry must never mean bill-twice. The system
fingerprints the run's inputs (a cryptographic hash — a tamper-evident
summary); an identical fingerprint returns the existing run. Changed inputs
create **version 2** and keep version 1 forever — an auditor asking "what did
you bill in July, and why" must get a reconstructible answer (ADR-0004).

**Concept — money as integer cents.** Every amount is a whole number of cents.
Floating-point decimals are slightly imprecise (`0.1 + 0.2 ≠ 0.3` exactly) —
fine for graphics, catastrophic for accounting. Integers are exact.

## Beat 3 — The underreporter (the showpiece)

Walk the columns out loud: "…they reported \$23k. But they administered this
many treatments, times the network's ~\$1,000 average ticket — at least \$40k
walked in the door. They reported **58%** of their own supply-implied floor."

**Punchline (memorize it):** *"Royalties are computed on self-reported revenue
— but every treatment consumed a vial HQ shipped. The supply chain is a lie
detector."* Then resolve the flag with a reason: it's a workflow, not an alarm.

**Concept — a floor, not an estimate.** The system claims only what the data
proves: revenue can't plausibly be *below* this line. It never guesses actual
revenue. Fraud detection that cries wolf gets turned off — hence the
configurable threshold (0.75) and analyst verdicts that survive recomputation
(ADR-0008, rule R5).

## Beat 4 — One-click recall

**Say:** "Supplier calls: lot 001 is contaminated. Here's every patient
touchpoint that used it, across all 20 clinics, in one query — and the answer
is trustworthy *by construction*, because the ledger it reads can only be
appended to."

**Concept — append-only ledger.** Shipment and administration rows physically
cannot be updated or deleted (triggers again). Corrections are *reversing
entries* — a negated row pointing at the original. History is sacred; you fix
the future, not the past. Bonus: on-hand stock is "shipped minus used," and a
CHECK constraint makes negative stock impossible — you cannot record using a
vial that isn't there (invariant 1, ADR-0003).

## The question you WILL get: "how does multi-tenancy work?"

> "Tenant isolation isn't in my application code — it's in Postgres, using
> **Row-Level Security**. Every tenant table carries a policy: you only see
> rows whose org matches the org in your session. The API verifies the login
> token and stamps that org into the database transaction; from that instant
> Postgres filters every query itself. There's no `WHERE org_id = …` I could
> forget to write — the classic multi-tenant bug is structurally impossible.
> And it's proven by a test: operator A cannot read or write operator B's rows,
> even with hand-crafted SQL."

- **RLS in one line:** a filter attached to the table itself, applied to every
  query automatically — the table wears its own bouncer.
- **JWT in one line:** sign-in hands you a *signed* note ("user X, org Y, role
  Z, expires in an hour"); tampering breaks the signature. Each request carries
  it, and its claims become the RLS context — the token *is* the tenancy.
- **HQ's view is policy-level, not a backdoor:** the policy itself contains
  "…or role is hq_admin." No code path skips security; admins are a case
  *inside* the security rule (ADR-0002).

## Rapid-fire answers

- **Migration?** A version-controlled script that changes the database's shape.
  CI rebuilds the whole schema from them, from zero, on every change — the
  production schema is reproducible, not folklore. Merged migrations are never
  edited; fixes are new migrations.
- **CRM integration?** A webhook (a URL accepting POSTs) with two properties:
  **HMAC authentication** — payloads are signed with a shared secret, so forged
  or tampered messages fail a constant-time check — and **idempotent upserts**,
  so the redeliveries webhooks love produce exactly one lead (ADR-0005, R7).
- **Why generate the API client?** Frontend types are generated from the
  backend's OpenAPI spec and CI fails on drift — the frontend can't quietly
  disagree with the backend; the compiler catches it.
- **Deployment?** Merge to main → CI gates (lint, strict types, tests against
  real Postgres, migrations-from-zero) → Render redeploys the API, Cloudflare
  the web, Neon holds Postgres. No manual deploy steps exist (ADR-0007).
- **What's next?** Point at the phase plan: Stripe collections, licensee
  portal, ad attribution — and a hardening phase (audit logs, observability,
  backups) explicitly gating any real data. Demo-shaped product, production-
  shaped patterns, and the gap written down.

## Logistics

- Hit the live URL ~2 minutes early (free tier sleeps; first request ~30s).
- Reseed beforehand for a guaranteed-pristine world — "exactly one flag" is a
  promise, not a hope.
- Wifi fails → every beat runs as curl (`integrations.md` + demo-script
  fallbacks); `make dev` runs the identical stack locally.
- Rehearse the Beat 3 punchline until it needs no screen.
