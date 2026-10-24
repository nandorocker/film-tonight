# Validation — 24 October 2026

## Current outcome

The cached Pages/D1 service is deployed at **https://film-tonight.pages.dev/**.
All 23 supported collectors published successfully in a manual cloud run starting
`2026-10-24T21:11:34.023467+00:00`. The public repository is
https://github.com/nandorocker/film-tonight. Hosted collection/schedule verification
is recorded below as it completes. No paid plan was enabled; account subscription
metadata was inaccessible (403), and actual edge CPU/quota headroom is unverified.
Docker startup/recreation, the local emulator and personal Hermes integration
were also tested. No Hermes restart or Windy production scheduler was added.

The scanner verified this temporary Tailnet-only preview:
`https://windy.tail1fe933.ts.net:5175/`. It proxies the loopback Pages emulator on
8788. No Caddy/tunnel/landing configuration was modified. Built-in browser tools
reported no connected desktop, so Chromium Playwright verified the local app.

## Checks actually executed

| Check | Result |
|---|---|
| Starter `python3 -m unittest discover -s tests -v` | Original 12 tests passed before edits |
| Current Python offline suite | 53 tests passed, 0.608 s in recorded final unit run |
| `npm test` | 16 tests passed; shared filtering, D1-compatible SQL, ordering, auth, jobs and privacy |
| `npm run build` | Successful; vendored Leaflet and separate historical demo |
| `npx playwright test` | 5 tests passed, 4.5 s in recorded run |
| `npm audit` after `undici` override | Zero known reported vulnerabilities |
| `docker compose config --quiet` | Successful |
| `docker build -t film-tonight:local .` | Successful, non-root runtime image |
| Isolated Docker startup | API ready, 31 registry venues, empty cache; `--network none`, no public listener/provider requests |
| Container removal/recreation with named volumes | Sanitized D1 smoke fixture and SQLite marker survived; temporary container and test volumes then removed |
| SQLite backup/restore | `Connection.backup()` retained all 23 programme rows; restored `PRAGMA integrity_check` returned `ok` |
| Real MCP subprocess smoke | Initialize + tools/list + search + coverage + refresh returned 5 responses, 3 tools, no tool errors; refresh queued |
| Real local collection after MCP request | 23 supported venue observations published; completion route executed; failures would remain separate |
| `git diff --check` | Passed after inspected implementation changes |

MCP was tested with a temporary synthetic private configuration against the real
local API. The personal Hermes skill/client was subsequently installed with a
UID-10000, mode-0600 private configuration. Native skill discovery found one match;
the native one-shot response returned five correct-date cached screenings, official
links, check times and 20/31 fresh coverage, distinguished English-friendly tags,
and disclosed neither the home address nor coordinates. No MCP registration or
all-profile gateway restart was needed. The real personal home was not placed in the
repository, demo, public assets, request URLs or test fixtures. Regression tests
verify private configured coordinates are absent from search/coverage output and
are supplied to the shared selector over stdin, not process arguments.

### Browser cases

Historical demo table and banner, client-side title filter, map opening and
venue/popup selection, official ticket links, 390px viewport without document
overflow, empty cache, failed initial fetch, failed later fetch with last-good
rows, blocked basemap requests retaining the table, delayed A→B→A date responses,
and a date change during first load. A separate real-data Chromium run displayed
75 upcoming rows with one API request and captured the rendered live page.

No blanket claim is made that every acceptance case has been covered. Notably,
film grouping is absent; the UI is a flat table. Manual neighborhood geocoding,
Telegram location requests, automatic map opening and private UI admission are
not implemented. Geolocation is deliberate opt-in and not persisted.

## Live collection evidence

An actual complete local publication run started at
`2026-10-24T17:13:54.361911+00:00`; source checks ranged from
`17:13:55.201173` to `17:14:36.363035` UTC. All 23 supported collectors returned
parseable observations, with **2,860 records across their published horizons** at
that run. These are not all tonight, not all movies, and not all English-accessible.
One later targeted Edison/Kino35 verification after language fixes changed the
current observed count as sessions elapsed; live counts are not permanent tests.

Original inventory: 22 of 25 have functioning collectors; Evald, Modřany and
Radotín had evidenced HTTP 429/unavailable robots responses. Balt adds a 23rd
collector. Five newly discovered regular venues still lack collectors. Seasonal
and temporary venue audit remains unfinished. See the explicit registry entries
and [coverage ledger](COVERAGE.md). Do not call these unsupported entries completed
dispositions, and do not call the output exhaustive.

Representative fixtures are small attributed synthetic structures, not wholesale
redistributions of captured cinema websites. Captured official HTML/JSON was also
parsed locally; source-family counts, language legends, identities and date
limitations are in [SOURCE_NOTES_HTML.md](SOURCE_NOTES_HTML.md). A complete manual
all-sessions comparison for every source family is **not yet established**.

The public Cinema City response was checked for event-level language fields.
CineStar's public SSR events, hall IDs, version metadata and tag legend were
inspected. Generic CineStar `Titulky`, MAT programme entries and Premiere `tit`
do not prove English audio; uncertainty is retained and excluded from confirmed
matches. Some source feeds may omit already-started screenings; disabling the
remaining filter cannot reconstruct earlier source records.

## Performance measurements

Host: Intel Core i7-8750H at nominal 2.20 GHz, 12 logical CPUs, Linux
6.12.111+deb13-amd64, glibc 2.41; Node 24.15.0, native Python 3.13. Hardware is an
existing laptop/server, not an independently benchmarked generic small VM.

`python3 tools/benchmark.py http://127.0.0.1:8788 --count 100` against the complete
collected cache, with the dated D1 projection:

- Median **42.91 ms**, p95 **50.90 ms**, min 41.19 ms, max 113.37 ms.
- 100 sequential HTTP requests, first request included; service/database had
  already been used (warm server/cache). No assertion of a cold-process benchmark.
- Included loopback HTTP, local Pages/Workerd emulator, D1 SQLite query, shared
  selection, response transfer and JSON decoding.
- Returned 72 remaining confirmed showtimes at measurement time, 22/31 venues
  fresh for that date. Balt's first advertised date was October 26, so successful
  collection does not imply fresh October 24 coverage.
- Excluded provider refresh, Internet latency, browser rendering, agent/model
  generation and actual remote Cloudflare CPU accounting.

One separate Chromium real-data run measured **650.64 ms** navigation-to-visible
table (75 rows), with one API request. This is one observation, **not a UI p95**.
The 5 browser tests verify lazy map interaction and fallback, not a measured remote
basemap p95. The five-second map target remains a remote acceptance gate.

Offline tests forbid network on cached query paths and hold a collection worker
waiting while an independent SQLite reader finishes under 200 ms. This proves
read/collection separation in the tested native path; it does not measure every
source-outage or cloud-concurrency scenario.

## Independent reviews and fixes

- Architecture challenge recommended Python Actions → authenticated ingestion →
  atomic D1 cache → Pages, with honest best-effort freshness and local-only origin.
- Deep security/correctness review found private origin in output/argv, missing
  fresh-runner collapse baseline, unbounded historical-date retention and timestamp
  format mismatches. All were accepted and corrected with regression tests. Its
  focused recheck confirmed those fixes, then identified a dated-fetch UI race;
  the race was corrected and both delayed-response browser tests passed.
- A separate source-parser review found an Edison trailing-language false-positive
  counterexample, DST duration arithmetic and combined Kino35 language-icon
  parsing. All were accepted, fixed and covered by regressions. It did not
  establish an observed live wrong-language inclusion. CineStar now has a
  synthetic session-legend/Nuxt test as well as the dated live collection.

Reviews are not substitutes for unperformed deployment/coverage gates. No claims
of model-cost savings, live free-tier headroom or production readiness are made.

## Deployed measurements and operational checks

- Production deployment: `5685ce09.film-tonight.pages.dev`; D1 in WEUR.
- Deployed Chromium: 104 rows for October 25, table visible 338.51 ms after date
  selection, 15 mapped locations, no page errors. Single observation, not a p95.
- 30 deployed API requests: median 262.14 ms, p95 424.23 ms; 104 results, 20/31
  fresh venues. Includes network round-trip and JSON decoding, not Worker CPU.
- Generic Python user-agents received edge 403/1010; descriptive `FilmTonight/1.0`
  works and is now used by publication, agent and benchmark clients.
- Focused deployment-client review accepted one diagnostic fix: a failed edge
  tail must return nonzero with a sanitized error, not silently appear successful.
- The tail captured no usable CPU events. CPU/free-tier suitability is not proven.

## Outstanding acceptance gates

1. Verify real edge CPU/headroom, source access from GitHub-hosted runners,
   scheduled execution/recovery and quota behavior. Actions timing is best effort;
   public schedules can disable after 60 days of repository inactivity.
2. Native Hermes/Telegram location handling has not been changed.
3. Finish the five known regular venue integrations and seasonal audit; recheck
   access restrictions for three blocked initial venues. Complete source-family
   all-session comparison and remaining coordinate verification.
4. Verify remaining remote mobile/failure cases, retention after downtime,
   backup/restore and user-visible freshness with the actual deployed stack.

The offline container's temporary supervised scheduler was stopped with its test
container; Windy retains development preview/API processes only. Production
collection belongs to GitHub Actions, not this host. Scheduling is best effort;
configured cron is not by itself evidence of a successful scheduled run.
