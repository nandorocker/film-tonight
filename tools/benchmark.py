"""Read-only API latency probe. Does not request any provider or refresh route."""
import argparse
import json
import platform
import statistics
import time
from urllib.request import Request,urlopen
from urllib.parse import urlsplit,urlencode

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base');p.add_argument('--count',type=int,default=100);p.add_argument('--date');a=p.parse_args()
    timings=[];result=None
    remote=urlsplit(a.base).hostname not in ('localhost','127.0.0.1','::1')
    endpoint=a.base.rstrip('/')+'/api/v1/screenings'+('?' + urlencode({'date':a.date}) if a.date else '')
    for _ in range(a.count):
        start=time.perf_counter()
        with urlopen(Request(endpoint,headers={'User-Agent':'FilmTonight/1.0','Accept':'application/json'}),timeout=10) as r:result=json.load(r)
        timings.append((time.perf_counter()-start)*1000)
    print(json.dumps({'platform':platform.platform(),'count':a.count,'median_ms':statistics.median(timings),
                      'p95_ms':sorted(timings)[int(a.count*.95)-1],'min_ms':min(timings),'max_ms':max(timings),
                      'returned_screenings':result['total'],'fresh_venues':result['summary']['fresh_venues'],
                      'includes':('HTTP network round-trip, deployed Pages/D1, selection, response transfer and JSON parsing' if remote else 'HTTP loopback, Pages emulator, D1 local query, selection, JSON parsing')+'; first request included',
                      'excludes':'Provider collection, UI, agent generation; no CPU-time or latency-component breakdown'},indent=2))
