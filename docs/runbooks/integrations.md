# Runbook: funnel ingestion (webhook + CSV import)

How to exercise the two ingestion endpoints (R7, ADR-0005) against a local
stack. All example data is synthetic.

## Secrets

Set the webhook shared secret in `api/.env` (template: `.env.example`):

```sh
GHL_WEBHOOK_SECRET=dev-only-webhook-secret
```

Unset → `POST /api/v1/webhooks/ghl` answers **503** (fail closed). Restart the
API after changing it. Never commit `.env`; the secret is never logged.

## Webhook: `POST /api/v1/webhooks/ghl`

No JWT — authentication is an **HMAC-SHA256 hex digest of the raw request
body** in the `X-Webhook-Signature` header. 401 on mismatch or missing header.

### Payload shape (demo contract, defined by this repo)

```json
{
  "event_type": "contact",              // "contact" | "appointment"
  "location_id": "<our location UUID>", // licensor-configured CRM custom field
  "contact": {
    "external_id": "ghl-contact-00123", // CRM id — lead identity is (source, external_id)
    "source": "instagram_ads",
    "created_at": "2026-07-14T18:02:11Z"  // optional; naive times read as UTC
  },
  "appointment": {                      // required when event_type = "appointment"
    "external_id": "ghl-appt-00987",    // accepted, not persisted in MVP (ADR-0005)
    "scheduled_at": "2026-07-16T17:00:00Z",
    "occurred_at": null,                // optional
    "outcome": null                     // optional: "no_show" | "no_sale" | "sale"
  }
}
```

Every event embeds the full contact, so any event can create the lead.
Semantics: lead replays are no-ops (first write wins); consult replays update
only non-null `occurred_at`/`outcome` (fields gain information, never lose it).

### Send a signed test webhook (curl + openssl)

```sh
SECRET=dev-only-webhook-secret
LOCATION_ID=<any location UUID from the seed>   # e.g. via psql: SELECT id FROM locations LIMIT 1;

BODY='{"event_type":"appointment","location_id":"'$LOCATION_ID'","contact":{"external_id":"ghl-contact-00123","source":"instagram_ads","created_at":"2026-07-14T18:02:11Z"},"appointment":{"external_id":"ghl-appt-00987","scheduled_at":"2026-07-16T17:00:00Z","occurred_at":null,"outcome":null}}'

SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $NF}')

curl -s -X POST http://127.0.0.1:8100/api/v1/webhooks/ghl \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: $SIG" \
  --data-binary "$BODY"
# → {"lead_created":true,"consult_created":true,"consult_updated":false}
```

Run the exact same curl again to see idempotency:

```sh
# → {"lead_created":false,"consult_created":false,"consult_updated":false}
```

Use `--data-binary` (not `-d`) — the signature covers the exact bytes sent.

### Response and error codes

| Status | code | Meaning |
|---|---|---|
| 200 | — | Event processed; body reports created/updated flags |
| 401 | `invalid_signature` | Missing or mismatched `X-Webhook-Signature` |
| 400 | `invalid_payload` | Body isn't JSON or doesn't match the shape above |
| 400 | `unknown_location` | `location_id` isn't a known location UUID |
| 503 | `webhook_not_configured` | `GHL_WEBHOOK_SECRET` unset on the server |

## CSV lead import: `POST /api/v1/imports/leads`

**hq_admin only** (JWT required). Raw `text/csv` body. Same idempotent upsert
path as the webhook.

### Format

Header row required. Columns:

| Column | Required | Notes |
|---|---|---|
| `source` | yes | Attribution source; part of the lead identity |
| `external_id` | yes | Upstream id; part of the lead identity |
| `location_id` | yes | Our location UUID |
| `created_at` | no | ISO 8601; empty → now; naive times read as UTC |

```csv
source,external_id,location_id,created_at
walkin_event,evt-2026-001,9b2f...,2026-07-01T09:00:00Z
walkin_event,evt-2026-002,9b2f...,
```

### Import

```sh
TOKEN=$(curl -s http://127.0.0.1:8100/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"hq_admin@clinic-network-os.demo","password":"demo-hq-2026!"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl -s -X POST http://127.0.0.1:8100/api/v1/imports/leads \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: text/csv" \
  --data-binary @leads.csv
# → {"imported":2,"skipped":0,"errors":[]}
```

Re-importing the same file reports `"skipped"` instead of `"imported"`.
Malformed rows don't abort the import: they come back in `errors` with their
CSV line number, and well-formed rows still land.

| Status | code | Meaning |
|---|---|---|
| 200 | — | Import ran; body has `imported`/`skipped`/`errors` |
| 400 | `import_format` | Not UTF-8, empty, or missing required columns |
| 401 | — | Missing/invalid JWT |
| 403 | `role_forbidden` | Caller is not hq_admin |

## Tenancy note

Both paths run under the `hq_admin` RLS role (policy-level, ADR-0002 — never a
bypass): licensor-managed systems feed the funnel. Rows land with the
destination location's `org_id`, so operators see exactly their own ingested
leads/consults. Ingestion never writes royalty or supply tables (R7).
