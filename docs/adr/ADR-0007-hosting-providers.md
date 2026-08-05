# ADR-0007: Hosting providers — Render, Cloudflare Pages, Neon

- **Status:** accepted
- **Date:** 2026-08-05
- **Phase:** 0
- **Refines:** ADR-0001 (which allowed Cloud Run/Render and Pages/Vercel)

## Context

Phase 0's exit criterion requires a live URL. ADR-0001 left the concrete
API host and static host open. Constraints: free tier, push-to-deploy from
GitHub on merge to main (CLAUDE.md §4 CD requirement), minimal console
surface for a solo project.

## Decision

- **API → Render** (Docker web service via `render.yaml` blueprint, free plan).
  Chosen over Cloud Run: blueprint-in-repo config, zero IAM/gcloud setup, and
  auto-deploy on push with no extra CI wiring. Migrations run at container boot
  (`alembic upgrade head && uvicorn …`) because `preDeployCommand` is not
  available on the free plan; safe while migrations are fast and idempotent.
- **Web → Cloudflare Pages** (GitHub integration; root `web/`, build
  `npm run build`, output `dist/`). Equivalent to Vercel; picked for the
  unmetered free bandwidth and simpler env model. `VITE_API_URL` points at the
  Render URL at build time.
- **Postgres → Neon** (free tier, pooled connection string). Serverless,
  scale-to-zero, branchable — already named in ADR-0001.

## Consequences

- CD is platform-native (both providers watch `main`); no deploy job in GitHub
  Actions. CI remains the merge gate; the platforms deploy what CI let through.
- Render free tier sleeps when idle — first request after a quiet period takes
  ~30s. Acceptable for a demo; a paid instance or keep-warm ping fixes it if it
  ever grates.
- The deployed API runs `ENVIRONMENT=dev` during Phase 0 so the dev-token
  endpoint can drive the walking-skeleton demo (all data is synthetic). Phase 1
  (ADR-0006 real auth) flips it to `prod`, which hard-disables that endpoint.
- Web↔API is cross-origin in production, so `CORS_ORIGINS` must contain the
  deployed web origin; local dev stays same-origin via the Vite proxy.

## Amendment (2026-08-05)

Cloudflare's dashboard now provisions Git-connected static sites as **Workers
with static assets** rather than classic Pages projects — same platform, same
free tier, same push-to-deploy; the deploy step is `npx wrangler deploy` driven
by `web/wrangler.jsonc`, and the URL is `*.workers.dev` instead of `*.pages.dev`.
The decision (Cloudflare for static hosting) is unchanged.
