from datetime import datetime
import json
import unittest
from providers import classify,parse_cinema_city,parse_cinestar,local_instant,record

class ProviderTests(unittest.TestCase):
    def nuxt(self,value):
        values=[]
        def pack(x):
            index=len(values);values.append(None)
            values[index]={k:pack(v) for k,v in x.items()} if isinstance(x,dict) else [pack(v) for v in x] if isinstance(x,list) else x
            return index
        pack(value)
        return '<script id="__NUXT_DATA__" type="application/json">'+json.dumps(values)+'</script>'

    def test_cinestar_session_legend_not_generic_subtitles_or_original_title(self):
        venue={'id':'cs','provider_id':'11','url':'https://cinestar.cz/cz/praha5/program'}
        labels=[['Titulky'],['ENG + CZ titulky'],['CZE + ENG titulky'],['Dabing'],['ORIGINAL + ENG titulky']]
        events=[{'EventId':str(i),'Start':'2026-10-24T18:00:00+00:00','Finish':'2026-10-24T20:00:00+00:00','TitleId':str(i),'ObjectId':'hall','Properties':[{'Name':x} for x in names]} for i,names in enumerate(labels)]
        data={'data':{'fixture':{'cinemaHallsEntries':[{'ObjectId':'hall','CinemaId':'11','Properties':[{'Name':'Hall 1'}]}],'scheduledEventsEntries':events}}}
        package={'programme':self.nuxt(data),'metadata':{str(i):{'title':'Same film version '+str(i),'url':'https://cinestar.cz/cz/praha5/filmy/movie/'+str(i),'checked_at':'2026-10-24T16:00:00Z'} for i in range(5)}}
        dates,rows=parse_cinestar(json.dumps(package),venue,'2026-10-24')
        self.assertEqual([r['access'] for r in rows],['unknown','english_audio','english_subtitles','not_english','english_subtitles'])
        self.assertEqual(len({r['id'] for r in rows}),5)
        del package['metadata']['0']
        with self.assertRaisesRegex(ValueError,'metadata'):parse_cinestar(json.dumps(package),venue,'2026-10-24')

    def test_language_rules(self):
        self.assertEqual(classify(['en'],['cs']),'english_audio')
        self.assertEqual(classify(['en'],[],['cs']),'not_english')
        self.assertEqual(classify(['fr'],['en']),'english_subtitles')
        self.assertEqual(classify(['en','fr']),'unknown')
        self.assertEqual(classify([],[],[],True),'english_friendly')
        self.assertEqual(classify(['en'],['en'],['cs']),'english_subtitles')

    def test_city_sessions_not_film_language_or_title(self):
        venue={'id':'flora','provider_id':'1052','url':'https://www.cinemacity.cz/'}
        film={'id':'f','name':'An English title','attributeIds':['original-lang-en'],'length':100}
        def event(id,lang,hall):return {'id':id,'cinemaId':'1052','filmId':'f','eventDateTime':'2026-10-24T20:00:00','languages':lang,'attributeIds':['2d'],'bookingLink':'https://tickets.cinemacity.cz/api/order/'+id,'auditorium':hall}
        source=json.dumps({'body':{'films':[film],'events':[event('1',{'original':['en'],'subtitles':['cs']},'1'),event('2',{'original':['en'],'dubbed':['cs']},'2'),event('3',{},'3')]}})
        dates,rows=parse_cinema_city(source,venue,'2026-10-24')
        self.assertEqual([r['access'] for r in rows],['english_audio','not_english','unknown'])
        self.assertEqual(len({r['id'] for r in rows}),3)

    def test_local_dst_rejects_ambiguity_and_gap(self):
        for value in ['2026-10-25T02:30:00','2026-03-29T02:30:00']:
            with self.assertRaises(ValueError):local_instant(value)
        self.assertNotEqual(local_instant('2026-10-25T02:30:00+02:00'),local_instant('2026-10-25T02:30:00+01:00').astimezone(__import__('datetime').timezone.utc))

    def test_empty_city_api_is_not_published_zero(self):
        with self.assertRaises(ValueError):parse_cinema_city('{"body":{"films":[],"events":[]}}',{},'2026-10-24')

    def test_duration_is_elapsed_time_across_both_dst_transitions(self):
        venue={'id':'v','url':'https://cinema.example'}
        for start,expected in [('2026-10-25T01:30:00+02:00','2026-10-25T02:30:00+01:00'),('2026-03-29T01:30:00+01:00','2026-03-29T04:30:00+02:00')]:
            row=record(venue,'1','Film',local_instant(start),duration=120)
            self.assertEqual(row['ends_at'],expected)

    def test_unknown_language_tokens_remain_unknown(self):
        self.assertEqual(classify(['en + fr']),'unknown')
        self.assertEqual(classify(['xx']),'unknown')

if __name__=='__main__':unittest.main()
