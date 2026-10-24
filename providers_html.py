"""Offline adapters for official HTML programmes (structures observed 2026-10-24).

Yearless headings are resolved within 62 days of the requested date, never from
the machine clock. Missing dates are not evidence of an empty published day.
"""
from datetime import date
from hashlib import sha256
import json
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from providers import local_instant, record


def _tree(source):
    # moviecache imports provider registries; defer this import to avoid a cycle.
    from moviecache import Tree
    return Tree(source).root


def _nodes(node, cls):
    return node.all(lambda n: n.has_class(cls))


def _text(node):
    return ' '.join(node.text().split())


def _one(node, cls):
    matches = _nodes(node, cls)
    if len(matches) != 1:
        raise ValueError('Expected one ' + cls)
    return matches[0]


def _title(node):
    title = _text(node)
    if not title:
        raise ValueError('Missing screening title')
    return title


def _href(node, venue):
    return _url(node.attrs.get('href'), venue)


def _url(value, venue):
    if not value:
        raise ValueError('Missing event link')
    result = urljoin(venue['url'], value)
    if urlsplit(result).scheme not in ('http', 'https'):
        raise ValueError('Invalid event link')
    return result


def _instant(value):
    if not isinstance(value, str) or not re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}', value):
        raise ValueError('Missing full screening datetime')
    return local_instant(value)


def _yearless(value, day):
    anchor = date.fromisoformat(day)
    match = re.search(r'\b(\d{1,2})\.\s*(\d{1,2})\.', value)
    if not match:
        raise ValueError('Missing dated heading')
    dd, mm = map(int, match.groups())
    candidates = []
    for year in (anchor.year - 1, anchor.year, anchor.year + 1):
        try:
            candidates.append(date(year, mm, dd))
        except ValueError:
            pass
    candidates = [d for d in candidates if abs((d - anchor).days) <= 62]
    if len(candidates) != 1:
        raise ValueError('Yearless date outside supported 62-day horizon')
    return candidates[0].isoformat()


def _start(day, clock):
    if not re.fullmatch(r'\d{1,2}:\d{2}', clock):
        raise ValueError('Missing screening time')
    return local_instant(day + 'T' + clock.zfill(5))


def _labels(raw):
    """Only explicit session labels, never nationality or original film language."""
    text = raw.lower()
    return dict(
        subtitles=['en'] if re.search(r'english subtitles|anglické titulky', text) else [],
        dubbed=['cs'] if 'český dabing' in text else [],
        friendly=bool(re.search(r'english[ -]friendly', text)), raw=raw)


def _identity(booking, start, hall=None):
    if not booking:
        raise ValueError('No stable screening identity')
    return sha256(json.dumps([booking, start.isoformat(), hall]).encode()).hexdigest()[:24]


def _name_labels(title, tags=''):
    labels = _labels(' | '.join(re.findall(r'\(([^()]*)\)', title)) + ' | ' + tags)
    labels['raw'] = title + (' | ' + tags if tags else '')
    return labels


def _row(venue, provider_id, title, start, **kwargs):
    if not isinstance(title, str) or not title.strip():
        raise ValueError('Missing screening title')
    row = record(venue, provider_id, title, start, **kwargs)
    # Deliberately anchored: a film followed by a discussion is still a film.
    if re.match(r'^(?:koncert|concert|diskuse|diskuze|discussion|debata)\s*[:–—-]', title, re.I):
        row['event_type'] = 'non_film'
    return row


def _finish(dates, rows):
    if not dates:
        raise ValueError('Programme dates missing; refusing empty success')
    ids = set()
    for row in rows:
        if row['id'] in ids:
            raise ValueError('Duplicate screening identity; refusing silent merge')
        ids.add(row['id'])
    return dates, rows


def parse_atlas(source, venue, day):
    dates, rows = set(), []
    for node in _tree(source).all(lambda n: n.has_class('line') and
                                  n.attrs.get('id', '').startswith('program-id-')):
        start = _instant(node.attrs['data-program-date'])
        title = _title(_one(node, 'title'))
        buys = _nodes(node, 'buy')
        if len(buys) > 1:
            raise ValueError('Ambiguous Atlas booking')
        title_links = _one(node, 'title').all(lambda n: n.tag == 'a')
        if not buys and len(title_links) != 1:
            raise ValueError('Atlas event link missing')
        booking = _href(buys[0] if buys else title_links[0], venue)
        buy_date = buys[0].attrs.get('data-program-date') if buys else None
        if buy_date and _instant(buy_date) != start:
            raise ValueError('Atlas booking date mismatch')
        if _text(_one(node, 'time')) != start.strftime('%H:%M'):
            raise ValueError('Atlas display time mismatch')
        labels = ' | '.join(n.attrs.get('title', '') or _text(n)
                            for n in _nodes(node, 'language'))
        rows.append(_row(venue, node.attrs['id'].removeprefix('program-id-'),
                         title, start, hall=_text(_one(node, 'location')),
                         booking=booking, **_labels(labels)))
        dates.add(start.date().isoformat())
    return _finish(dates, rows)


_MONTHS = ('ledna', 'února', 'března', 'dubna', 'května', 'června',
           'července', 'srpna', 'září', 'října', 'listopadu', 'prosince')


def parse_pilotu(source, venue, day):
    root = _tree(source)
    headings = root.all(lambda n: n.has_class('swiper-slide') and n.has_class('day'))
    slides = root.all(lambda n: n.has_class('swiper-slide') and n.has_class('event'))
    if not headings or len(headings) != len(slides):
        raise ValueError('Pilotů day/event slide mismatch')
    dates, rows = set(), []
    for heading, slide in zip(headings, slides):
        match = re.search(r'(\d{1,2})\.\s*(' + '|'.join(_MONTHS) + r')\b', _text(heading))
        if not match:
            raise ValueError('Pilotů date missing')
        published = _yearless(f'{match[1]}. {_MONTHS.index(match[2]) + 1}.', day)
        dates.add(published)
        for item in slide.all(lambda n: n.tag == 'li'):
            content = _one(item, 'program__content-wrap')
            links = content.all(lambda n: n.tag == 'a' and
                                re.fullmatch(r'/detail/\d+', n.attrs.get('href', '')))
            times = content.all(lambda n: n.tag == 'em')
            if len(links) != 1 or len(times) != 1:
                raise ValueError('Malformed Pilotů screening')
            title = _title(links[0])
            start = _start(published, _text(times[0]))
            buy = _nodes(item, 'button-buy-small')
            booking = _href(buy[0] if buy else links[0], venue)
            rows.append(_row(venue, links[0].attrs['href'].split('/')[-1], title,
                             start, booking=booking, **_name_labels(title)))
    return _finish(dates, rows)


def parse_kavalirka(source, venue, day):
    dates, rows = set(), []
    for item in _nodes(_tree(source), 'page__program-item'):
        if _nodes(item, 'page__newsletter-form'):
            continue
        published = _yearless(_text(_one(item, 'page__program-term')), day)
        start = _start(published, _text(_one(item, 'page__program-hours')))
        title = _title(_one(item, 'page__program-name'))
        links = item.all(lambda n: n.tag == 'a' and
                         n.attrs.get('href', '').startswith('/cs/koupit/'))
        if not links:
            links = item.all(lambda n: n.tag == 'a' and
                             n.attrs.get('href', '').startswith('/cs/udalost/'))
        if len(links) != 1:
            raise ValueError('Kavalírka booking missing or ambiguous')
        booking = _href(links[0], venue)
        tags = ' | '.join(_text(n) for n in _nodes(item, 'page__program-tag'))
        rows.append(_row(venue, _identity(booking, start), title, start,
                         booking=booking, **_name_labels(title, tags)))
        dates.add(published)
    return _finish(dates, rows)


def parse_kino35(source, venue, day):
    dates, rows, published = set(), [], None
    for tr in _tree(source).all(lambda n: n.tag == 'tr'):
        if tr.has_class('header'):
            published = _yearless(_text(tr), day)
            dates.add(published)
        elif _nodes(tr, 'time') or _nodes(tr, 'name') or _nodes(tr, 'ticket'):
            if not published:
                raise ValueError('Kino35 screening without heading')
            title = _title(_one(tr, 'name'))
            start = _start(published, _text(_one(tr, 'time')))
            booking = _href(_one(tr, 'ticket'), venue)
            full_date = parse_qs(urlsplit(booking).query).get('perfbegin', [])
            if len(full_date) != 1 or _instant(full_date[0]) != start:
                raise ValueError('Kino35 booking date mismatch')
            audio = [code.strip().lower() for n in _nodes(tr, 'ico-sound') for code in re.split(r'[,/]', _text(n)) if code.strip()]
            subs = [code.strip().lower() for n in _nodes(tr, 'ico-sub') for code in re.split(r'[,/]', _text(n)) if code.strip()]
            raw = ' | '.join((n.attrs.get('title', '') + ': ' + _text(n)).strip()
                             for n in tr.all(lambda n: n.has_class('ico')))
            row = _row(venue, _identity(booking, start), title, start, booking=booking,
                       audio=audio, subtitles=subs, friendly=bool(_nodes(tr, 'ico-english')), raw=raw)
            price = _nodes(tr, 'price')
            if price:
                match = re.fullmatch(r'(\d+)\s*Kč', _text(price[0]))
                if match:
                    row['price'] = int(match[1])
            rows.append(row)
    return _finish(dates, rows)


def parse_ponrepo(source, venue, day):
    dates, rows = set(), []
    for item in _nodes(_tree(source), 'event-item'):
        start = _instant(item.attrs['data-time'])
        provider_id = item.attrs['data-id']
        if not provider_id:
            raise ValueError('Ponrepo event ID missing')
        title = _title(_one(item, 'event-item__title'))
        raw = _text(_one(item, 'event-item__details'))
        links = _nodes(item, 'event-item__btn')
        if not links:
            links = _one(item, 'event-item__title').all(lambda n: n.tag == 'a')
        if len(links) != 1:
            raise ValueError('Ponrepo event link missing or ambiguous')
        fmt = re.search(r'\b(?:\d+\s*mm|DCP)\b', raw, re.I)
        # The unlabelled country/year and "české" field are not audio evidence.
        rows.append(_row(venue, provider_id, title, start, booking=_href(links[0], venue),
                         format=fmt[0] if fmt else None,
                         friendly=bool(re.search(r'english[ -]friendly', raw, re.I)), raw=raw))
        dates.add(start.date().isoformat())
    return _finish(dates, rows)


def _edison_languages(raw):
    # Programme-description suffix, not country metadata. Preserve mixed audio
    # (including slash notation); never turn ESP/EN into English-only audio.
    code = r'(?:[A-Z]{2,4}|various)'
    codes = code + r'(?:\s*[,/]\s*' + code + r')*'
    parts = re.split(r'\bSub\.\s*', raw, maxsplit=1, flags=re.I)
    # Find the whole code field, then validate all of it. A suffix-only search
    # would incorrectly turn unsupported "FR + EN" syntax into English-only EN.
    first_code = re.search(r'(?<![A-Za-z])(?:[A-Za-z]{2,4}|various)(?![A-Za-z])', parts[0], re.I)
    audio_match = re.fullmatch(r'(' + codes + r')\s*,?\s*', parts[0][first_code.start():], re.I) if first_code else None
    sub_match = re.fullmatch(r'\s*(' + codes + r')\s*', parts[1], re.I) if len(parts) == 2 else None
    aliases = {'cz': 'cs', 'arab': 'ar', 'esp': 'es', 'swe': 'sv',
               'se': 'sv', 'dk': 'da', 'gru': 'ka'}
    def decode(match):
        if not match:
            return []
        values = [value.strip().lower() for value in re.split(r'[,/]', match[1])]
        # "various" is unspecified, not proof of exclusively non-English audio.
        if 'various' in values:
            return []
        return [aliases.get(value, value) for value in values]
    return decode(audio_match), decode(sub_match)


def parse_edison(source, venue, day):
    dates, rows = set(), []
    scripts = _tree(source).all(lambda n: n.tag == 'script' and
                               n.attrs.get('type') == 'application/ld+json')
    for script in scripts:
        data = json.loads(script.text())
        events = data if isinstance(data, list) else [data]
        for event in events:
            if not isinstance(event, dict) or event.get('@type') != 'Event':
                continue
            starts = event['startDate']
            starts = starts if isinstance(starts, list) else [starts]
            if not starts:
                raise ValueError('Edison event has no start dates')
            raw = event.get('description', '')
            audio, subs = _edison_languages(raw)
            film_url = _url(event['url'], venue)
            offers = event.get('offers') or {}
            booking = _url(offers.get('url') or film_url, venue)
            # A generic /program offer is not a screening identifier. Film URL +
            # start is the available source identity; duplicate IDs fail closed.
            for value in starts:
                start = _instant(value)
                row = _row(venue, _identity(film_url, start), event['name'], start,
                           booking=booking, film_id=film_url, audio=audio, subtitles=subs,
                           friendly=bool(re.search(r'english[ -]friendly', raw, re.I)), raw=raw)
                if offers.get('price') is not None:
                    row['price'] = float(offers['price'])
                rows.append(row)
                dates.add(start.date().isoformat())
    return _finish(dates, rows)


_MAT_MONTHS = ('leden', 'únor', 'březen', 'duben', 'květen', 'červen',
               'červenec', 'srpen', 'září', 'říjen', 'listopad', 'prosinec')


def parse_mat(source, venue, day):
    dates, rows, previous, first = set(), [], None, None
    for item in _nodes(_tree(source), 'cinema1'):
        heading = _text(_one(item, 'cinema121'))
        match = re.search(r'(\d{1,2})\s*(' + '|'.join(_MAT_MONTHS) + r')$', heading)
        if not match:
            raise ValueError('MAT dated heading missing')
        dd, mm = int(match[1]), _MAT_MONTHS.index(match[2]) + 1
        if previous is None:
            current = date.fromisoformat(_yearless(f'{dd}. {mm}.', day))
            first = current
        else:
            # Official programme cards are ordered, including next-season dates.
            year = previous.year + ((mm, dd) < (previous.month, previous.day))
            current = date(year, mm, dd)
        if (current - first).days > 366:
            raise ValueError('MAT yearless programme is not within one ordered year')
        previous = current
        clock = _text(_one(item, 'cinema122'))
        info = _one(item, 'cinema124')
        links = info.all(lambda n: n.tag == 'a')
        if not clock and not links:
            # Explicit blank-time advance announcements are not screenings and
            # cannot establish a published empty day.
            continue
        start = _start(current.isoformat(), clock.replace('.', ':'))
        title_links = _one(item, 'cinema123').all(lambda n: n.tag == 'a')
        if len(title_links) != 1 or len(links) > 1:
            raise ValueError('MAT film or booking link missing/ambiguous')
        title = _title(title_links[0])
        booking = _href(links[0] if links else title_links[0], venue)
        provider_id = info.attrs.get('data-definitionid')
        if not provider_id:
            raise ValueError('MAT screening definition ID missing')
        row = _row(venue, provider_id, title, start, booking=booking,
                   film_id=_href(title_links[0], venue), raw='')
        # This is an explicit programme-card label, not a film genre/country.
        if any(_text(n).startswith('KONCERT V ') for n in _nodes(item, 'cinema123note')):
            row['event_type'] = 'non_film'
        prices = info.all(lambda n: n.tag == 'strong')
        if len(prices) == 1 and re.fullmatch(r'\d+\s*Kč', _text(prices[0])):
            row['price'] = int(re.search(r'\d+', _text(prices[0]))[0])
        dates.add(current.isoformat())
        rows.append(row)
    return _finish(dates, rows)


def parse_premiere_hostivar(source, venue, day):
    root = _tree(source)
    titles = root.all(lambda n: n.tag == 'title')
    if len(titles) != 1 or not _text(titles[0]).startswith('Premiere Cinemas Praha Hostivař'):
        raise ValueError('Premiere source is not the Praha Hostivař branch')
    programme = _one(root, 'ps-program')
    dates, rows = set(), []
    for tab in _nodes(programme, 'ps-tab'):
        links = tab.all(lambda n: n.tag == 'a')
        if len(links) != 1 or not links[0].attrs.get('href', '').startswith('#tab-'):
            raise ValueError('Premiere date tab link missing')
        panels = programme.all(lambda n: n.has_class('panel') and
                               n.attrs.get('id') == links[0].attrs['href'][1:])
        if len(panels) != 1:
            raise ValueError('Premiere tab/panel mismatch')
        panel = panels[0]
        tables = _nodes(panel, 'ind_table-program')
        if not tables:
            if 'Program na další týden zveřejníme' in _text(panel):
                continue  # A dated navigation tab alone is not publication.
            raise ValueError('Premiere programme table missing')
        if len(tables) != 1:
            raise ValueError('Premiere programme table ambiguous')
        advance = tab.has_class('ps-tab-advance-sale')
        published = None if advance else _yearless(_text(links[0]), day)
        if published:
            dates.add(published)
        for tr in tables[0].all(lambda n: n.tag == 'tr'):
            movies = _nodes(tr, 'ind_table-program-movie')
            if not movies:
                if _nodes(tr, 'ind_table-program-time'):
                    raise ValueError('Premiere session without film')
                continue
            if len(movies) != 1:
                raise ValueError('Premiere film cell ambiguous')
            movie = movies[0]
            film_links = movie.all(lambda n: n.tag == 'a')
            tooltip = _one(movie, 'tooltip-pc')
            title = _title(_one(_tree(tooltip.attrs.get('title', '')), 'tt-nadpis-filmu'))
            if len(film_links) != 1:
                raise ValueError('Premiere film link missing/ambiguous')
            film_url = _href(film_links[0], venue)
            version = _text(_one(tr, 'ind_table-program-version'))
            if advance:
                published = _yearless(_text(_one(movie, 'ind_program-table-movie-advance-booking')), day)
            # Version 'tit' is not English audio evidence; 'cz' may be a Czech
            # original or dub, so retain raw version without guessing either.
            formats = [_text(n) for n in _nodes(movie, 'ind_table-program-icon')
                       if any(n.has_class(c) for c in ('ind_table-program-icon-4k',
                              'ind_table-program-icon-da', 'ind_table-program-icon-71'))]
            fmt = ', '.join(formats) or None
            cells = _nodes(tr, 'ind_table-program-time')
            if not cells:
                raise ValueError('Premiere film row has no screening times')
            for cell in cells:
                sessions = [n for n in cell.children if getattr(n, 'tag', None) in ('a', 'span')]
                if not sessions:
                    raise ValueError('Premiere screening time missing')
                for session in sessions:
                    start = _start(published, _text(session))
                    booking = _href(session, venue) if session.tag == 'a' else film_url
                    match = re.fullmatch(r'/vstupenky/(\d+)/', urlsplit(booking).path)
                    # Non-bookable spans expose no screening ID/hall. Include
                    # source film URL plus version/format in fallback identity.
                    fallback = json.dumps([film_url, version, fmt])
                    provider_id = match[1] if match else _identity(fallback, start)
                    rows.append(_row(venue, provider_id, title, start, booking=booking,
                                     film_id=film_url, format=fmt, raw=version))
                    dates.add(published)
    return _finish(dates, rows)


def parse_dlabacov(source, venue, day):
    """Public WP programme JSON discovered in the official page's loaded JS.

    Input: /wp-json/bitterend/v1/events/list?language=cs, not the empty Vue shell.
    """
    try:
        payload = json.loads(source)
    except json.JSONDecodeError as error:
        raise ValueError('Dlabačov requires public events/list JSON, not the empty HTML shell') from error
    if not isinstance(payload, dict) or payload.get('status') != 'success' or not isinstance(payload.get('data'), dict):
        raise ValueError('Dlabačov programme unsuccessful or missing')
    dates, rows = set(), []
    languages = {'angličtina': 'en', 'čeština': 'cs', 'němčina': 'de',
                 'dánština': 'da', 'norština': 'no'}
    for year, months in payload['data'].items():
        if not re.fullmatch(r'\d{4}', year) or not isinstance(months, dict):
            raise ValueError('Dlabačov programme year malformed')
        for month, days in months.items():
            if not re.fullmatch(r'\d{1,2}', month) or not isinstance(days, dict):
                raise ValueError('Dlabačov programme month malformed')
            for label, sessions in days.items():
                match = re.fullmatch(r'(\d{1,2})\.(\d{1,2})', label)
                if not match or int(match[2]) != int(month) or not isinstance(sessions, list):
                    raise ValueError('Dlabačov programme day malformed')
                published = date(int(year), int(month), int(match[1])).isoformat()
                dates.add(published)
                for session in sessions:
                    start = _start(published, session['time'])
                    audio_labels, langs = session.get('audio', []), session.get('langs', [])
                    tags = session.get('tags', [])
                    if not all(isinstance(value, list) for value in (audio_labels, langs, tags)):
                        raise ValueError('Dlabačov screening labels malformed')
                    audio = [languages.get(label.lower(), 'und') for label in audio_labels]
                    booking = _url(session.get('ticketLink') or session.get('goOutSaleUrl') or
                                   session.get('link'), venue)
                    provider_id = session.get('goOutId') or _identity(booking, start)
                    # Loaded official JS renders audio as "Audio: ...", 66 as
                    # dubbing and 67 as generic subtitles, NOT English subtitles.
                    raw = {'audio': audio_labels, 'langs': langs, 'tags': tags}
                    row = _row(venue, provider_id, session['name'], start, audio=audio,
                               dubbed=audio if 66 in langs else [], booking=booking,
                               film_id=str(session['id']), format=', '.join(tags) or None, raw=raw)
                    if 'und' in audio:
                        row['access'] = 'unknown'
                    if 'DIVADLO' in tags:
                        row['event_type'] = 'non_film'
                    if re.fullmatch(r'\d+(?:\.\d+)?', str(session.get('price', ''))):
                        row['price'] = float(session['price'])
                    rows.append(row)
    return _finish(dates, rows)


def parse_balt(source, venue, day):
    # Canonical programme source, not the marketing Blockbuster repetitions.
    venue = dict(venue, url='https://kinobalt.cz/')
    dates, rows = set(), []
    for item in _nodes(_tree(source), 'c-Screening'):
        if item.attrs.get('itemtype') != 'https://schema.org/ScreeningEvent':
            raise ValueError('Balt screening microdata missing')
        times = item.all(lambda n: n.tag == 'time' and n.attrs.get('itemprop') == 'startDate')
        links = _one(item, 'c-Screening-title').all(lambda n: n.tag == 'a')
        if len(times) != 1 or len(links) != 1:
            raise ValueError('Balt screening time/title malformed')
        start = _instant(times[0].attrs['datetime'])
        metadata = json.loads(links[0].attrs['data-movie'])
        title = _title(links[0])
        hall = _text(_one(item, 'c-Tags-item--place'))
        if not hall:
            raise ValueError('Balt screening hall missing')
        tickets = _nodes(item, 'btn-ticket')
        if len(tickets) > 1:
            raise ValueError('Balt booking ambiguous')
        booking = _href(tickets[0], venue) if tickets else venue['url']
        raw = ' | '.join(_text(n) for n in _nodes(item, 'c-Label'))
        # These are screening labels. Czech subtitles alone say nothing about
        # audio; explicit Czech/Slovak dubbing is negative English evidence.
        dubbed = [code for label, code in (('cz dabing', 'cs'), ('sk dabing', 'sk'))
                  if label in raw.lower()]
        subtitles = ['cs'] if 'cz titulky' in raw.lower() else []
        row = _row(venue, _identity(booking, start, hall), title, start, hall=hall,
                   booking=booking, subtitles=subtitles, dubbed=dubbed,
                   duration=metadata.get('runtime') or None, raw=raw)
        row['availability_reported'] = 'sold_out' if item.has_class('is-soldout') else 'not_reported_sold_out'
        dates.add(start.date().isoformat())
        rows.append(row)
    return _finish(dates, rows)


PARSERS = {
    'atlas': parse_atlas,
    'pilotu': parse_pilotu,
    'kavalirka': parse_kavalirka,
    'kino35': parse_kino35,
    'ponrepo': parse_ponrepo,
    'edison': parse_edison,
    'mat': parse_mat,
    'premiere_hostivar': parse_premiere_hostivar,
    'dlabacov': parse_dlabacov,
    'balt': parse_balt,
}
