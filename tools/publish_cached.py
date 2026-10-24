"""Re-publish already collected local observations. Does not crawl or change age."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import moviecache as m
from collector_job import publish
from providers import PARSER_VERSION

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',default='data/cache.sqlite');a=p.parse_args()
    base=os.environ['FILM_API_URL'];token=os.environ['FILM_INGEST_TOKEN']
    failures=[]
    with m.connect(a.db) as db:
        for r in db.execute('SELECT * FROM programme_runs'):
            rows=json.loads(r['records_json'])
            for row in rows:
                if not row['booking_url'].startswith('https://'):row['booking_url']=next(v['url'] for v in m.registry() if v['id']==r['venue_id'])
            payload={'venue_id':r['venue_id'],'generation':r['generation'],'checked_at':r['checked_at'],
                     'outcome':'ok','detail':'Previously collected official programme','dates':json.loads(r['dates_json']),
                     'screenings':rows,'raw_sha':r['raw_sha'],'parser_version':PARSER_VERSION}
            try:publish(base,token,'internal/ingest',payload);print(r['venue_id'],'published',len(rows))
            except HTTPError as e:failures.append(r['venue_id']);print(r['venue_id'],e.code,e.read().decode()[:300])
    if failures:sys.exit(1)
