from email.message import Message
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.robotparser import RobotFileParser

import moviecache as m

class TransportTests(unittest.TestCase):
    def setUp(self):
        robot=RobotFileParser();robot.parse([])
        self.robots=patch.dict(m._robots,{'test.example':robot});self.robots.start()
        self.sleep=patch.object(m.time,'sleep');self.sleep.start()
    def tearDown(self):self.robots.stop();self.sleep.stop()
    def test_304_reuses_body_and_current_parser_still_validates(self):
        error=HTTPError('https://test.example',304,'Not Modified',Message(),None)
        page={'body':'malformed old body','etag':'test','modified':None}
        with patch.object(m,'urlopen',side_effect=error):
            self.assertEqual(m.fetch('https://test.example',page)[0],page['body'])
            result=m.collect({'id':'test','adapter':'aerokina','url':'https://test.example'},page)
            self.assertIn('error',result)
    def test_long_retry_after_defers_without_hammering(self):
        headers=Message();headers['Retry-After']='120'
        with patch.object(m,'urlopen',side_effect=HTTPError('https://test.example',429,'Rate limited',headers,None)) as fetch:
            with self.assertRaisesRegex(ValueError,'Retry-After'):m.fetch('https://test.example')
            self.assertEqual(fetch.call_count,1)
    def test_robots_denial_never_fetches_programme(self):
        deny=RobotFileParser();deny.parse(['User-agent: *','Disallow: /'])
        with patch.dict(m._robots,{'test.example':deny}),patch.object(m,'urlopen',side_effect=AssertionError('must not fetch')):
            with self.assertRaisesRegex(ValueError,'disallows'):m.fetch('https://test.example/programme')

if __name__=='__main__':unittest.main()
