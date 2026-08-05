# /docs — repository context store

This folder is the project's living documentation. Per CLAUDE.md §5, check here for
background before working on an area, and write back anything a future contributor
(or a future Claude session) would need.

## Layout

| Path | What lives here |
|---|---|
| `PROJECT_CONTEXT.md` | Domain semantics, business rules, and architecture rationale. **Read this first** for any domain work. |
| `adr/` | Architecture Decision Records — `ADR-NNNN-title.md`, numbered, append-only. Major decisions only; supersede, never delete. |
| `runbooks/` | Operational how-tos: local dev, deploy, demo reset, incident notes. Created as needed. |
| `phases/` | Per-phase working notes and exit-criteria evidence. Created as needed. |

## Rules

- Docs are updated in the same PR as the change they describe; stale docs are bugs.
- ADRs get the next free number. A superseded ADR gets a `Status: superseded by ADR-NNNN`
  header line — its file is never edited beyond that, never deleted.
- Anything that only exists in a chat transcript does not exist. Write it down here.
