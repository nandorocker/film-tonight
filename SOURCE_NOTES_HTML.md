# Official HTML adapters

Implemented from official captures dated 2026-10-24; adapters
perform no network access. Committed fixtures are tiny **synthetic** examples,
attributed in HTML comments or JSON fixture metadata, not copied programme pages or current listings.

| Adapter key | Official source / structure |
| --- | --- |
| `atlas` | kinoatlaspraha.cz — `program-id-*` rows, full local datetime, hall, session language tags; sold-out rows can have only a detail link |
| `pilotu` | kinopilotu.cz — ordered day/event swiper slides, session detail IDs, explicit parenthesized screening language suffixes |
| `kavalirka` | kinokavalirka.cz — dated accordion items, screening tags, buy/detail event links; newsletter accordion excluded |
| `kino35` | kino35.ifp.cz — dated table headers, screening audio/subtitle icons, full `perfbegin` booking datetime cross-check |
| `ponrepo` | nfa.cz — event IDs and offset timestamps, explicit English Friendly label; country/year and unlabelled Czech field are not audio evidence |
| `edison` | edisonfilmhub.cz — JSON-LD Event arrays, startDate arrays and explicit `Sub.` language codes in programme descriptions |
| `mat` | www.mat.cz/kino/cz/kino-mat — ordered `cinema1` programme cards, `data-definitionid` screening IDs, explicit times and buy/detail links |
| `premiere_hostivar` | www.premierecinemas.cz — Praha Hostivař page title required; date tabs joined to their own panels, advance dates read from each film row |
| `dlabacov` | dlabacov.cz public WP JSON endpoint — nested explicit year/month/day keys, GoOut screening IDs, programme audio labels |
| `balt` | canonical kinobalt.cz — `c-Screening` ScreeningEvent microdata only, full local timestamps, hall and session language labels |

## Additional source discovery (2026-10-24)

- MAT's previously supplied capture was a single film detail. The programme
  entrypoint `https://www.mat.cz/kino/cz/kino-mat` was fetched successfully using
  `moviecache.fetch`, including its robots checks, response bound and pacing.
  Programme cards expose no screening-language labels; original-language titles
  beneath Czech titles are **not** used as audio evidence. Blank-time cards with
  no ticket link are advance announcements, not midnight screenings or empty-day
  evidence. Buyless timed cards remain auditable via the film-detail URL.
- Premiere's supplied capture identifies **Praha Hostivař** in its document title.
  No complete screening-date attributes were found. Ordinary schedules have
  yearless dated tabs; the advance-sale panel has yearless dates inside each row.
  Film release dates elsewhere on the page are not schedule dates. Unpublished
  future panels explicitly say the next week's programme will be announced;
  these navigation dates are excluded. Version `tit` and `cz` remain raw unknown
  evidence: neither proves English audio or English subtitles.
- Dlabačov's supplied root is a Vue shell, not a programme. Its loaded public
  `https://dlabacov.cz/wp-content/themes/sage/dist/scripts/main_36cc23d4.js`
  explicitly registers route `bitterend/v1/events` + `/list` and passes
  `language`. The root declares base URL `https://dlabacov.cz/wp-json`.
  **Fetch input for adapter `dlabacov`:**
  `https://dlabacov.cz/wp-json/bitterend/v1/events/list?language=cs`.
  This endpoint returned public programme JSON successfully without cookies,
  nonces or authentication, using `moviecache.fetch` robots checks. No guessed
  GoOut feeder parameters or access bypass was needed. The same loaded JS renders
  each entry's `audio` as `Audio: ...`, language ID 66 as dubbing and 67 as generic
  subtitles (`čt/sub`), not English subtitles. Unrecognised audio labels yield
  unknown access. Explicit `DIVADLO` entries are non-film.
- Balt uses the supplied public HTML capture. Canonical source/booking fallback
  is `https://kinobalt.cz/`, not an alternate domain. Marketing Blockbuster cards
  are excluded. `CZ titulky` alone leaves access unknown; `CZ dabing` / `SK Dabing`
  are explicit screening dubbing evidence. Film-country metadata is ignored.

## Limits

- Yearless Pilotů, Kavalírka, Kino35 and Premiere headings use the nearest year within 62
  days of the requested date. This is a bounded inference, not a source year.
  Captures outside this horizon fail; no machine-clock inference is made.
- MAT's first yearless date is anchored by the same 62-day rule. Its ordered
  programme then rolls into the next year only when month/day decreases, with
  a maximum 366-day programme span. This supports its explicit next-season opera
  schedule but remains an inferred year; no film-release year is substituted.
- Publication dates come only from dated structures actually present. Only
  Pilotů's explicitly paired empty day slide, Kino35's empty dated header,
  Premiere's dated table, and Dlabačov's explicit empty dated JSON list can
  establish a published empty day; missing dates are not treated as empty.
- Generic booking pages are not proof of ticket availability. Edison JSON-LD
  offers often link to `/program`; row identity uses the source film URL and
  start instead. No hall is exposed in those Event objects. Duplicate identities
  fail rather than merging potentially separate screenings.
- Premiere exposes no hall or screening ID on non-bookable time spans. Their
  fallback identity includes source film URL, start, version and format; bookable
  links use `/vstupenky/ID/`. Duplicate fallback identities fail closed. Balt's
  identity includes booking URL (or canonical programme fallback), start and hall.
- Unknown/non-English language sessions remain in results. Country, title,
  website language and original film language do not qualify a session. Only
  explicit parenthesized language labels in session names are consumed.
- Standalone concert/discussion titles with an explicit `:` or dash prefix are
  marked non-film; film-plus-discussion titles remain films. Other event types
  are not comprehensively classified.
- These adapters do not establish full venue coverage or future publication
  completeness. Registry/download integration is deliberately outside this file
  scope; Dlabačov requires its public JSON input rather than the root HTML shell.
