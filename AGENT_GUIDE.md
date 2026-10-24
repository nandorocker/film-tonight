# Agent contract: Prague movie listings

This is an integration guide, not an installed ChatGPT skill. Use it as instructions for your own agent, or later wrap these commands in an MCP server.

## When asked what is playing

1. Resolve the date in Europe/Prague. Query local data immediately: `python moviecache.py query --date YYYY-MM-DD --after HH:MM --format json`.
2. Show a short table first: start, title, venue, English access and freshness. Do not wait for research or map rendering. For `sample` or `stale`, state its timestamp clearly. If the cache is missing, say so; do not fabricate a list.
3. Inspect coverage. Run `python moviecache.py refresh --date YYYY-MM-DD` if supported providers are stale/missing. Do not repeatedly retry failed providers within the same turn. Re-query after the refresh.
4. For unsupported venues, use targeted live research only when broader coverage is necessary. Keep that research visibly separate from automated collector coverage. Report gaps instead of claiming completeness.
5. Render a map from `query --format geojson` after the table. Choose a few films using the user's mood, timing, travel preferences and screening format.

## Required interpretation

- `english_audio`, `english_subtitles`, `english_friendly` qualify. `unknown`, `conflict`, `not_english` do not qualify as confirmed matches.
- Do not relabel `english_friendly` as “English audio” or “English subtitles” without additional screening-specific evidence.
- An English-language title, English website or American production country does not prove the screening's language.
- Showtimes are timezone-aware. Convert to Europe/Prague for display. Consider travel time before recommending an imminent start.
- Never imply cached availability guarantees admission. Check the official booking page for a final shortlist.
- Preserve `source_url`, `booking_url`, `checked_at`, `freshness`, `origin` and `language_evidence` when citing or transforming results.
- State coverage honestly: this starter has five live collectors. Historical example data covers more venues but is not live evidence.

## Fast response policy

The first read is local and should not require web searches. Show it before refreshing. If the user needs an immediate decision, choose from adequately fresh supported venues; offer broader coverage only if useful. Reuse static coordinates and map assets; do not geocode venues or redraw a basemap from scratch for each request.
