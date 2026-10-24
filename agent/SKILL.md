---
name: film-tonight
description: Find English-accessible films and cinema showtimes in Prague, especially tonight or near the user; research films and cinema questions on demand.
---

# Film tonight

Use the personal-profile movie client, not broad web research for the first answer.
Run `python3 "$HERMES_HOME/skills/media/film-tonight/agent/client.py" search --table`.
For machine-readable results omit `--table`. `--filters '{"date":"YYYY-MM-DD","after":"18:00","buffer_minutes":30}'`
changes the search. `coverage` reads status; `refresh` queues an authenticated job.
Configuration is `$HERMES_HOME/data/film-tonight/config.json` via `FILM_CONFIG`.
Pass that path explicitly in the command environment; do not print its contents.

- Resolve relative dates at request time in Europe/Prague. Default to remaining
  tonight, with an honest departure buffer, never recommend a start in the past.
- Show the cached table first: time, film, cinema, exact English-access label,
  check age, and official booking link. Then discuss preferences/recommendations.
- Ask what neighborhood/origin to use if it is unspecified; the private configured
  home is an authorized fallback, not a public application default. Allow an
  explicit neighborhood or deliberately shared Telegram location to override it.
  Telegram location requests are NOT implemented by this skill. Never pretend
  to have live GPS, and never share a precise origin in URLs, maps or logs.
- Query citywide unless asked for a radius; rank locally by straight-line distance
  when an origin exists. No invented walking/transit times. Link directions to
  the destination only, and let the maps app resolve the user's departure point.
- Disclose fresh venues/total, missing, blocked, stale, unknown and conflict gaps.
  Never describe a partial list as “all movies.” Historical demo is not live data.
- `english_friendly` does not identify audio vs subtitles. No inference from
  country, English title, English website, or a film's general original language.
- Refresh separately, after answering; queued means next best-effort scheduled
  collection, not already updated. Re-query later and retain dated last-good data.
- UI/map use the same filters/data; share the app URL without a private origin.
- Research public official sources and trustworthy reviews on demand for plots,
  recommendations, accessibility clarification and broader coverage. Keep those
  findings separate from cached verified language/showtime evidence; cite sources.
- Never buy tickets, message anyone or change other Hermes profiles.
