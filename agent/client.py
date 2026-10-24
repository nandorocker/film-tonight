#!/usr/bin/env python3
"""Hermes/CLI client. Origin is filtered locally and never sent to the public API."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]

def config():
    default=Path(os.environ['HERMES_HOME'])/'data/film-tonight/config.json' if os.environ.get('HERMES_HOME') else Path.home()/'.config/film-tonight/config.json'
    path=Path(os.environ.get('FILM_CONFIG',str(default)))
    return json.loads(path.read_text()) if path.exists() else {}

def request(path, method='GET', authenticated=False):
    cfg=config();base=cfg.get('api_url') or os.environ.get('FILM_API_URL')
    if not base:raise ValueError('Configure api_url before using the movie service')
    headers={'Accept':'application/json','User-Agent':'FilmTonight/1.0'}
    if authenticated:
        token=cfg.get('refresh_token') or os.environ.get('FILM_REFRESH_TOKEN')
        if not token:raise ValueError('Refresh is not configured for this profile')
        headers['Authorization']='Bearer '+token
    with urlopen(Request(base.rstrip('/')+'/api/v1/'+path,method=method,headers=headers),timeout=15) as response:
        return json.load(response)

def search_screenings(filters=None):
    cfg=config();filters=dict(filters or {})
    if 'origin' not in filters and cfg.get('origin'):
        filters['origin']=cfg['origin']
    day=filters.get('date') or datetime.now(ZoneInfo('Europe/Prague')).date().isoformat()
    snapshot=request('snapshot?'+urlencode({'date':day}))
    result=subprocess.run(['node',str(ROOT/'tools/query.mjs')],input=json.dumps({'snapshot':snapshot,'filters':filters}),text=True,capture_output=True,timeout=15)
    if result.returncode:raise ValueError('Invalid search filters or incompatible snapshot')
    return json.loads(result.stdout)

def get_coverage(filters=None):
    result=search_screenings(filters);result.pop('screenings',None);return result

def refresh_screenings():
    return request('refresh','POST',True)

def table(result):
    from zoneinfo import ZoneInfo
    def cell(value):return str(value).replace('|','\\|').replace('\n',' ')
    lines=[f"{result['service_date']} · Europe/Prague",'','| Start | Film | Cinema | English access | Checked |','|---|---|---|---|---|']
    for r in result['screenings']:
        start=datetime.fromisoformat(r['starts_at'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Prague')).strftime('%H:%M')
        title=cell(r['title']).replace('[','\\[').replace(']','\\]')
        booking=quote(r['booking_url'],safe=':/?&=,%#._~-')
        movie=f'[{title}]({booking})'
        checked=datetime.fromisoformat(r['checked_at'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Prague')).strftime('%d %b %H:%M')
        lines.append('| '+' | '.join(cell(v) for v in [start,movie,r['venue'],r['access'],checked+' '+r['freshness']])+' |')
    lines.append(f"\nCoverage: {result['summary']['fresh_venues']}/{result['summary']['total_venues']} venues fresh. Not an exhaustive citywide list.")
    return '\n'.join(lines)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['search','coverage','refresh'])
    p.add_argument('--filters',default='{}');p.add_argument('--table',action='store_true');a=p.parse_args()
    try:
        value={'search':search_screenings,'coverage':get_coverage}.get(a.command,lambda _:refresh_screenings())(json.loads(a.filters))
        print(table(value) if a.table and a.command=='search' else json.dumps(value,ensure_ascii=False,indent=2))
    except Exception as error:
        print(json.dumps({'error':type(error).__name__,'message':'Movie service unavailable or configuration invalid; check profile settings and coverage.'}),file=sys.stderr);sys.exit(1)
