"""Explicit opt-in live source check. Offline CI never invokes this command."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import moviecache as m

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--venue',action='append',required=True);p.add_argument('--db',default='data/cache.sqlite');a=p.parse_args()
    venues=[v for v in m.registry() if v['id'] in a.venue]
    if len(venues)!=len(set(a.venue)):p.error('Unknown venue')
    with m.connect(a.db) as db:
        print(json.dumps(m.refresh(db,venues,m.datetime.now(m.PRAGUE).date().isoformat(),force=True),ensure_ascii=False,indent=2))
