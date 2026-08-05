# Runbook: deploy (Neon + Render + Cloudflare Pages)

Architecture (ADR-0007): Cloudflare Pages serves the built SPA → Render runs the
API container → Neon hosts Postgres. Both platforms watch `main` and deploy on
merge; CI is the gate in front of them.

## One-time setup

### 1. Neon (database)

1. https://neon.tech → create project (name: `clinic-network-os`, Postgres 16+).
2. Copy the **pooled** connection string and convert it for asyncpg:
   - scheme `postgresql://` → `postgresql+asyncpg://`
   - `?sslmode=require&channel_binding=require` → `?ssl=require`
     (asyncpg does not understand `sslmode`/`channel_binding`)
   - result shape:
     `postgresql+asyncpg://USER:PASS@ep-xxx-pooler.REGION.aws.neon.tech/neondb?ssl=require`

### 2. Render (API)

1. https://render.com → **New → Blueprint** → connect
   `kudratsingh/aesthetic-enterprises-demo`. Render reads `render.yaml` and
   proposes the `cnos-api` service.
2. When prompted for env vars:
   - `DATABASE_URL` — the converted Neon URL from step 1
   - `CORS_ORIGINS` — leave a placeholder `[]` for now; filled in step 4
3. Deploy. Note the service URL, e.g. `https://cnos-api.onrender.com`.
4. Verify: `curl https://cnos-api.onrender.com/api/v1/health` → `{"status":"ok"}`
   (first hit after idle takes ~30s — free tier cold start).

### 3. Cloudflare (web)

Cloudflare's current dashboard provisions Git-connected static sites as
**Workers with static assets** (the successor to classic Pages). The repo
carries `web/wrangler.jsonc`, which tells `wrangler deploy` to publish
`web/dist` as a SPA.

1. https://dash.cloudflare.com → **Workers & Pages → Create → Connect to Git**
   → pick the repo.
2. Build settings:
   - Root directory: **`/web`** (the #1 mistake — `/` makes npm fail on a
     missing package.json)
   - Build command: `npm run build`
   - Deploy command: `npx wrangler deploy`
3. Build variables:
   - `VITE_API_URL` = the Render URL (no trailing slash)
   - `NODE_VERSION` = `22`
4. Deploy. Note the URL, e.g. `https://clinic-network-os.<account>.workers.dev`.

### 4. Close the CORS loop

Render dashboard → `cnos-api` → Environment →
`CORS_ORIGINS` = `["https://<your-worker>.workers.dev"]` (JSON array, exact
origin, no trailing slash) → save (triggers redeploy).

### 5. Verify the live round trip

Open the Pages URL → API health shows `ok` → **Sign in (dev token)** → the
web → api → db message renders with live database time. Phase 0 exit criterion met.

## Steady state

- Merge to `main` ⇒ Render rebuilds the API image; Pages rebuilds the web.
  Nothing to click.
- Migrations run at API boot (`alembic upgrade head` in the container CMD) —
  keep them fast and idempotent; merged migrations are immutable (CLAUDE.md §3).
- Secrets live only in the Render/Pages dashboards. Never in the repo, never in
  logs.

## Phase 1 flip (when real auth lands)

Set Render `ENVIRONMENT=prod` — this hard-disables `/api/v1/auth/dev-token`.
Until then the deployed instance runs `dev` deliberately: the demo needs the
dev-token flow and all data is synthetic (see ADR-0007).

## Current deployment (2026-08-05)

- Web: https://aesthetic-enterprises-demo.singhkudrat59.workers.dev (Cloudflare
  named the worker after the repo — dashboard project name wins over
  `wrangler.jsonc` for Git-connected projects)
- API: https://cnos-api.onrender.com
- DB: Neon project `clinic-network-os`, us-west-2. Note: Neon provisioned
  **Postgres 18** (their default) while CI/local run 16 — nothing we use differs
  yet; align CI/local to 18 if drift ever matters.

## Troubleshooting

- **Web shows "unreachable"**: check CORS_ORIGINS matches the exact Pages origin;
  check the Render service isn't failing health checks (Logs tab).
- **API boot loop with DB errors**: DATABASE_URL not converted for asyncpg
  (`sslmode`/`channel_binding` params must be replaced with `ssl=require`).
- **Stale web after API change**: Pages only rebuilds on repo pushes — a
  Render-side env change doesn't rebuild the web. Re-deploy from the Pages
  dashboard if needed.
