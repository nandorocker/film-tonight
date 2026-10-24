import json
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import moviecache as m


VENUE = {'id': 'test', 'name': 'Test cinema', 'url': 'https://cinema.example/en',
         'adapter': 'aerokina', 'coordinates': [14.4, 50.1]}


def page(audio='cs', tags=('ENG',), start='2026-10-24T20:00:00+02:00'):
    event = {'@type': 'Event', 'name': 'Test film', 'startDate': start,
             'inLanguage': audio, 'url': 'https://cinema.example/en?projection=1',
             'offers': {'price': '180', 'priceCurrency': 'CZK'}}
    local = m.instant(start).astimezone(m.PRAGUE)
    heading = local.strftime('program-day-%d-%m-%Y')
    return f'<a class="program__day" id="{heading}">Today</a><div class="program__info-row">' + ''.join(f'<span class="program__tag">{t}</span>' for t in tags) + '<script type="application/ld+json">' + json.dumps(event) + '</script></div>'


class LanguageTests(unittest.TestCase):
    def test_english_site_is_not_screening_evidence(self):
        _, rows = m.parse_aerokina(page(audio='fr', tags=()), VENUE)
        self.assertEqual(rows[0]['access'], 'unknown')

    def test_non_english_film_with_venue_tag(self):
        _, rows = m.parse_aerokina(page(), VENUE)
        self.assertEqual(rows[0]['access'], 'english_friendly')
        self.assertEqual(rows[0]['audio'], 'cs')

    def test_dubbing_overrides_original_english(self):
        self.assertEqual(m.language_access('en', ['ENG', 'Czech Dub']), 'not_english')
        self.assertEqual(m.language_access('en / ro / no', []), 'unknown')
        self.assertEqual(m.language_access('en / ro', ['ENG']), 'english_friendly')

    def test_broken_page_fails_instead_of_empty_success(self):
        with self.assertRaises(ValueError):
            m.parse_aerokina('<h1>Checking your browser</h1>', VENUE)

    def test_timestamp_must_be_aware(self):
        with self.assertRaises(ValueError):
            m.parse_aerokina(page(start='2026-10-24T20:00:00'), VENUE)

    def test_prague_date_and_dst(self):
        dates, rows = m.parse_aerokina(page(start='2026-10-24T22:30:00+00:00'), VENUE)
        self.assertEqual(dates, {'2026-10-25'})
        self.assertEqual(rows[0]['starts_at'], '2026-10-25T00:30:00+02:00')
        _, rows = m.parse_aerokina(page(start='2026-10-25T18:00:00+00:00'), VENUE)
        self.assertEqual(rows[0]['starts_at'], '2026-10-25T19:00:00+01:00')


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.db = m.connect(Path(self.temp.name) / 'cache.sqlite')
        _, self.rows = m.parse_aerokina(page(), VENUE)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def add(self, kind='live', checked='2026-10-24T15:55:00+00:00'):
        with self.db:
            m.write_snapshot(self.db, 'test', '2026-10-24', self.rows, VENUE['url'], kind=kind, checked_at=checked)

    def test_sample_never_counts_as_fresh(self):
        self.add(kind='manual_sample')
        row = m.newest(self.db, 'test', '2026-10-24')
        now = datetime(2026,10,24,15,56,tzinfo=timezone.utc)
        self.assertFalse(m.fresh(row, 900, now))

    def test_expiry_boundary_and_future_clock(self):
        self.add()
        row = m.newest(self.db, 'test', '2026-10-24')
        self.assertTrue(m.fresh(row, 900, datetime(2026,10,24,16,10,tzinfo=timezone.utc)))
        self.assertFalse(m.fresh(row, 900, datetime(2026,10,24,16,11,tzinfo=timezone.utc)))
        self.assertFalse(m.fresh(row, 900, datetime(2026,10,24,15,54,tzinfo=timezone.utc)))

    def test_failed_refresh_keeps_last_good_and_exposes_failure(self):
        self.add()
        with patch.object(m, 'download', side_effect=TimeoutError('offline')):
            report = m.refresh(self.db, [VENUE], '2026-10-24', force=True)
        self.assertEqual(report[0]['outcome'], 'error')
        result = m.query(self.db, [VENUE], '2026-10-24')
        self.assertEqual(len(result['screenings']), 1)
        self.assertEqual(result['coverage'][0]['last_attempt']['outcome'], 'error')

    def test_unpublished_date_does_not_imply_no_screenings(self):
        with patch.object(m, 'download', return_value=(page(), None, None)):
            report = m.refresh(self.db, [VENUE], '2026-11-10', force=True)
        self.assertEqual(report[0]['outcome'], 'unpublished')
        self.assertEqual(m.query(self.db, [VENUE], '2026-11-10')['coverage'][0]['state'], 'unpublished')

    def test_date_and_language_filter_and_geojson(self):
        self.add()
        self.assertEqual(len(m.query(self.db, [VENUE], '2026-10-25')['screenings']), 0)
        result = m.query(self.db, [VENUE], '2026-10-24')
        self.assertEqual(m.geojson(result)['features'][0]['geometry']['coordinates'], [14.4, 50.1])
        self.rows[0]['access'] = 'conflict'
        self.add()
        self.assertEqual(len(m.query(self.db, [VENUE], '2026-10-24')['screenings']), 0)
        self.assertEqual(len(m.query(self.db, [VENUE], '2026-10-24', include_uncertain=True)['screenings']), 1)

    def test_unknown_coordinates_remain_in_list_but_not_map_points(self):
        self.add()
        result = m.query(self.db, [dict(VENUE, coordinates=None)], '2026-10-24')
        mapped = m.geojson(result)
        self.assertEqual(len(result['screenings']), 1)
        self.assertEqual(mapped['features'], [])
        self.assertEqual(mapped['unmapped_venue_ids'], ['test'])


if __name__ == '__main__':
    unittest.main()
