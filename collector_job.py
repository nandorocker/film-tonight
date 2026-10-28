#!/usr/bin/env python3
"""Run the collector and publish normalized per-venue observations; never seeds demos."""
import argparse
from contextlib import closing
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import moviecache as m
from providers import PARSER_VERSION

def error_fields(error):
    fields={'type':type(error).__name__}
    if isinstance(error,HTTPError):
        fields['http_status']=error.code
    return fields

def request_json(request, operation):
    # Startup reads need the same protection as idempotent publication writes.
    for attempt in range(3):
        delay=2**attempt
        try:
            try:
                with urlopen(request, timeout=30) as response:
                    return json.load(response)
            except HTTPError as error:
                try:
                    if error.code not in (429,500,502,503,504) or attempt==2:
                        raise
                    retry=error.headers.get('Retry-After','').strip()
                    if retry:
                        try:
                            delay=int(retry) if retry.isdigit() else max(0,(parsedate_to_datetime(retry)-datetime.now(m.UTC)).total_seconds())
                        except (TypeError,ValueError,OverflowError):
                            pass  # Malformed advice uses the short default backoff.
                    if delay>30:
                        raise
                    retry_fields=error_fields(error)
                finally:
                    error.close()
            except (URLError,TimeoutError,ConnectionError) as error:
                if attempt==2:
                    raise
                retry_fields=error_fields(error)
        except Exception as error:
            print(json.dumps({'outcome':'request_error','operation':operation,'attempt':attempt+1,**error_fields(error)}),file=sys.stderr,flush=True)
            raise
        print(json.dumps({'outcome':'request_retry','operation':operation,'attempt':attempt+1,**retry_fields}),file=sys.stderr,flush=True)
        time.sleep(delay)

def publish(base, token, path, value):
    request = Request(base.rstrip('/')+'/api/v1/'+path, data=json.dumps(value, ensure_ascii=False).encode(),
                      headers={'User-Agent':'FilmTonight/1.0','Content-Type':'application/json','Authorization':'Bearer '+token}, method='POST')
    # Replay the same generation/body: cloud writes are ordered and idempotent.
    return request_json(request,'job_completion' if path=='internal/jobs' else 'publication')

def prune(db, days=30):
    cutoff=(datetime.now(m.UTC)-timedelta(days=days)).isoformat()
    raw_cutoff=(datetime.now(m.UTC)-timedelta(days=7)).isoformat()
    with db:
        # Keep the latest useful venue/date snapshot irrespective of age.
        service_cutoff=(datetime.now(m.PRAGUE).date()-timedelta(days=days)).isoformat()
        today=datetime.now(m.PRAGUE).date().isoformat()
        db.execute('DELETE FROM snapshots WHERE service_date<? OR (checked_at<? AND id NOT IN (SELECT max(id) FROM snapshots WHERE service_date>=? GROUP BY venue_id,service_date))',(service_cutoff,cutoff,today))
        db.execute('DELETE FROM attempts WHERE checked_at<? AND id NOT IN (SELECT max(id) FROM attempts GROUP BY venue_id)',(cutoff,))
        db.execute('DELETE FROM pages WHERE venue_id NOT IN (SELECT venue_id FROM programme_runs WHERE checked_at>=?)',(raw_cutoff,))

def run(db_path, base=None, token=None):
    generation=m.utcnow()
    if base:
        # Reuse only public, version-specific normalized title metadata, not raw pages.
        prior={}
        today=datetime.now(m.PRAGUE).date()
        for offset in range(7):
            day=(today+timedelta(days=offset)).isoformat()
            request=Request(base.rstrip('/')+'/api/v1/snapshot?date='+day,headers={'User-Agent':'FilmTonight/1.0','Accept':'application/json'})
            previous=request_json(request,'snapshot_read')
            for programme in previous.get('snapshots',[]):
                entry=prior.setdefault(programme['venue_id'],dict(programme,screenings=[]))
                entry['screenings'].extend(programme['screenings'])
        for programme in prior.values():
            for item in programme.get('screenings',[]):
                meta=item.get('language_evidence',{}).get('version_metadata')
                if meta and str(item.get('film_id','')).startswith('cinestar-version:'):
                    m._cinestar_metadata[item['film_id'].split(':',1)[1]]=meta
    with closing(m.connect(db_path)) as db:
        if base:
            # A fresh Actions runner still needs the last-good cloud comparison
            # baseline. This is normalized, public data, not a raw-page archive.
            with db:
                for programme in prior.values():
                    db.execute('INSERT OR IGNORE INTO programme_runs VALUES(?,?,?,?,?,?)',
                               (programme['venue_id'],programme['generation'],programme['checked_at'],json.dumps(programme['dates']),json.dumps(programme['screenings']),programme.get('raw_sha')))
        reports=m.refresh(db,m.registry(),datetime.now(m.PRAGUE).date().isoformat(),force=True)
        publication_errors=[]
        for report in reports:
            if report['outcome']=='coalesced':
                return {'outcome':'coalesced'}
            venue_id=report['venue_id']
            attempt=db.execute('SELECT * FROM attempts WHERE venue_id=? ORDER BY id DESC LIMIT 1',(venue_id,)).fetchone()
            payload={'venue_id':venue_id,'generation':generation,'checked_at':attempt['checked_at'],
                     'outcome':'error','detail':report.get('detail','Collection failed')}
            if report['outcome'] in ('ok','unpublished'):
                row=db.execute('SELECT * FROM programme_runs WHERE venue_id=?',(venue_id,)).fetchone()
                payload.update(outcome='ok',detail='Parsed official programme',dates=json.loads(row['dates_json']),
                               screenings=json.loads(row['records_json']),raw_sha=row['raw_sha'],parser_version=PARSER_VERSION)
                for item in payload['screenings']:
                    # Kino35 publishes an HTTP booking link; use its HTTPS official programme
                    # as fallback rather than silently upgrading an unverified booking host.
                    if not item['booking_url'].startswith('https://'):
                        item['booking_url']=next(v['url'] for v in m.registry() if v['id']==venue_id)
            if base:
                try:
                    publish(base,token,'internal/ingest',payload)
                except Exception as error:
                    publication_errors.append(venue_id)
                    print(json.dumps({'venue_id':venue_id,'outcome':'publication_error',**error_fields(error)}),file=sys.stderr,flush=True)
                    continue
            print(json.dumps({'venue_id':venue_id,'outcome':payload['outcome'],'count':len(payload.get('screenings',[]))}),flush=True)
        prune(db)
    failed_venues=sorted(r['venue_id'] for r in reports if r['outcome']=='error')
    if base:
        publish(base,token,'internal/jobs',{'generation':generation,'failed':bool(publication_errors or failed_venues)})
    if publication_errors:
        raise RuntimeError('Publication failed for '+','.join(publication_errors))
    if failed_venues and os.environ.get('GITHUB_ACTIONS')=='true':
        print('::warning::Collection completed with source errors: '+','.join(failed_venues),flush=True)
    return {'generation':generation,'outcome':'complete_with_errors' if failed_venues else 'complete','failed_venues':failed_venues,'results':reports}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default=os.environ.get('MOVIE_DB','data/cache.sqlite'))
    p.add_argument('--watch',type=int,default=0,metavar='SECONDS')
    args=p.parse_args()
    base=os.environ.get('FILM_API_URL');token=os.environ.get('FILM_INGEST_TOKEN')
    if base and not token:p.error('FILM_INGEST_TOKEN required for publication')
    if args.watch and args.watch<600:p.error('watch interval must be at least 600 seconds')
    while True:
        try:
            report=run(args.db,base,token)
            print(json.dumps(report),flush=True)
        except Exception as error:
            # Avoid emitting credential-bearing URLs/HTTP headers or bodies.
            print(json.dumps({'outcome':'job_error',**error_fields(error)}),file=sys.stderr,flush=True)
            if not args.watch:sys.exit(1)
        if not args.watch:break
        time.sleep(args.watch)
