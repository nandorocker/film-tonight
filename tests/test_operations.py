from contextlib import closing
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import threading
import time
from unittest.mock import patch

import collector_job as job
import moviecache as m

class OperationsTests(unittest.TestCase):
    def test_fresh_scheduled_runner_restores_collapse_baseline(self):
        tomorrow=datetime.now(m.PRAGUE).date()+timedelta(days=1)
        start=datetime.combine(tomorrow,datetime.min.time().replace(hour=20),m.PRAGUE).isoformat()
        checked=m.utcnow();venue={'id':'test','name':'Test','adapter':'aerokina','url':'https://test.example','coordinates':None}
        old=[{'id':str(i),'title':'Film','starts_at':start,'access':'unknown','booking_url':'https://test.example','language_evidence':{}} for i in range(100)]
        programme={'venue_id':'test','generation':checked,'checked_at':checked,'dates':[tomorrow.isoformat()],'screenings':old}
        def previous(url,**_):
            self.assertEqual(url.get_header('User-agent'),'FilmTonight/1.0')
            data={'snapshots':[programme] if tomorrow.isoformat() in url.full_url else []}
            return io.BytesIO(json.dumps(data).encode())
        result={'venue':venue,'dates':{tomorrow.isoformat()},'rows':old[:5],'body':'fixture','etag':None,'modified':None,'raw_sha':'a'*64,'seconds':0}
        with tempfile.TemporaryDirectory() as temp, patch.object(job,'urlopen',side_effect=previous),patch.object(m,'registry',return_value=[venue]),patch.object(m,'collect',return_value=result),patch.object(job,'publish') as publish:
            job.run(Path(temp)/'new.sqlite','https://cloud.example','not-a-real-token')
            observation=publish.call_args_list[0].args[-1]
            self.assertEqual(observation['outcome'],'error')
            with closing(m.connect(Path(temp)/'new.sqlite')) as db:
                self.assertEqual(len(json.loads(db.execute('SELECT records_json FROM programme_runs').fetchone()[0])),100)
            self.assertTrue(publish.call_args_list[-1].args[-1]['failed'])

    def test_retention_removes_expired_dates_not_only_old_versions(self):
        with tempfile.TemporaryDirectory() as temp,closing(m.connect(Path(temp)/'test.sqlite')) as db:
            old=(datetime.now(m.PRAGUE).date()-timedelta(days=100)).isoformat()
            checked=(datetime.now(m.UTC)-timedelta(days=100)).isoformat();today=datetime.now(m.PRAGUE).date().isoformat()
            with db:
                for i in range(4):m.write_snapshot(db,'v'+str(i),old,[],'https://test.example',checked_at=checked)
                m.write_snapshot(db,'current',today,[],'https://test.example',checked_at=checked)
            job.prune(db)
            self.assertEqual([r['venue_id'] for r in db.execute('SELECT * FROM snapshots')],['current'])

    def test_newer_schema_is_not_downgraded(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'future.sqlite'
            with closing(sqlite3.connect(path)) as db:db.execute('PRAGMA user_version=99');db.commit()
            with self.assertRaises(ValueError):m.connect(path)
            with closing(sqlite3.connect(path)) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],99)

    def test_cached_legacy_query_never_downloads(self):
        with tempfile.TemporaryDirectory() as temp,closing(m.connect(Path(temp)/'cache.sqlite')) as db,patch.object(m,'urlopen',side_effect=AssertionError('network forbidden')):
            self.assertEqual(m.query(db,m.registry(),'2026-10-24')['screenings'],[])

    def test_slow_collection_does_not_block_independent_readers(self):
        entered=threading.Event();release=threading.Event()
        venue={'id':'test','name':'Test','adapter':'aerokina','url':'https://test.example','coordinates':None}
        def slow(*_):
            entered.set();release.wait(5)
            return {'venue':venue,'error':'simulated outage','seconds':0}
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'collect',side_effect=slow):
            path=Path(temp)/'cache.sqlite'
            with closing(m.connect(path)):pass
            def worker():
                with closing(m.connect(path)) as db:m.refresh(db,[venue],'2026-10-24',force=True)
            thread=threading.Thread(target=worker);thread.start()
            try:
                self.assertTrue(entered.wait(2));start=time.perf_counter()
                with closing(m.connect(path)) as db:m.query(db,[venue],'2026-10-24')
                self.assertLess(time.perf_counter()-start,0.2)
            finally:release.set();thread.join(5)

if __name__=='__main__':unittest.main()
