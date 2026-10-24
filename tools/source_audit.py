"""Opt-in official source inspection. Captures stay outside the repository."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
UA = 'FilmTonight/1.0 (personal Prague cinema programme cache)'

def inspect(v):
    out = {'id': v['id'], 'url': v['url']}
    try:
        parts = urlsplit(v['url'])
        robots = RobotFileParser()
        try:
            with urlopen(Request(f'{parts.scheme}://{parts.netloc}/robots.txt', headers={'User-Agent': UA}), timeout=15) as r:
                robots.parse(r.read(200_000).decode('utf-8', 'replace').splitlines())
            out['robots_allowed'] = robots.can_fetch(UA, v['url'])
            if not out['robots_allowed']:
                return dict(out, error='robots.txt disallows programme collection')
        except Exception as e:
            out['robots_check'] = type(e).__name__
        with urlopen(Request(v['url'], headers={'User-Agent': UA}), timeout=20) as r:
            raw = r.read(5_000_001)
            out.update(status=r.status, final_url=r.url, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            if len(raw) > 5_000_000:
                raise ValueError('body limit')
            (Path(sys.argv[1]) / (v['id'] + '.html')).write_bytes(raw)
    except Exception as e:
        out['error'] = f'{type(e).__name__}: {e}'
    return out

if __name__ == '__main__':
    Path(sys.argv[1]).mkdir(parents=True, exist_ok=True)
    venues = json.loads((ROOT / 'venues.json').read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(inspect, venues):
            print(json.dumps(result, ensure_ascii=False), flush=True)
