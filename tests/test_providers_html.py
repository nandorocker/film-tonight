"""Offline contract tests using attributed synthetic official-site structures."""
from pathlib import Path
import json
import socket
import unittest
from unittest.mock import patch

from providers_html import PARSERS


FIXTURES = Path(__file__).parent / 'fixtures' / 'html'
VENUE = {'id': 'example', 'url': 'https://cinema.example/program'}


def fixture(name):
    return (FIXTURES / (name + '.html')).read_text()


class HtmlProvidersTest(unittest.TestCase):
    def setUp(self):
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def parse(self, name, source=None, day='2026-10-24'):
        return PARSERS[name](fixture(name) if source is None else source, VENUE, day)

    def test_all_adapters_offline_contract(self):
        for name in PARSERS:
            with self.subTest(name=name):
                dates, rows = self.parse(name)
                self.assertIn('2026-10-24', dates)
                self.assertTrue(rows)
                self.assertEqual(len(rows), len({r['id'] for r in rows}))
                for row in rows:
                    self.assertIn(row['starts_at'][:10], dates)
                    self.assertRegex(row['starts_at'], r'\+0[12]:00$')
                    self.assertIsNotNone(row['language_evidence']['raw_label'])
                    self.assertTrue(row['booking_url'].startswith(('https://', 'http://')))

    def test_missing_structure_is_not_empty_success(self):
        for name in PARSERS:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.parse(name, '<html>Programme coming soon</html>')

    def test_explicit_dated_empty_programmes(self):
        sources = {
            'pilotu': '<div class="swiper-slide day">25. října</div><div class="swiper-slide event"><ul></ul></div>',
            'kino35': '<table><tr class="header"><td>25. 10.</td></tr></table>',
        }
        for name, source in sources.items():
            with self.subTest(name=name):
                self.assertEqual(self.parse(name, source), ({'2026-10-25'}, []))

    def test_missing_date_is_not_reported_published(self):
        for name in PARSERS:
            with self.subTest(name=name):
                dates, _ = self.parse(name, day='2026-11-01')
                self.assertNotIn('2026-11-01', dates)

    def test_atlas_source_ids_and_sold_out_detail_fallback(self):
        dates, rows = self.parse('atlas')
        self.assertEqual(dates, {'2026-10-24'})
        self.assertEqual([r['provider_id'] for r in rows], ['101', '102'])
        self.assertEqual([r['access'] for r in rows], ['english_friendly', 'unknown'])
        self.assertEqual(rows[1]['booking_url'], 'https://cinema.example/program?program=102')
        with self.assertRaises(ValueError):
            self.parse('atlas', fixture('atlas').replace('>18:00<', '>19:00<', 1))

    def test_pilotu_screening_suffixes_and_explicit_empty_slide(self):
        dates, rows = self.parse('pilotu')
        self.assertEqual(dates, {'2026-10-24', '2026-10-25'})
        self.assertEqual([r['access'] for r in rows], ['english_friendly', 'english_subtitles', 'unknown'])
        self.assertEqual(rows[0]['provider_id'], '101')
        with self.assertRaises(ValueError):
            self.parse('pilotu', fixture('pilotu').replace('swiper-slide day selected', 'other'))

    def test_kavalirka_session_labels_and_non_film(self):
        _, rows = self.parse('kavalirka')
        self.assertEqual([r['access'] for r in rows], ['not_english', 'english_friendly', 'unknown'])
        self.assertEqual(rows[2]['event_type'], 'non_film')
        self.assertIn('English Friendly', rows[1]['language_evidence']['raw_label'])

    def test_kino35_audio_subtitles_price_and_explicit_empty_header(self):
        dates, rows = self.parse('kino35')
        self.assertIn('2026-10-25', dates)
        self.assertEqual(rows[0]['audio'], ['fr'])
        self.assertEqual(rows[0]['subtitles'], ['en'])
        self.assertEqual(rows[0]['price'], 180)
        self.assertEqual(rows[0]['access'], 'english_subtitles')
        self.assertEqual(rows[1]['access'], 'english_friendly')
        with self.assertRaises(ValueError):
            self.parse('kino35', fixture('kino35').replace('2026-10-24T13', '2026-10-25T13'))

    def test_ponrepo_country_is_not_audio_and_dst_offsets_preserved(self):
        _, rows = self.parse('ponrepo')
        self.assertEqual([r['access'] for r in rows], ['english_friendly', 'unknown'])
        self.assertEqual(rows[0]['audio'], [])
        self.assertEqual(rows[0]['format'], '35 mm')
        self.assertTrue(rows[0]['starts_at'].endswith('+02:00'))
        self.assertTrue(rows[1]['starts_at'].endswith('+01:00'))

    def test_edison_arrays_mixed_audio_subtitles_unknown_and_non_film(self):
        dates, rows = self.parse('edison')
        self.assertEqual(dates, {'2026-10-24', '2026-10-25'})
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['audio'], ['he', 'hu', 'en'])
        self.assertEqual(rows[0]['subtitles'], ['cs', 'en'])
        self.assertEqual(rows[0]['access'], 'english_subtitles')
        self.assertEqual(rows[2]['access'], 'unknown')
        self.assertEqual(rows[3]['event_type'], 'non_film')
        self.assertEqual(rows[3]['access'], 'english_audio')

    def test_identity_never_silently_merges(self):
        for name in ('atlas', 'ponrepo', 'edison'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.parse(name, fixture(name) + fixture(name))

    def test_edison_bad_link_and_date_only_are_rejected(self):
        for old, new in [('2026-10-24T20:45', '2026-10-24'),
                         ('https://edisonfilmhub.cz/filmy/example', 'javascript:alert(1)')]:
            with self.subTest(new=new), self.assertRaises(ValueError):
                self.parse('edison', fixture('edison').replace(old, new))

    def test_edison_slash_audio_case_and_unspecified_audio(self):
        cases = [('ESP/EN, Sub. CZ', ['es', 'en'], ['cs'], 'unknown'),
                 ('XX, EN, Sub. CZ', ['xx', 'en'], ['cs'], 'unknown'),
                 ('Festival En, Sub. CZ', ['en'], ['cs'], 'english_audio'),
                 (' EN ', ['en'], [], 'english_audio'),
                 ('Mezipatra various, Sub. CZ, EN', [], ['cs', 'en'], 'english_subtitles')]
        for raw, audio, subtitles, access in cases:
            with self.subTest(raw=raw):
                _, rows = self.parse('edison', fixture('edison').replace('Festival HE, HU, EN, Sub. CZ, EN ', raw))
                self.assertEqual(rows[0]['audio'], audio)
                self.assertEqual(rows[0]['subtitles'], subtitles)
                self.assertEqual(rows[0]['access'], access)

    def test_mat_ids_unknown_language_ordered_year_rollover_and_announcements(self):
        dates, rows = self.parse('mat')
        self.assertEqual(dates, {'2026-10-24', '2027-03-10'})
        self.assertEqual([r['provider_id'] for r in rows], ['101', '102', '104'])
        self.assertTrue(all(r['access'] == 'unknown' for r in rows))
        self.assertEqual(rows[0]['price'], 159)
        self.assertEqual(rows[1]['event_type'], 'non_film')
        self.assertEqual(rows[0]['title'], 'Example')
        self.assertNotEqual(rows[0]['id'], rows[1]['id'])
        self.assertNotIn('2026-10-25', dates)  # Blank-time announcement, not empty publication.
        with self.assertRaises(ValueError):
            self.parse('mat', fixture('mat').replace('>14.00<', '>bad<', 1))
        with self.assertRaises(ValueError):
            self.parse('mat', fixture('mat').replace('data-definitionid="101"', 'broken="101"'))

    def test_premiere_branch_dates_versions_and_unpublished_tabs(self):
        dates, rows = self.parse('premiere_hostivar')
        self.assertEqual(dates, {'2026-10-24', '2026-10-25', '2026-12-15'})
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(r['access'] == 'unknown' for r in rows))
        self.assertEqual(rows[0]['title'], 'Example')
        self.assertEqual(rows[0]['format'], '4K')
        self.assertEqual(rows[2]['provider_id'], '101')
        self.assertEqual(rows[3]['starts_at'], '2026-10-25T20:00:00+01:00')
        self.assertEqual(rows[4]['starts_at'][:10], '2026-12-15')
        with self.assertRaises(ValueError):
            self.parse('premiere_hostivar', fixture('premiere_hostivar').replace('Praha Hostivař', 'Olomouc'))
        with self.assertRaises(ValueError):
            self.parse('premiere_hostivar', fixture('premiere_hostivar').replace('id="tab-2"', 'id="tab-9"'))
        with self.assertRaises(ValueError):
            self.parse('premiere_hostivar', fixture('premiere_hostivar').replace('>14:30<', '>bad<'))

    def test_dlabacov_session_audio_generic_subtitles_and_identity(self):
        dates, rows = self.parse('dlabacov')
        self.assertEqual(dates, {'2026-10-24', '2026-10-25'})
        self.assertEqual([r['access'] for r in rows], ['english_audio', 'not_english', 'unknown'])
        self.assertEqual(rows[0]['subtitles'], [])  # ID 67 is not English subtitles.
        self.assertEqual(rows[1]['dubbed'], ['cs'])
        self.assertEqual(rows[2]['event_type'], 'non_film')
        self.assertEqual([r['provider_id'] for r in rows], ['101', '102', '103'])
        self.assertEqual(rows[0]['language_evidence']['raw_label']['langs'], [67])
        self.assertEqual(rows[0]['price'], 150)
        for source in [fixture('dlabacov').replace('"success"', '"error"'),
                       fixture('dlabacov').replace('"24.10"', '"24.11"'),
                       fixture('dlabacov').replace('"18:00"', '"bad"', 1)]:
            with self.assertRaises(ValueError):
                self.parse('dlabacov', source)

    def test_dlabacov_unknown_mixed_audio_never_becomes_english_only(self):
        source = fixture('dlabacov').replace('["Angličtina"]', '["Angličtina", "Unknown label"]')
        _, rows = self.parse('dlabacov', source)
        self.assertEqual(rows[0]['access'], 'unknown')
        self.assertEqual(rows[0]['audio'], ['en', 'und'])
        _, rows = self.parse('dlabacov', fixture('dlabacov').replace('["Angličtina"]', '["Unknown label"]'))
        self.assertEqual(rows[0]['access'], 'unknown')

    def test_dlabacov_duplicate_screening_is_not_merged(self):
        source = json.loads(fixture('dlabacov'))
        sessions = source['data']['2026']['10']['24.10']
        sessions.append(sessions[0])
        with self.assertRaises(ValueError):
            self.parse('dlabacov', json.dumps(source))

    def test_balt_canonical_microdata_halls_runtime_and_language(self):
        dates, rows = self.parse('balt')
        self.assertEqual(len(rows), 3)  # Not the Blockbuster promotion.
        self.assertEqual(dates, {'2026-10-24', '2026-10-25'})
        self.assertEqual([r['access'] for r in rows], ['unknown', 'not_english', 'not_english'])
        self.assertEqual(rows[0]['source_url'], 'https://kinobalt.cz/')
        self.assertEqual(rows[0]['booking_url'], 'https://kinobalt.cz/')
        self.assertEqual(rows[0]['availability_reported'], 'sold_out')
        self.assertEqual(rows[0]['ends_at'], '2026-10-24T19:34:00+02:00')
        self.assertNotEqual(rows[0]['id'], rows[1]['id'])  # Same title/start, different halls.
        self.assertEqual(rows[2]['title'], 'Another: special screening')
        self.assertEqual(rows[2]['dubbed'], ['sk'])
        with self.assertRaises(ValueError):
            self.parse('balt', fixture('balt').replace('2026-10-24T18:00', '2026-10-25T02:30'))
        with self.assertRaises(ValueError):
            self.parse('balt', fixture('balt').replace('c-Tags-item--place', 'broken', 1))
        with self.assertRaises(ValueError):
            self.parse('balt', fixture('balt') + fixture('balt'))

    def test_yearless_horizon_and_new_year(self):
        for name in ('pilotu', 'kavalirka', 'kino35', 'mat', 'premiere_hostivar'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.parse(name, day='2026-04-01')
        source = fixture('kavalirka').replace('24. 10.', '31. 12.').replace('25. 10.', '1. 1.')
        dates, rows = self.parse('kavalirka', source, day='2026-12-31')
        self.assertEqual(dates, {'2026-12-31', '2027-01-01'})

    def test_ambiguous_naive_dst_time_rejected(self):
        for name in ('atlas', 'edison'):
            source = fixture(name).replace('2026-10-24 18:00:00', '2026-10-25 02:30:00') if name == 'atlas' else fixture(name).replace('2026-10-24T20:45', '2026-10-25T02:30')
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.parse(name, source)

    def test_malformed_sessions_fail_not_partial_success(self):
        mutations = {
            'atlas': ('class="title"', 'class="broken"'),
            'pilotu': ('>19:10<', '>bad<'),
            'kavalirka': ('page__program-hours', 'broken'),
            'kino35': ('class="ticket"', 'class="broken"'),
            'ponrepo': ('event-item__details', 'broken'),
            'edison': ('"startDate"', '"broken"'),
        }
        for name, (old, new) in mutations.items():
            with self.subTest(name=name), self.assertRaises((ValueError, KeyError)):
                self.parse(name, fixture(name).replace(old, new, 1))


if __name__ == '__main__':
    unittest.main()
