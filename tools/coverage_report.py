"""Generate a factual ledger from the local collector's observations (no network)."""
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import moviecache as m

if __name__=='__main__':
    lines=['# Coverage ledger','','Generated from local observations; this is **not exhaustive Prague coverage**.',
           'The denominator includes the original 25 venues plus six discovered regular venues.',
           'Seasonal/cultural venues below remain a separate unresolved audit scope.',
           '', '| Venue | Adapter / disposition | Last success (UTC) | Observed dates | Total / confirmed / unknown / conflict | Source |',
           '|---|---|---|---|---|---|']
    with closing(m.connect('data/cache.sqlite')) as db:
        for v in m.registry():
            r=db.execute('SELECT * FROM programme_runs WHERE venue_id=?',(v['id'],)).fetchone()
            if r:
                rows=json.loads(r['records_json']);dates=json.loads(r['dates_json']);counts=Counter(x['access'] for x in rows)
                numbers=f"{len(rows)} / {sum(counts[a] for a in m.ACCESSIBLE)} / {counts['unknown']} / {counts['conflict']}"
                horizon=f'{dates[0]} – {dates[-1]} ({len(dates)} dates)';checked=r['checked_at']
            else:numbers='—';horizon='Not established';checked='Never'
            disposition=v['adapter']+(' — '+v['blocker'] if v.get('blocker') else '')
            lines.append(f"| {v['name']} | {disposition} | {checked} | {horizon} | {numbers} | [Official]({v['url']}) |")
    lines += ['', '## Language and source evidence', '',
      '- Cinema City: official `data-api-service/v1/quickbook/10101/film-events/in-cinema/ID/at-date/DATE` supplies session `languages.original`, `dubbed`, `voiceover`, `subtitles`. These override film metadata. Empty future responses do not establish publication.',
      '- CineStar: official SSR Nuxt `scheduledEventsEntries`, `cinemaHallsEntries`, and public version-specific movie detail pages provide IDs, times, halls and version titles. Only explicit session labels `ENG + CZ titulky`, `CZE + ENG titulky`, or `ORIGINAL + ENG titulky` establish English. Generic `Titulky` stays unknown; `Dabing` excludes without English subtitles. The official `movieTags` legend was inspected. Links open the version programme, not a guessed checkout.',
      '- Aerokina: screening-specific JSON-LD Events and `program__tag` labels. `ENG` invokes the site’s English Friendly filter; it does not establish the audio/subtitle split.',
      '- Other ten source families, legends, identity fallbacks and year-inference limits: [source notes](SOURCE_NOTES_HTML.md).',
      '- Rows include non-English and unknown sessions for audit. Counts above cover each published horizon, not just tonight; non-film classification is incomplete and not an attendance guarantee.',
      '', '## Audit and unresolved venues', '',
      'Checked official [Prague City Tourism cinemas](https://prague.eu/en/objevujte-kategorie/cinemas/) (33 entries, including cultural/seasonal sites), plus independent [Kinomaniak](https://kinomaniak.cz/kina/mesto/praha), [Kinobox](https://www.kinobox.cz/kino_program) and [GoOut](https://goout.net/en/prague/cinemas/lvznyvlkkzw/) discovery results on 2026-10-24. Search results can be old and conflicting; they are not screening evidence.',
      '', 'New regular venues: Balt is collected; Petřiny, Ústřední knihovna, Za plotem, Horní Počernice and KC Beseda have explicit unfinished registry entries. They are **implementation gaps**, not access restrictions or completed dispositions.',
      '', 'Seasonal/cultural candidates discovered, not yet individually verified or collected: DOX, Cross Club, Gabriel Loci, Holešovice Market, Karlín Barracks, Kepler, Klubovna, MeetFactory, Kinský Garden, Pragovka, Spojovna, Sunset Cinema, Kinobus, Stalin, Žluté lázně, Střelecký ostrov, 3Kino, Biotop, botanical garden, CAMP, Hostivař outdoor, Invalidovna, Jasoň, Kamínka, Lysolaje, Devítka, Statek, Port7, Řepy, Skautský institut, Ďolíček, V podzámčí, Veletržní palác, Vypich, Zahrada and Výletní kino Smíchov. No claim of seasonal closure is made merely because it is October. A directory’s “active” tag is not verified current operation. These gaps prevent an exhaustive/citywide-complete claim.',
      '', '## Coordinates', '',
      'All original 25 now have coordinates. Missing seven were checked against official Prague City Tourism map data on 2026-10-24; Aero, Flora and Světozor seed markers were corrected. Other original seed coordinates remain approximate, not independently reverified marker positions. Balt and four newly discovered venues remain unmapped; Za plotem uses official directory coordinates. Modřany’s address conflicts between directories and remains explicitly flagged. Static coordinates are never re-geocoded on search.',
      '', '## Restrictions and follow-up', '',
      'Evald, Modřany and Radotín returned HTTP 429 in the bounded October 24 audit, with unavailable robots responses. Their collection is deferred, not bypassed or called closed. Recheck access restrictions conservatively before adding their collectors. Raw captures remain private local diagnostic files, outside Git. Public source links and normalized facts do not establish permission for bulk redistribution.',
      '', 'Cloud CPU limits, real deployed scheduling, private UI admission and Hermes installation remain separate deployment gates; see [validation](VALIDATION.md).']
    Path('COVERAGE.md').write_text('\n'.join(lines)+'\n')
