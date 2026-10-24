# Implementation checklist

- [x] Inspect supplied starter and reproduce its 12 offline tests.
- [x] Read Windy/Hermes operating and privacy rules.
- [x] Architecture challenge: Python Actions collector, atomic D1 publication, Pages UI.
- [x] Audit sources and document known coverage boundaries (audit completion still open).
- [x] Preserve SQLite CLI; add 23 live venue collectors, locking, retention and publication.
- [x] Versioned cached API, shared browser/edge filtering, table and map.
- [x] Portable Hermes client/MCP and table-first instructions; personal-profile skill installed and native smoke passed.
- [x] Offline resilience/security tests, live source checks, browser checks and reviews.
- [x] Pages/D1 deployed at https://film-tonight.pages.dev/ with separate write credentials.
- [x] GitHub-hosted collection/publication and offline CI passed; operational docs updated.
- [ ] Observe an actual scheduled event and verify edge CPU/quota headroom.

The UI may be public, but private home configuration is only on the Hermes
personal profile. No credentials or private origins belong in this repository.
Cloudflare authentication succeeded. Actions scheduling is best effort,
not a ten-minute freshness guarantee. No paid plan was enabled; edge CPU/quota
headroom remains unverified.
