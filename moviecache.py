#!/usr/bin/env python3
"""Portable Prague screening cache. Python 3.11+, standard library only."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from datetime import date, datetime, time as clocktime, timezone, timedelta
from hashlib import sha256
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import fcntl
import random
import threading
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from providers import PARSER_VERSION, parse_cinema_city, parse_cinestar, nuxt_data, nuxt_entries, cinestar_metadata

HERE = Path(__file__).resolve().parent
PRAGUE = ZoneInfo('Europe/Prague')
UTC = timezone.utc
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
ACCESSIBLE = {'english_audio', 'english_subtitles', 'english_friendly'}


def utcnow():
    return datetime.now(UTC).isoformat()


def instant(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return result


class Node:
    def __init__(self, tag='', attrs=None):
        self.tag, self.attrs, self.children = tag, dict(attrs or []), []

    def all(self, predicate):
        found = [self] if predicate(self) else []
        for child in self.children:
            if isinstance(child, Node):
                found.extend(child.all(predicate))
        return found

    def text(self):
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children)

    def has_class(self, value):
        return value in self.attrs.get('class', '').split()


class Tree(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def language_access(audio, tags):
    """A website being in English is never evidence about a screening."""
    raw = str(audio or '').lower()
    languages = set(re.findall(r'\b[a-z]{2,3}\b', raw))
    tag_text = ' '.join(tags).lower()
    dubbed = any(t in tag_text for t in ('dabing', 'czech dub', 'český dabing'))
    english_subs = any(t in tag_text for t in ('english subtitles', 'anglické titulky'))
    if english_subs:
        return 'english_subtitles'
    if dubbed:
        return 'not_english'
    if languages and languages <= {'en', 'eng'}:
        return 'english_audio'
    if any(t.strip().lower() in ('eng', 'english friendly', 'english-friendly') for t in tags):
        return 'english_friendly'
    return 'unknown'


def parse_aerokina(source, venue):
    root = Tree(source).root
    dates = set()
    for node in root.all(lambda n: n.has_class('program__day')):
        match = re.fullmatch(r'program-day-(\d{2})-(\d{2})-(\d{4})', node.attrs.get('id', ''))
        if match:
            day, month, year = map(int, match.groups())
            dates.add(date(year, month, day).isoformat())
    rows = root.all(lambda n: n.has_class('program__info-row'))
    if not dates or not rows:
        raise ValueError('Programme structure missing; refusing to cache an empty success')
    results = []
    for row in rows:
        scripts = row.all(lambda n: n.tag == 'script' and n.attrs.get('type') == 'application/ld+json')
        if len(scripts) != 1:
            raise ValueError('Expected one structured Event per screening row')
        event = json.loads(scripts[0].text())
        if event.get('@type') != 'Event':
            raise ValueError('Structured screening is not an Event')
        start = instant(event['startDate']).astimezone(PRAGUE)
        if start.date().isoformat() not in dates:
            raise ValueError('Structured date disagrees with programme day headings')
        tags = [' '.join(n.text().split()) for n in row.all(lambda n: n.has_class('program__tag'))]
        offers = event.get('offers', {})
        booking = event.get('url') or venue['url']
        if urlsplit(booking).scheme != 'https' or urlsplit(booking).hostname != urlsplit(venue['url']).hostname:
            raise ValueError('Unexpected booking URL origin')
        results.append({
            'id': sha256((venue['id']+'|'+booking+'|'+start.isoformat()).encode()).hexdigest()[:20],
            'title': event['name'], 'starts_at': start.isoformat(),
            'ends_at': event.get('endDate'), 'audio': event.get('inLanguage'),
            'access': language_access(event.get('inLanguage'), tags),
            'language_evidence': {'audio': event.get('inLanguage'), 'venue_tags': tags},
            'price': offers.get('price'), 'currency': offers.get('priceCurrency'),
            'booking_url': booking,
            'availability_reported': offers.get('availability'),
        })
    ids = [r['id'] for r in results]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate screening IDs; refusing ambiguous snapshot')
    return dates, results


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    if db.execute('PRAGMA user_version').fetchone()[0] > 2:
        db.close()
        raise ValueError('Database schema is newer than this collector; refusing downgrade')
    db.executescript('''
      PRAGMA journal_mode=WAL;
      CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY, venue_id TEXT NOT NULL, service_date TEXT NOT NULL,
        checked_at TEXT NOT NULL, kind TEXT NOT NULL, state TEXT NOT NULL,
        records_json TEXT NOT NULL, source_url TEXT NOT NULL, raw_sha TEXT);
      CREATE INDEX IF NOT EXISTS snapshot_lookup ON snapshots(venue_id,service_date,id);
      CREATE TABLE IF NOT EXISTS pages (
        venue_id TEXT PRIMARY KEY, etag TEXT, modified TEXT, body TEXT NOT NULL, raw_sha TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY, venue_id TEXT, service_date TEXT, checked_at TEXT,
        outcome TEXT, detail TEXT);
      CREATE TABLE IF NOT EXISTS programme_runs (
        venue_id TEXT PRIMARY KEY, generation TEXT NOT NULL, checked_at TEXT NOT NULL,
        dates_json TEXT NOT NULL, records_json TEXT NOT NULL, raw_sha TEXT);
      PRAGMA user_version=2;
    ''')
    return db


def write_snapshot(db, venue_id, day, records, source_url, *, kind='live', state='ok', checked_at=None, raw_sha=None):
    db.execute('INSERT INTO snapshots(venue_id,service_date,checked_at,kind,state,records_json,source_url,raw_sha) VALUES(?,?,?,?,?,?,?,?)',
               (venue_id, day, checked_at or utcnow(), kind, state, json.dumps(records, ensure_ascii=False), source_url, raw_sha))


def newest(db, venue_id, day):
    return db.execute('SELECT * FROM snapshots WHERE venue_id=? AND service_date=? ORDER BY id DESC LIMIT 1', (venue_id, day)).fetchone()


def fresh(row, ttl, now=None):
    if not row or row['kind'] != 'live' or row['state'] != 'ok':
        return False
    age = ((now or datetime.now(UTC)) - instant(row['checked_at'])).total_seconds()
    return 0 <= age <= ttl


def registry():
    return json.loads((HERE / 'venues.json').read_text())


def download(venue, old_page):
    if venue['adapter'] == 'cinestar':
        source=fetch(venue['url'])[0]
        metadata={}
        if old_page:
            metadata=json.loads(old_page['body']).get('metadata',{})
        metadata.update(_cinestar_metadata)
        data=nuxt_data(source)
        today=datetime.now(PRAGUE).date()
        ids={str(e['TitleId']) for e in nuxt_entries(data,'scheduledEventsEntries')
             if 0 <= (instant(e['Start']).astimezone(PRAGUE).date()-today).days < 7}
        for film_id in sorted(ids):
            old=metadata.get(film_id)
            if old and 0 <= (datetime.now(UTC)-instant(old['checked_at'])).total_seconds() < 86400:
                continue
            url=venue['url'].rsplit('/program',1)[0]+'/filmy/movie/'+film_id
            html=fetch(url)[0]
            metadata.update(cinestar_metadata(html,url,utcnow()))
        return json.dumps({'programme':source,'metadata':metadata}), None, None
    if venue['adapter'] == 'cinema_city':
        results = {}
        today = datetime.now(PRAGUE).date()
        for offset in range(7):
            day = (today + timedelta(days=offset)).isoformat()
            url = f"https://www.cinemacity.cz/cz/data-api-service/v1/quickbook/10101/film-events/in-cinema/{venue['provider_id']}/at-date/{day}?attr=&lang=en_GB"
            results[day] = fetch(url)[0]
        return json.dumps(results), None, None
    return fetch(venue['url'], old_page)


_host_lock = threading.Lock()
_host_times = {}
_robots = {}
_cinestar_metadata = {}


def fetch(url, old_page=None):
    """Bounded retries and per-host pacing. Robots deny/temporary failures fail closed."""
    from urllib.robotparser import RobotFileParser
    host = urlsplit(url).netloc
    ua = 'FilmTonight/1.0 (personal Prague cinema programme cache)'
    with _host_lock:
        if host not in _robots:
            parser = RobotFileParser()
            try:
                with urlopen(Request(f'https://{host}/robots.txt', headers={'User-Agent': ua}), timeout=12) as response:
                    parser.parse(response.read(200_000).decode('utf-8', 'replace').splitlines())
            except HTTPError as error:
                if error.code not in (404, 410):
                    raise ValueError(f'robots.txt unavailable ({error.code}); collection deferred')
                parser.parse([])
            _robots[host] = parser
        if not _robots[host].can_fetch(ua, url):
            raise ValueError('robots.txt disallows this programme URL')
        pause = max(0, _host_times.get(host, 0) - time.monotonic())
        time.sleep(pause)
        _host_times[host] = time.monotonic() + max(1, _robots[host].crawl_delay(ua) or 0)
    headers = {'User-Agent': ua, 'Accept': 'text/html,application/json'}
    if old_page:
        if old_page['etag']:
            headers['If-None-Match'] = old_page['etag']
        if old_page['modified']:
            headers['If-Modified-Since'] = old_page['modified']
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=12) as response:
                if urlsplit(response.url).hostname != urlsplit(url).hostname:
                    raise ValueError('Unexpected redirect origin')
                body = response.read(5_000_001)
                if len(body) > 5_000_000:
                    raise ValueError('Page exceeds 5 MB limit')
                return body.decode(response.headers.get_content_charset() or 'utf-8'), response.headers.get('ETag'), response.headers.get('Last-Modified')
        except HTTPError as error:
            if error.code == 304 and old_page:
                return old_page['body'], old_page['etag'], old_page['modified']
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            retry = error.headers.get('Retry-After', '')
            if retry and not retry.isdigit():
                from email.utils import parsedate_to_datetime
                retry = str(max(0, int((parsedate_to_datetime(retry)-datetime.now(UTC)).total_seconds())))
            delay = int(retry) if retry.isdigit() else 2 ** attempt + random.random()
            if delay > 30:
                raise ValueError('Provider requested long Retry-After; deferred')
            time.sleep(delay)
        except (TimeoutError, OSError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt + random.random())


def collect(venue, old_page):
    started = time.monotonic()
    try:
        body, etag, modified = download(venue, old_page)
        today = datetime.now(PRAGUE).date().isoformat()
        if venue['adapter'] == 'aerokina':
            dates, rows = parse_aerokina(body, venue)
        elif venue['adapter'] == 'cinema_city':
            dates, rows = set(), []
            for day, source in json.loads(body).items():
                if not json.loads(source).get('body', {}).get('events'):
                    continue
                days, events = parse_cinema_city(source, venue, day)
                dates.update(days)
                rows.extend(events)
        elif venue['adapter'] == 'cinestar':
            dates,rows=parse_cinestar(body,venue,today)
        else:
            from providers_html import PARSERS
            dates, rows = PARSERS[venue['adapter']](body, venue, today)
        if not dates:
            raise ValueError('No published dates established')
        ids = [row['id'] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate source screening identity')
        for row in rows:
            row.setdefault('source_url', venue['url'])
            row.setdefault('event_type', 'unknown')
            row.setdefault('format', None)
            row['language_evidence'].update(extracted_at=utcnow(), parser_version=PARSER_VERSION, url=venue['url'])
        return {'venue': venue, 'dates': dates, 'rows': rows, 'body': body, 'etag': etag, 'modified': modified,
                'raw_sha': sha256(body.encode()).hexdigest(), 'seconds': round(time.monotonic()-started, 3)}
    except Exception as error:
        return {'venue': venue, 'error': f'{type(error).__name__}: {error}', 'seconds': round(time.monotonic()-started, 3)}


def refresh(db, venues, day, ttl=900, force=False):
    path = db.execute('PRAGMA database_list').fetchone()[2]
    with open(str(path) + '.refresh.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return [{'outcome': 'coalesced', 'detail': 'Refresh already running'}]
        return _refresh(db, venues, day, ttl, force)


def _refresh(db, venues, day, ttl=900, force=False):
    """Parallel network reads; serialized transactional writes on the main thread."""
    report, pending = [], []
    for venue in venues:
        if venue['adapter'] in ('not_implemented', 'blocked'):
            continue
        if not force and fresh(newest(db, venue['id'], day), ttl):
            report.append({'venue_id': venue['id'], 'outcome': 'cache_fresh'})
        else:
            page = db.execute('SELECT * FROM pages WHERE venue_id=?', (venue['id'],)).fetchone()
            pending.append((venue, dict(page) if page else None))
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(collect, venue, page) for venue, page in pending]
        for future in as_completed(futures):
            result = future.result()
            venue = result['venue']
            checked = utcnow()
            if 'error' not in result:
                previous = db.execute('SELECT records_json FROM programme_runs WHERE venue_id=?', (venue['id'],)).fetchone()
                if previous:
                    previous_rows = json.loads(previous['records_json'])
                    upcoming = [r for r in previous_rows if instant(r['starts_at']) >= datetime.now(UTC)]
                    if len(upcoming) >= 20 and len(result['rows']) < len(upcoming) / 5:
                        result['error'] = 'Suspicious programme collapse; previous snapshot retained for inspection'
            if 'error' in result:
                # Last good snapshot remains readable, but coverage exposes the failed attempt.
                with db:
                    db.execute('INSERT INTO attempts(venue_id,service_date,checked_at,outcome,detail) VALUES(?,?,?,?,?)',
                               (venue['id'], day, checked, 'error', result['error']))
                report.append({'venue_id': venue['id'], 'outcome': 'error', 'detail': result['error'], 'seconds': result['seconds']})
                continue
            with db:
                db.execute('INSERT OR REPLACE INTO pages VALUES(?,?,?,?,?)',
                           (venue['id'], result['etag'], result['modified'], result['body'], result['raw_sha']))
                db.execute('INSERT OR REPLACE INTO programme_runs VALUES(?,?,?,?,?,?)',
                           (venue['id'], checked, checked, json.dumps(sorted(result['dates'])), json.dumps(result['rows'], ensure_ascii=False), result['raw_sha']))
                for covered in sorted(result['dates']):
                    rows = [r for r in result['rows'] if instant(r['starts_at']).astimezone(PRAGUE).date().isoformat() == covered]
                    write_snapshot(db, venue['id'], covered, rows, venue['url'], checked_at=checked, raw_sha=result['raw_sha'])
                previous_days = {r[0] for r in db.execute('SELECT DISTINCT service_date FROM snapshots WHERE venue_id=? AND service_date>=?', (venue['id'], day))}
                for removed in previous_days - result['dates']:
                    if removed != day:
                        write_snapshot(db, venue['id'], removed, [], venue['url'], checked_at=checked, state='unpublished', raw_sha=result['raw_sha'])
                if day not in result['dates']:
                    # A page without the requested date is not proof of zero screenings.
                    write_snapshot(db, venue['id'], day, [], venue['url'], checked_at=checked, state='unpublished', raw_sha=result['raw_sha'])
                db.execute('INSERT INTO attempts(venue_id,service_date,checked_at,outcome,detail) VALUES(?,?,?,?,?)',
                           (venue['id'], day, checked, 'ok', 'Parsed dated programme'))
            report.append({'venue_id': venue['id'], 'outcome': 'ok' if day in result['dates'] else 'unpublished',
                           'dates_cached': len(result['dates']), 'screenings_cached': len(result['rows']), 'seconds': result['seconds']})
    return sorted(report, key=lambda r: r['venue_id'])


def query(db, venues, day, after='18:00', ttl=900, include_uncertain=False):
    now = datetime.now(UTC)
    screenings, coverage = [], []
    for venue in venues:
        row = newest(db, venue['id'], day)
        attempt = db.execute('SELECT checked_at,outcome,detail FROM attempts WHERE venue_id=? AND service_date=? ORDER BY id DESC LIMIT 1', (venue['id'], day)).fetchone()
        is_fresh = fresh(row, ttl, now)
        state = 'missing' if not row else row['state'] if row['state'] != 'ok' else 'fresh' if is_fresh else 'sample' if row['kind'] == 'manual_sample' else 'stale'
        covered = {k: venue[k] for k in ('id', 'name', 'adapter')}
        covered.update(state=state, checked_at=row['checked_at'] if row else None,
                       last_attempt=dict(attempt) if attempt else None)
        coverage.append(covered)
        if not row or row['state'] != 'ok':
            continue
        for item in json.loads(row['records_json']):
            local = instant(item['starts_at']).astimezone(PRAGUE)
            if local.date().isoformat() != day or local.strftime('%H:%M') < after:
                continue
            if item['access'] not in ACCESSIBLE and not include_uncertain:
                continue
            screenings.append(dict(item, venue_id=venue['id'], venue=venue['name'], coordinates=venue['coordinates'],
                                   source_url=row['source_url'], checked_at=row['checked_at'], freshness=state,
                                   origin=row['kind']))
    return {'schema_version': 1, 'service_date': day, 'timezone': 'Europe/Prague', 'after': after,
            'generated_at': now.isoformat(), 'ttl_seconds': ttl, 'screenings': sorted(screenings, key=lambda r: (r['starts_at'], r['venue'], r['title'])),
            'coverage': coverage}


def geojson(payload):
    features = []
    unmapped = []
    by_venue = {}
    for item in payload['screenings']:
        by_venue.setdefault(item['venue_id'], []).append(item)
    for venue_id, items in by_venue.items():
        first = items[0]
        if not first['coordinates'] or len(first['coordinates']) != 2:
            unmapped.append(venue_id)
            continue
        features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': first['coordinates']},
                         'properties': {'venue_id': venue_id, 'name': first['venue'], 'freshness': first['freshness'],
                                        'checked_at': first['checked_at'], 'screenings': items}})
    return {'type': 'FeatureCollection', 'features': features, 'coverage': payload['coverage'], 'unmapped_venue_ids': unmapped,
            'service_date': payload['service_date'], 'generated_at': payload['generated_at']}


def markdown(payload):
    lines = [f"{payload['service_date']} · Europe/Prague · starts from {payload['after']}", '',
             '| Start | Movie | Cinema | English access | Cache |', '|---|---|---|---|---|']
    def cell(text):
        return str(text).replace('|', '\\|').replace('\n', ' ')
    for row in payload['screenings']:
        values = [instant(row['starts_at']).astimezone(PRAGUE).strftime('%H:%M'), row['title'], row['venue'], row['access'], row['freshness']]
        lines.append('| ' + ' | '.join(cell(v) for v in values) + ' |')
    counts = {}
    for item in payload['coverage']:
        counts[item['state']] = counts.get(item['state'], 0) + 1
    lines.extend(['', 'Coverage: ' + ', '.join(f'{n} {state}' for state, n in sorted(counts.items()))])
    return '\n'.join(lines)


def seed(db, venues):
    source = json.loads((HERE / 'examples' / 'snapshot-2026-10-24.json').read_text())
    imported = 0
    with db:
        for entry in source['venues']:
            if newest(db, entry['venue_id'], source['service_date']):
                continue
            write_snapshot(db, entry['venue_id'], source['service_date'], entry['screenings'], entry['source_url'],
                           kind='manual_sample', checked_at=source['observed_at'])
            imported += 1
    return {'imported': imported, 'kind': 'manual_sample', 'note': 'Historical hand-compiled example, not a live collection. Never considered fresh.'}


def serve(db_path, venues, port, ttl):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            params = parse_qs(parsed.query)
            try:
                if parsed.path == '/health':
                    value = {'ok': True, 'schema_version': 1}
                elif parsed.path in ('/screenings', '/coverage', '/map.geojson'):
                    day = valid_date(params.get('date', [datetime.now(PRAGUE).date().isoformat()])[0])
                    after = valid_time(params.get('after', ['18:00'])[0])
                    with closing(connect(db_path)) as db:
                        value = query(db, venues, day, after, ttl)
                    if parsed.path == '/coverage':
                        value = {k: value[k] for k in ('service_date', 'generated_at', 'coverage')}
                    elif parsed.path == '/map.geojson':
                        value = geojson(value)
                else:
                    self.send_error(404)
                    return
                body = json.dumps(value, ensure_ascii=False).encode()
                self.send_response(200)
            except (ValueError, argparse.ArgumentTypeError) as error:
                body = json.dumps({'error': str(error)}).encode()
                self.send_response(400)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    print(f'Read-only API: http://127.0.0.1:{port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


def valid_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError('Use a valid YYYY-MM-DD date')


def valid_time(value):
    if not re.fullmatch(r'\d{2}:\d{2}', value):
        raise argparse.ArgumentTypeError('Use HH:MM')
    try:
        clocktime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError('Use a valid HH:MM time')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=str(HERE / 'data' / 'cache.sqlite'))
    parser.add_argument('--ttl', type=int, default=900, help='Freshness threshold in seconds (default 900)')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('seed', help='Import historical example; never marks it fresh')
    for name in ('query', 'refresh', 'coverage', 'watch'):
        p = sub.add_parser(name)
        if name != 'watch':
            p.add_argument('--date', type=valid_date, default=datetime.now(PRAGUE).date().isoformat())
        if name in ('query', 'coverage'):
            p.add_argument('--after', type=valid_time, default='18:00')
            p.add_argument('--format', choices=('json','table','geojson'), default='json')
            p.add_argument('--include-uncertain', action='store_true')
        if name in ('refresh', 'watch'):
            p.add_argument('--force', action='store_true')
        if name == 'watch':
            p.add_argument('--interval', type=int, default=600)
    p = sub.add_parser('serve')
    p.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if args.ttl < 0:
        parser.error('--ttl must be nonnegative')
    if args.command == 'watch' and args.interval < 60:
        parser.error('watch requires --interval >= 60')
    venues = registry()
    if args.command == 'serve':
        serve(args.db, venues, args.port, args.ttl)
        return
    with connect(args.db) as db:
        if args.command == 'seed':
            output = seed(db, venues)
        elif args.command == 'refresh':
            output = refresh(db, venues, args.date, args.ttl, args.force)
        elif args.command == 'watch':
            # Always derive today's date again, so midnight rolls over correctly.
            try:
                while True:
                    today = datetime.now(PRAGUE).date()
                    # One page fetch already covers its advertised upcoming dates.
                    reports = refresh(db, venues, today.isoformat(), args.ttl, True)
                    print(json.dumps({'checked_at': utcnow(), 'results': reports}), flush=True)
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                return
        else:
            output = query(db, venues, args.date, args.after, args.ttl, args.include_uncertain)
            if args.command == 'coverage':
                output = {k: output[k] for k in ('service_date','generated_at','coverage')}
            elif args.format == 'table':
                print(markdown(output))
                return
            elif args.format == 'geojson':
                output = geojson(output)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
