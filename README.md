<img src="assets/icon.svg" width="64" height="64" alt="">

# Film tonight

Fast, source-labelled Prague cinema listings for a small table/map app and a
personal Hermes agent. **Live: https://film-tonight.pages.dev/ — coverage is partial.**
See [COVERAGE.md](COVERAGE.md) and [VALIDATION.md](VALIDATION.md) for actual evidence
and outstanding gates, not a promise that every Prague screening is collected.

## Run the whole local service

On Linux with Docker Compose:

```sh
docker compose up --build
```

This starts a loopback-only Pages/D1 emulator, persistent SQLite collector,
600-second scheduler and responsive UI at port 8788. It generates local credentials
without external accounts. First collection is asynchronous; the empty app remains
usable. Supervisor/container restart preserves data and rechecks sources. No demo
seed is imported. Host networking is intentional for loopback isolation; this
Compose file targets Linux, not Docker Desktop's default networking.

For native development (Node 24, Python 3.11+, system timezone data):

```sh
npm ci
python3 tools/local.py
```

To run only the app while working on it: `npm run dev`. Migrate its local database
first with `npx wrangler d1 migrations apply film-tonight --local`. To run one real
collection, use `python3 collector_job.py` (local SQLite only); publication uses
`FILM_API_URL` and `FILM_INGEST_TOKEN` from a private environment. Never put those
values in Git, a browser bundle or a command line. `.dev.vars` is ignored and mode
0600 under the local supervisor. `?demo=1` explicitly selects historical examples.

On Windy, a development-only Vite proxy can be started with `npx vite`, after
`npm run build` and the Pages emulator. Its scanner-managed Tailnet link is taken
from the Windy catalog; do not create public Caddy routes or expose a wide bind.

## Online, designed for free tiers

```text
GitHub Actions (Python, public repo, best-effort 10-minute schedule)
    → authenticated per-venue observations → Cloudflare D1
Cloudflare Pages UI + read-only Pages Functions API
    ← Hermes personal-profile client (private origin applied locally)
```

Collection is deliberately outside the Free Worker CPU budget. Dated reads are
filtered in D1, then use the same pure selector as the UI and agent. No per-query
provider scraping, model calls or venue geocoding. Data updates never rebuild Pages.
Deployed reads have been measured (see validation); Cloudflare CPU and quota
headroom **remain unverified**. Local emulator success does not establish Free-tier suitability.
Do not enable a paid plan or paid runners to conceal a quota failure.

### Deploy

1. Authenticate Wrangler: `npx wrangler login --device --browser=false`. Approval
   happens in the user's Cloudflare account, not by pasting credentials in chat.
2. `npx wrangler d1 create film-tonight`; put its returned ID in `wrangler.toml`.
   Apply `npx wrangler d1 migrations apply film-tonight --remote`.
3. `npx wrangler pages project create film-tonight --production-branch main`.
4. Set independent Pages secrets `INGEST_TOKEN` and `REFRESH_TOKEN` using Wrangler's
   private interactive secret input or secret files with mode 0600. Never use a
   Cloudflare deployment credential as an ingestion credential.
5. `npm run build && npx wrangler pages deploy dist --project-name film-tonight`.
   Use the actual returned `pages.dev` URL; do not invent one.
6. In the public GitHub repository, set variable `FILM_API_URL` to that URL and
   secret `FILM_INGEST_TOKEN` to the ingestion credential. The scheduled job is
   skipped while the URL variable is absent. Manually run the collection workflow
   once and inspect source coverage before calling scheduling active.
7. Verify unauthenticated writes fail, reads work, the UI loads on mobile, a
   scheduled run succeeds, and Cloudflare reports CPU/quota headroom. No paid
   resource or public origin routing on Windy is needed.

The simple deployment is a **public UI and public sanitized read API**, as the user
allowed when privacy would add complexity. There are no home coordinates, agent
preferences, account records or raw pages in it. Write/refresh routes require
separate secrets. Cloudflare Access may protect both UI/API later; protecting only
the HTML would not make the API private. Hermes and Actions would need compatible
machine admission before enabling such a gate.

## API and clients

All routes start `/api/v1` and return JSON with schema version 2:

| Route | Behavior |
|---|---|
| `GET /snapshot?date=YYYY-MM-DD` | Sanitized cache for one Prague date; published horizons and per-venue observations retained |
| `GET /screenings` | Defaults to remaining tonight after 18:00; confirmed English access |
| `GET /coverage` | Same selection metadata, counts, horizons, source errors, no screening array |
| `GET /map.geojson` | Same filters and rows, explicit unmapped venue IDs |
| `GET /health` | Process health, not source health |
| `GET /ready` | Database binding/schema readiness, not completeness |
| `POST /refresh` | Refresh-token protected, coalesced job ID; next scheduled collection, not immediate crawling |
| `GET /jobs/ID` | Refresh-token protected queued/complete/complete_with_errors status |
| `POST /internal/ingest` | Dedicated ingestion-token protected atomic per-venue publication |
| `POST /internal/jobs` | Ingestion-token protected completion and pruning |

Search filters: `date`, `after`, `remaining=true|false`, `buffer_minutes=0..240`,
`access=confirmed|all|english_audio|english_subtitles|english_friendly|unknown|conflict|not_english`,
`venue`, `q`, `format`. The browser and agent additionally accept local `origin`
and `radius_km`; the public API rejects origin/radius URLs. Private origin is
removed from returned filters and stdin—not argv—is used for local selection.
Distances are approximate, straight-line, rounded to 0.1 km. Radius exclusions are
explicit; no origin means citywide, not an implicit central-Prague cutoff.

The original SQLite `moviecache.py query`, `coverage`, `refresh`, `serve`, `seed`
and `watch` remain compatible. Original HTTP routes belong to its separate
loopback-only read server on port 8765, not the Pages API. Its legacy wall-clock
`--after` query does **not** imply remaining tonight; agents use the new shared
selector client instead. Existing SQLite schema upgrades are additive; a future
schema version fails rather than being silently downgraded or deleted.

### Hermes and MCP

`agent/client.py search --table` returns the cached table first. `coverage` and
`refresh` use the same service. `agent/mcp_stdio.py` exposes `search_screenings`,
`get_coverage`, `refresh_screenings` over MCP stdio (Python standard library; Node
required for the shared selector). See `agent/mcp.example.json` and
`agent/SKILL.md`. This repository is **not itself an installed Hermes skill**.

Keep profile configuration in `$HERMES_HOME/data/film-tonight/config.json` mode
0600, or select another private path through `FILM_CONFIG`:

```json
{"api_url":"https://YOUR-PROJECT.pages.dev","origin":null,"refresh_token":"SET_PRIVATELY"}
```

Install the narrow `agent/`, `tools/query.mjs`, `web/query.js` and `package.json`
plus `agent/SKILL.md` as the skill root. The personal home is configured privately,
not in this example or the public UI. Never inspect/change sibling profiles.
Hermes may research films/questions on demand after showing cached results;
Telegram location requests are not implemented. Relative dates use Europe/Prague;
English-friendly tags are not relabelled as audio/subtitles. See the skill's rules.

## Collection, retention and failures

- Each venue succeeds or fails independently. Failure and suspicious programme
  collapse preserve last good records and show the latest failed attempt.
- Atomic D1 batches replace the whole venue observation. Canonical UTC collection
  generation provides ordering/idempotency; older uploads cannot overwrite newer
  ones. Published dates absent from the new view are unpublished, not invented zero.
- Per-host minimum one-second pacing, bounded concurrency (4), 12-second requests,
  response bounds, robots checks, limited retries/backoff and Retry-After deferral.
  Robots 403/429/temporary failure defers rather than bypasses collection.
- SQLite stores normalized snapshots/attempts and only the latest raw body per
  venue. Raw bodies older than seven days are pruned; this is **not** an archive of
  every raw capture. Old historical service dates/versions are pruned after 30 days;
  the latest current/future snapshot and one last-good venue programme remain.
- D1 stores current normalized programmes plus one normalized daily observation
  per venue, retained 30 days. No raw bodies or private origin. History pruning
  runs after collection; a stopped scheduler cannot prune itself.
- Freshness is 900 seconds; stale results stay readable. A new API generation
  timestamp is not a new source check. Source prices/availability are observations,
  never a ticket or seat guarantee.
- GitHub Actions scheduling can delay/drop and public schedules can disable after
  60 days without repository activity. Monitor timestamps, inspect workflow status,
  and manually reactivate/recover; there is no strict ten-minute guarantee.
- Cloud runners retain normalized comparison baselines from the previous seven
  dated cloud snapshots. Raw/conditional-response caches persist in native/Docker
  SQLite, **not** across fresh GitHub runners. This tradeoff is explicit.

## Backup and restore

Local: use Python's SQLite `Connection.backup()` for `data/cache.sqlite` (WAL-safe),
and back up the persisted emulator state while the local stack is stopped. Copy
private `.wrangler/local-secrets.env` separately, never into a public artifact.
Do not back up only the main SQLite file while writes are active.

Cloud: `npx wrangler d1 export film-tonight --remote --output /private/backup.sql`.
Restore into a **new** D1 database with `wrangler d1 execute NEW --remote --file`
and test it before changing the binding. Never automatically delete/overwrite a
user database. Pause collection for a consistent cutover. Keep rollback bindings,
previous Pages deployment and secrets privately; resume collection after verifying
last-good data and denied unauthenticated writes.

## Verify

```sh
npm ci
npm test
python3 -m unittest discover -s tests -v
npm run build
npx playwright install chromium
npx playwright test                # running local Pages emulator required
python3 tools/live_smoke.py --venue kino-aero  # explicit network opt-in
python3 tools/benchmark.py http://127.0.0.1:8788 --count 100
```

CI is offline with respect to cinema sources. `package-lock.json` pins Node
dependencies; Python collection/MCP use the standard library. `undici` is pinned
through an override for Wrangler's transitive advisories. Basemap tiles are loaded
on demand from OpenStreetMap with attribution and without offline/bulk caching;
failed map loading leaves the table and directions usable.
