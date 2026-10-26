from datetime import datetime, timedelta
from email.utils import format_datetime
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import collector_job as job


def http_error(status, retry=None):
    headers={} if retry is None else {'Retry-After':retry}
    return HTTPError('https://private.example/secret',status,'secret reason',headers,io.BytesIO(b'secret body'))


class PublicationTests(unittest.TestCase):
    def publish(self,path='internal/ingest'):
        return job.publish('https://cloud.example','test-only',path,{'generation':'2026-10-26T12:00:00Z','failed':False})

    def test_success_does_not_retry(self):
        with patch.object(job,'urlopen',return_value=io.BytesIO(b'{"ok":true}')) as send,patch.object(job.time,'sleep') as sleep:
            self.assertEqual(self.publish(),{'ok':True})
        send.assert_called_once()
        sleep.assert_not_called()

    def test_transient_http_errors_retry_identical_publications(self):
        for path in ('internal/ingest','internal/jobs'):
            for status in (429,500,502,503,504):
                with self.subTest(path=path,status=status):
                    error=http_error(status)
                    def pause(delay):
                        self.assertTrue(error.fp is None or error.fp.closed)
                        self.assertEqual(delay,1)
                    with patch.object(job,'urlopen',side_effect=[error,io.BytesIO(b'{"ok":true}')]) as send,patch.object(job.time,'sleep',side_effect=pause):
                        self.assertEqual(self.publish(path),{'ok':True})
                    requests=[call.args[0] for call in send.call_args_list]
                    self.assertIs(requests[0],requests[1])
                    self.assertEqual(requests[0].data,requests[1].data)

    def test_permanent_http_errors_are_closed_and_not_retried(self):
        for status in (400,401,403,404,413):
            with self.subTest(status=status):
                error=http_error(status)
                with patch.object(job,'urlopen',side_effect=error) as send,patch.object(job.time,'sleep') as sleep:
                    with self.assertRaises(HTTPError) as caught:self.publish()
                self.assertIs(caught.exception,error)
                self.assertTrue(error.fp is None or error.fp.closed)
                send.assert_called_once()
                sleep.assert_not_called()

    def test_transport_errors_retry_and_exhaustion_stays_failed(self):
        for error in (URLError('secret reason'),TimeoutError('secret'),ConnectionResetError('secret'),http_error(503)):
            with self.subTest(error=type(error).__name__):
                with patch.object(job,'urlopen',side_effect=error) as send,patch.object(job.time,'sleep') as sleep:
                    with self.assertRaises(type(error)):self.publish()
                self.assertEqual(send.call_count,3)
                self.assertEqual([c.args[0] for c in sleep.call_args_list],[1,2])
                with patch.object(job,'urlopen',side_effect=[error,io.BytesIO(b'{}')]),patch.object(job.time,'sleep'):
                    self.assertEqual(self.publish(),{})

    def test_retry_after_is_honored_or_deferred(self):
        now=datetime(2026,10,26,12,tzinfo=job.m.UTC)
        cases=[('0',0),('7',7),('30',30),('31',None),('garbage',1),
               (format_datetime(now+timedelta(seconds=10),usegmt=True),10),
               (format_datetime(now-timedelta(seconds=10),usegmt=True),0),
               (format_datetime(now+timedelta(seconds=60),usegmt=True),None)]
        for header,delay in cases:
            with self.subTest(header=header):
                error=http_error(503,header)
                with patch.object(job,'datetime') as clock,patch.object(job,'urlopen',side_effect=[error,io.BytesIO(b'{}')]) as send,patch.object(job.time,'sleep') as sleep:
                    clock.now.return_value=now
                    if delay is None:
                        with self.assertRaises(HTTPError):self.publish()
                        send.assert_called_once()
                        sleep.assert_not_called()
                    else:
                        self.assertEqual(self.publish(),{})
                        sleep.assert_called_once_with(delay)
                self.assertTrue(error.fp is None or error.fp.closed)

    def test_invalid_response_is_not_retried(self):
        with patch.object(job,'urlopen',return_value=io.BytesIO(b'not json')) as send,patch.object(job.time,'sleep') as sleep:
            with self.assertRaises(json.JSONDecodeError):self.publish()
        send.assert_called_once()
        sleep.assert_not_called()

    def test_error_fields_do_not_expose_secrets(self):
        self.assertEqual(job.error_fields(http_error(503)),{'type':'HTTPError','http_status':503})
        self.assertEqual(job.error_fields(URLError('https://secret:token@example.com/private')),{'type':'URLError'})


if __name__=='__main__':unittest.main()
