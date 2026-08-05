# PROJECT_CONTEXT.md — Domain & System Context for clinic-network-os

Audience: coding agents and contributors. This document explains the business domain, the rules the system encodes, and the reasoning behind the architecture. `CLAUDE.md` at the repo root defines *how* to work; this document defines *what the system means*. On conflict, `CLAUDE.md` wins for process; this document wins for domain semantics.

---

## 1. The business model this system serves

The reference operator is a **clinic licensor**: a company that sells licenses to independent owners ("operators") to run aesthetic-services clinics under a shared brand, playbook, and supply chain. The licensor's revenue has three streams: an upfront license fee (outside this system's scope), **an ongoing royalty — default 7% of each location's revenue**, and margin on the consumable product it supplies to clinics. Operators may own multiple locations. Clinics run a consult-to-treatment funnel: marketing produces leads, leads book free consults, an in-clinic closer sells multi-visit treatment plans, licensed staff administer treatments that consume supplied product.

The structural tension the system exists to resolve: **royalties are computed on revenue the licensee reports about itself.** Self-reporting creates an underreporting incentive. The licensor, however, controls two independent signals — the top of the funnel (lead/booking data flows through licensor-managed marketing systems) and the product supply (every treatment consumes vials the licensor shipped). Product consumption therefore implies a floor on plausible revenue. The system's distinctive job is joining the royalty ledger to the supply ledger so that reported revenue can be *verified*, not just recorded.

All data in this repository is synthetic. Location names in the seed may resemble real public clinic names purely as realistic labels; every figure attached to them is fabricated by the seed script.

## 2. Personas and permissions

| Capability | hq_admin | operator | clinic_staff |
|---|---|---|---|
| See all orgs/locations | ✔ | own org only | own location only |
| Configure license agreements, rates, minimums | ✔ | — | — |
| Run royalty periods, issue invoices | ✔ | — | — |
| Submit/attest monthly revenue report | — | ✔ (own locations) | — |
| View statements, line items, invoices | all | own | — |
| Receive/ship lots | ✔ (ship) | ✔ (receive) | ✔ (receive) |
| Log treatment administrations | — | ✔ | ✔ |
| View variance flags | ✔ | own, resolved view only | — |
| KPI dashboards | network-wide | own locations | own location |

Enforcement is Postgres RLS keyed on `app.org_id` / `app.role` session settings (see CLAUDE.md §2.3 and ADR-0002). UI role-gating is a convenience layer, never the security boundary.

## 3. Domain glossary (canonical vocabulary — use these exact terms)

- **Org** — a tenant: the HQ licensor or one operator company. **Location** — one physical clinic, owned by exactly one org.
- **License agreement** — per-org terms: `royalty_rate` (default 0.07), `base_definition`, `monthly_minimum` (nullable), effective date range. Rates are per-agreement so grandfathered or promotional terms don't require code changes.
- **Period** — one calendar month in the network timezone. Storage is UTC; period boundaries are computed in `network_timezone` (config, default `America/Phoenix`, chosen because it observes no DST and eliminates an entire class of boundary bugs).
- **Revenue report** — an operator's monthly statement per location: `gross_sales`, `refunds`, derived `net_base = gross_sales − refunds`. Lifecycle: `draft → submitted → locked`. Submission requires **attestation** (who, when). Locked reports are immutable; corrections create a successor report referencing the original.
- **Royalty run** — one versioned execution of royalty calculation for a period across all active locations. Runs are idempotent per (period, input set) and append-only: a rerun after corrected inputs creates version N+1; prior versions are never mutated. **Line item** — one location's result within a run: `base`, `rate`, `minimum_applied`, `adjustments`, `amount_due`.
- **Invoice** — billing artifact generated from exactly one run version. Statuses: `issued → paid | overdue`. Regeneration supersedes (`superseded_by`), never edits. **Aging** — buckets of unpaid invoices by days outstanding (0–30, 31–60, 61–90, 90+).
- **Product / Lot / Shipment / Administration** — the supply chain. A lot carries supplier and expiry; shipments move lot quantities to locations; an administration records one treatment consuming product from a specific lot at a specific location, referencing a `synthetic_patient_ref`. The administrations/shipments tables form an **append-only ledger**: corrections are reversing entries, and derived on-hand can never go negative (DB CHECK).
- **Variance flag** — a per-location, per-period discrepancy record comparing `reported net_base` against an `expected_floor` derived from supply consumption. Statuses: `open → reviewed → resolved(reason)`.
- **Recall query** — "every administration that used lot X," one query, any time window.

## 4. Core business rules (implementation spec)

Money is **integer cents** everywhere — storage, transport, arithmetic. No floats touch currency. IDs are UUIDv7 (time-ordered).

**R1 — Royalty amount.** For a location active the full period: `royalty = max(round(rate × net_base), monthly_minimum or 0)`; `minimum_applied = true` when the floor binds. Mid-period activation prorates the minimum by active days ÷ days in period; the percentage component never prorates (it already scales with revenue).

**R2 — Base definition (MVP default).** `net_base = gross_sales − refunds`, treatment revenue only. Retail/product resale is excluded in the MVP and the field structure leaves room to include it later via `base_definition`. This is a flagged assumption (§8), not settled law.

**R3 — Report locking.** `submit` requires attestation and transitions draft→submitted→locked atomically. Any mutation attempt on a locked report raises `ReportLockedError`; the correction path is `create_correction(report_id)` producing a new draft linked to its predecessor. A period with an unlocked report for an active location cannot be included in a run — the run either excludes that location (recorded on the run) or is blocked, per a `run_policy` config (MVP default: exclude and record).

**R4 — Run versioning.** `run_royalty_period(period)` computes over the current locked reports and adjustments. If an identical input fingerprint already has a run version, return it (idempotency). If inputs changed, create version N+1. Line items always belong to exactly one version.

**R5 — Variance computation (MVP default).** `expected_floor = administrations_in_period × avg_net_ticket`, where `avg_net_ticket` is the trailing-90-day network average of `sale.plan_value ÷ planned_treatments` (seed provides a stable value). Flag when `net_base < expected_floor × variance_threshold` (config, default 0.75). The formula is deliberately a *floor*, not an estimate of truth — it can only ever indicate "reported revenue is implausibly low given product consumed," which is the honest claim the data supports. Thresholds and the ticket model are configurable because false positives destroy trust in the feature.

**R6 — Ledger semantics.** Shipments and administrations are insert-only. On-hand per (location, lot) = shipped − administered − reversals; a transaction that would drive it negative fails at the database. Expired lots cannot be administered (checked at service layer, surfaced clearly in UI).

**R7 — Funnel ingestion.** External webhook payloads (`/webhooks/ghl`, HMAC-verified) and CSV imports are mapped into `leads/consults/sales` with `source` and `external_id` for idempotent upsert. Ingestion never mutates royalty or supply aggregates directly — it only feeds the funnel/KPI layer.

## 5. Flow narratives (the three loops)

**Monthly royalty loop.** Operator opens the period → enters gross and refunds per location → attests and submits (locks) → HQ runs the period → line items computed under R1–R4 → invoices issued → aging tracks payment → variance job compares each location's report to its supply-derived floor (R5) and opens flags → HQ reviews flags; resolution reasons are recorded. Everything an operator is billed for is visible to them as a statement — transparency is a design goal because disputes are the expensive failure mode.

**Supply loop.** HQ receives a lot from a supplier → ships quantities to locations → clinic staff log each administration against a lot at treatment time → on-hand decrements under R6 → reorder signal when on-hand crosses a threshold (post-MVP) → recall query available at all times.

**Funnel loop.** Marketing systems push contacts/appointments via webhook → mapped to leads/consults → in-clinic sale recorded with plan value → treatments scheduled → administrations link the funnel to the supply ledger, closing the verification triangle.

## 6. Architecture rationale (the "why" behind CLAUDE.md's "what")

- **RLS in the database, not the app** (ADR-0002): tenancy bugs in application code are the most common multi-tenant failure; pushing enforcement into Postgres makes the safe path the only path and makes the isolation testable with two seeded tenants.
- **Append-only ledgers** (ADR-0003): supply movements and royalty runs are financial-adjacent records where "who changed what, when" is the product. Updates destroy that; reversing entries and versions preserve it, and they make idempotency natural.
- **Versioned royalty runs** (ADR-0004): recalculation after corrected inputs is a certainty, and audit clauses in license agreements make traceable recomputation a requirement, not a nicety.
- **Sync from external marketing systems rather than replace them** (ADR-0005): the funnel already lives in a third-party CRM; the wedge is owning the canonical data and the money logic first. Replacement is a later, political decision — the architecture stays agnostic to it.
- **No PHI, no EHR** — clinical records belong in purpose-built, BAA-covered systems. This system stores `synthetic_patient_ref` opaque identifiers only, and that boundary is permanent in this codebase.

## 7. Seed world (deterministic — fixed RNG seed)

One HQ org; three operator orgs (one single-location, one 3-location, one 4-location) plus enough single-location operators to reach ~20 locations; 6 months of funnel and treatment history with plausible ramp curves; agreements at 7% with one grandfathered 5% and one $2,000/month minimum; lots, shipments, and administrations consistent with treatment volume — **except one designated underreporter location whose submitted reports run ~40% below its supply-implied floor**, guaranteeing exactly one variance flag per recent period for the demo. `make demo-reset` rebuilds this world identically every time.

## 8. Assumptions log (defaults chosen to unblock; surface, don't silently change)

A1: royalty base excludes retail (R2). A2: variance threshold 0.75 and trailing-90d ticket model (R5). A3: run policy excludes-and-records unlocked locations (R3). A4: periods are calendar months in `America/Phoenix`. A5: invoices are net-30. A6: a single network-wide product price list (no per-location pricing). Each is a config point or clearly isolated function; changing one must not require schema surgery.

## 9. Non-goals (MVP)

Payment execution (Stripe/ACH is Phase 6), onboarding portal (Phase 7), ad-spend attribution (Phase 8), consent registry and audit-log hardening (Phase 9), any marketing-content generation, any real data of any kind.

## 10. docs/ conventions

```
/docs
  PROJECT_CONTEXT.md      # this file — domain semantics, rules, rationale
  /adr                    # ADR-NNNN-kebab-title.md, sequential, never deleted
  /runbooks               # added when operational procedures exist (Phase 6+)
```

ADR format: Status / Context / Decision / Consequences, one page, present tense. Write one whenever a decision would take a paragraph to justify in a PR description; link ADRs from the PRs that implement them. When this document and an ADR disagree, the newer ADR wins and this document gets a same-PR update — stale context documents are worse than none.
