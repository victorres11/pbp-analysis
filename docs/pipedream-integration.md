# Pipedream Webhook Bridge for Coach DB → pbp-analysis

> Research / documentation only (no implementation).

## Goals
- Accept Coach DB webhook events in Pipedream.
- Transform payloads into the minimal refresh request needed by pbp-analysis.
- Trigger `data.json` regeneration (via an external runner/CI) when relevant changes occur.

## Architecture (text-based)
```
Coach DB
  └─ Webhook (HTTPS POST)
        │
        ▼
Pipedream HTTP Trigger Workflow
  ├─ Step 1: Validate auth + signature
  ├─ Step 2: Normalize / transform payload
  ├─ Step 3: De-dup / debounce (optional)
  └─ Step 4: Trigger data refresh runner
        │
        ▼
Refresh Runner (CI / server / container)
  ├─ Pull latest pbp-analysis + pbp-parser + PDFs
  ├─ Run: python3 generate_data.py
  └─ Publish data.json (commit, artifact, or deploy)
        │
        ▼
Static App (index.html + data.json)
```

## Coach DB webhook payload structure (needs confirmation)
No public payload spec is available in this repo. Please provide a sample payload or API docs so the mapping below can be finalized.

**Minimum fields needed for a safe refresh decision:**
- Event metadata: `event_type`, `event_id`, `occurred_at` (or `created_at`)
- Entity identifiers: `game_id`, `team_id`, `season_id`
- Change summary (optional): `fields_changed`, `source`

**Proposed normalized internal shape (example):**
```json
{
  "event_type": "game.updated",
  "event_id": "evt_123",
  "occurred_at": "2026-02-13T17:05:12Z",
  "season_id": "2025",
  "game_id": "asu-2025-08-30",
  "team_id": "asu",
  "fields_changed": ["plays", "score"],
  "raw": { /* original payload */ }
}
```

## Pipedream transformation logic needed
**Assumptions (to be verified once payload is known):**
- Only a subset of webhook events should trigger refresh (e.g., game score updates, PBP corrections).
- Multiple events may fire in a short window; debounce or collapse duplicate refresh requests.

**Proposed logic:**
1. Parse JSON body from `steps.trigger.event.body`.
2. Validate auth and (if available) signature.
3. Map Coach DB payload → normalized shape.
4. Filter on `event_type` allowlist.
5. Build a refresh request payload for the runner (e.g., season + game ids).
6. Call refresh runner endpoint with a signed token.

## How to trigger `data.json` regeneration
The current repo generates `data.json` by running `python3 generate_data.py`, which relies on the `pbp-parser` repo located at `../pbp-parser` and the PDF data directories referenced by that repo.

**Practical trigger options:**
- **CI workflow dispatch** (recommended): Pipedream calls a CI workflow (GitHub Actions, etc.) that:
  1) checks out `pbp-analysis` and `pbp-parser`,
  2) runs `python3 generate_data.py`,
  3) commits/publishes the new `data.json`.
- **Dedicated refresh service**: a small server/container with `pbp-parser` + PDFs mounted. Pipedream calls its authenticated endpoint.
- **Queue + worker**: if events are frequent, push a job to a queue and let a worker do batch refreshes.

## Webhook endpoint setup (Pipedream)
- Create a new **Workflow** with an **HTTP trigger**.
- Enable auth on the HTTP trigger (custom static token or OAuth) and restrict IPs if Coach DB supports static IPs.
- Consider sending `x-pd-nostore: 1` for sensitive payloads to avoid event storage.
- Return a fast 2xx response, and run refresh async if possible (`$.respond({ immediate: true, ... })`).

## Sample Pipedream workflow (Node.js)
> Illustrative only; replace `REFRESH_URL` and `REFRESH_TOKEN` with your runner endpoint.

```javascript
import { axios } from "@pipedream/platform";

export default defineComponent({
  props: {
    refreshUrl: { type: "string", default: process.env.REFRESH_URL },
    refreshToken: { type: "string", default: process.env.REFRESH_TOKEN },
    allowedEvents: { type: "string[]", default: ["game.updated", "play.updated"] },
  },
  async run({ steps, $ }) {
    const payload = steps.trigger.event.body || {};
    const eventType = payload.event_type || payload.type;

    if (!this.allowedEvents.includes(eventType)) {
      await $.respond({ status: 202, body: { ok: true, skipped: true } });
      return;
    }

    const normalized = {
      event_type: eventType,
      event_id: payload.id || payload.event_id,
      occurred_at: payload.occurred_at || payload.created_at,
      season_id: payload.season_id,
      game_id: payload.game_id,
      team_id: payload.team_id,
      raw: payload,
    };

    await $.respond({ immediate: true, status: 200, body: { ok: true } });

    await axios($, {
      method: "POST",
      url: this.refreshUrl,
      headers: {
        authorization: `Bearer ${this.refreshToken}`,
        "content-type": "application/json",
      },
      data: normalized,
      timeout: 10000,
    });
  },
});
```


## Platform limits to account for
- HTTP trigger rate limit averages 10 QPS; bursts may be throttled with `429` responses.
- HTTP trigger request bodies have a size limit (larger payloads require the upload-body mechanism).
- HTTP-triggered workflows default to 30s execution time; max is 5 min (free tiers) or 12.5 min (paid tiers).

## Testing approach
- Use Pipedream’s HTTP trigger test mode to send sample JSON payloads.
- Validate that auth failures return `401` / `403` quickly.
- Simulate an allowlisted event and verify the refresh runner receives the normalized payload.
- Rate-test with multiple quick events to verify debounce / dedup logic (if added).

## Security considerations
- Require auth on the HTTP trigger (custom token or OAuth). Avoid public unauthenticated webhooks.
- Verify HMAC signatures if Coach DB supports signing.
- Avoid logging sensitive payloads (`x-pd-nostore: 1` or workflow data-retention settings).
- Use secrets for tokens and rotate them periodically.
- Implement rate limiting / debounce on refresh to avoid excessive CI runs.

## Cost implications
- Pipedream Workflows use a credit-based model (credits are tied to compute time and memory).
- Free plans have daily credit limits; paid plans allow higher usage and longer execution times.
- Keep refresh work outside Pipedream (CI or worker) to avoid timeouts and unnecessary credit burn.
- Additional costs may come from CI runs / compute used to regenerate `data.json`.

## Deployment checklist
- [ ] Confirm Coach DB webhook payload + signing method
- [ ] Decide refresh runner (CI vs server vs worker)
- [ ] Create Pipedream HTTP trigger with auth
- [ ] Store refresh token in Pipedream secrets
- [ ] Implement allowlist + dedup / throttling
- [ ] Verify refresh job can run `python3 generate_data.py`
- [ ] Validate `data.json` publish path
- [ ] Monitor logs + alert on failures

## References
- Pipedream HTTP Trigger docs (auth, payload, headers, `x-pd-nostore`): https://pipedream.com/docs/workflows/steps/triggers/
- Pipedream HTTP response in workflows (`$.respond`): https://pipedream.mintlify.dev/docs/workflows/building-workflows/triggers
- Pipedream workflow limits (timeouts, QPS, payload size): https://pipedream.com/docs/limits
- Pipedream concurrency / throttling: https://pipedream.com/docs/workflows/building-workflows/settings/concurrency-and-throttling/
- Pipedream pricing / credits: https://pipedream.com/docs/pricing
- Pipedream platform axios: https://pipedream.com/docs/http
