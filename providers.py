"""Deterministic public programme parsers; never infer language from a title."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

PRAGUE = ZoneInfo('Europe/Prague')
PARSER_VERSION = '2026-10-24.2'
LANGUAGES = set('aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu'.split())

def nuxt_data(source):
    match = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', source, re.S)
    if not match:
        raise ValueError('Missing CineStar structured programme')
    values, memo = json.loads(match[1]), {}
    def decode(index):
        if not isinstance(index, int):
            return index
        if index < 0:
            return None
        if index in memo:
            return memo[index]
        value = values[index]
        if isinstance(value, dict):
            result = {}
            memo[index] = result
            result.update({key: decode(ref) for key, ref in value.items()})
            return result
        if isinstance(value, list):
            if value and isinstance(value[0], str):
                if value[0] in ('ShallowReactive', 'Reactive', 'Ref', 'ShallowRef'):
                    return decode(value[1])
                return [value[0]] + [decode(ref) for ref in value[1:]]
            return [decode(ref) for ref in value]
        return value
    return decode(0)

def classify(audio=(), subtitles=(), dubbed=(), friendly=False):
    audio, subtitles, dubbed = set(audio), set(subtitles), set(dubbed)
    if 'en' in subtitles:
        return 'english_subtitles'
    effective = dubbed or audio
    if effective and effective <= {'en'}:
        return 'english_audio'
    if dubbed and 'en' not in dubbed:
        return 'unknown' if dubbed - LANGUAGES else 'not_english'
    if friendly:
        return 'english_friendly'
    return 'not_english' if effective and 'en' not in effective and not effective - LANGUAGES else 'unknown'

def local_instant(value):
    """Provider documented local times; reject ambiguous/nonexistent DST wall times."""
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo:
        return parsed.astimezone(PRAGUE)
    a, b = parsed.replace(tzinfo=PRAGUE, fold=0), parsed.replace(tzinfo=PRAGUE, fold=1)
    if a.utcoffset() != b.utcoffset():
        raise ValueError('Ambiguous or nonexistent Prague wall time without offset')
    return a

def record(venue, provider_id, title, start, *, audio=(), subtitles=(), dubbed=(), friendly=False,
           booking=None, hall=None, format=None, duration=None, raw=None, film_id=None):
    return {
        'id': f"{venue['id']}:{provider_id}", 'provider_id': str(provider_id),
        'film_id': film_id, 'title': title, 'starts_at': start.isoformat(),
        'ends_at': (start.astimezone(timezone.utc) + timedelta(minutes=int(duration))).astimezone(PRAGUE).isoformat() if duration else None,
        'audio': list(audio), 'subtitles': list(subtitles), 'dubbed': list(dubbed),
        'access': classify(audio, subtitles, dubbed, friendly), 'hall': hall, 'format': format,
        'booking_url': booking or venue['url'], 'source_url': venue['url'],
        'price': None, 'currency': 'CZK', 'event_type': 'film',
        'language_evidence': {'raw_label': raw, 'audio': list(audio), 'subtitles': list(subtitles),
                              'dubbed': list(dubbed), 'english_friendly': friendly,
                              'url': venue['url'], 'parser_version': PARSER_VERSION},
    }

def parse_cinema_city(source, venue, day):
    body = json.loads(source)['body']
    films = {f['id']: f for f in body['films']}
    if not isinstance(body['events'], list):
        raise ValueError('Missing Cinema City events')
    rows = []
    for event in body['events']:
        if str(event['cinemaId']) != str(venue['provider_id']):
            raise ValueError('Wrong Cinema City venue')
        film = films[event['filmId']]
        lang = event.get('languages') or {}
        # Session-specific languages are authoritative; film attributeIds are not.
        attrs = event.get('attributeIds', [])
        start = local_instant(event['eventDateTime'])
        if start.date().isoformat() != day:
            raise ValueError('Wrong Cinema City date')
        row = record(venue, event['id'], film['name'], start,
                     audio=lang.get('original', []), subtitles=lang.get('subtitles', []),
                     dubbed=lang.get('dubbed', []) or lang.get('voiceover', []),
                     booking=event['bookingLink'], hall=event.get('auditorium'),
                     format=', '.join(a for a in attrs if a in ('2d','3d','imax','4dx','70-mm','screenx')),
                     duration=film.get('length'), raw=lang, film_id='cinema-city:'+film['id'])
        row['availability_reported'] = 'sold_out' if event.get('soldOut') else 'not_reported_sold_out'
        rows.append(row)
    # Empty API payload alone doesn't establish whether that future date is published.
    if not rows:
        raise ValueError('Empty Cinema City response: publication not established')
    return {day}, rows


def nuxt_entries(data, key):
    for value in data['data'].values():
        if isinstance(value, dict) and key in value:
            return value[key]
    raise ValueError('Missing CineStar '+key)


def cinestar_metadata(source, url, checked_at):
    data=nuxt_data(source)
    entry=nuxt_entries(data,'entry')
    groups=nuxt_entries(data,'groups')
    result={}
    for item in groups + [{'MovieId':entry['MovieId'],'TitleArray':entry['TitleArray']}]:
        result[str(item['MovieId'])]={'title':item['TitleArray'],'url':url,'checked_at':checked_at}
    return result


def parse_cinestar(source, venue, day):
    package=json.loads(source)
    data=nuxt_data(package['programme'])
    halls={str(h['ObjectId']):h for h in nuxt_entries(data,'cinemaHallsEntries') if str(h['CinemaId'])==str(venue['provider_id'])}
    if not halls:
        raise ValueError('CineStar venue halls missing')
    events=nuxt_entries(data,'scheduledEventsEntries')
    if not events:
        raise ValueError('No dated CineStar programme established')
    rows=[];dates=set()
    anchor=datetime.fromisoformat(day).date()
    for event in events:
        hall=halls.get(str(event['ObjectId']))
        if hall is None:
            raise ValueError('Unexpected CineStar auditorium')
        start=local_instant(event['Start'])
        # Public SSR includes a long advance-sales horizon. Bound collection to 7 days.
        if not 0 <= (start.date()-anchor).days < 7:
            continue
        dates.add(start.date().isoformat())
        meta=package['metadata'].get(str(event['TitleId']))
        if not meta:
            raise ValueError('CineStar version title metadata missing')
        labels=[p['Name'] for p in event['Properties']]
        audio=[];subs=[];dub=[]
        if 'ENG + CZ titulky' in labels:
            audio=['en'];subs=['cs']
        if 'CZE + ENG titulky' in labels:
            audio=['cs'];subs=['en']
        if 'ORIGINAL + ENG titulky' in labels:
            subs=['en']
        if 'CZ' in labels:
            audio=['cs']
        # Generic Titulky does NOT establish English audio; don't infer from USA.
        if 'Dabing' in labels:
            dub=['cs']
        row=record(venue,event['EventId'],meta['title'],start,audio=audio,subtitles=subs,dubbed=dub,
                   booking=meta['url']+'#program',hall=hall['Properties'][0]['Name'],
                   format=', '.join(x for x in labels if x in ('3D','3D+HFR','4K','Atmos','Dolby Atmos','GOLD CLASS','THEATRE DELUXE','7.1')),
                   raw=labels,film_id='cinestar-version:'+str(event['TitleId']))
        row['ends_at']=local_instant(event['Finish']).isoformat()
        row['language_evidence']['version_metadata']=meta
        row['language_evidence']['limitation']='Generic Titulky is unknown audio. Booking opens the official version programme, not a checkout.'
        rows.append(row)
    return dates,rows
