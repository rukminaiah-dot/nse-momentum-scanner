from io import BytesIO
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from v2.backend.history_transport import HistoryApi, HistoryRequestError


class HistoryTransportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch('v2.backend.history_transport.COOLDOWN_PATH', Path(temp.name)/'cooldown')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_rate_limit_cooldown_prevents_subsequent_network_calls(self):
        api = HistoryApi('fake')
        with patch('v2.backend.history_transport.urlopen', side_effect=HTTPError('url',429,'limit',{'Retry-After':'90'},None)) as request:
            for _ in range(3):
                with self.assertRaises(HistoryRequestError) as caught:
                    api.get_intra_day_candle_data('KEY','minutes',15)
                self.assertEqual(caught.exception.status,429)
                self.assertGreater(caught.exception.retry_after,0)
            self.assertEqual(request.call_count,1)
            other_process_client = HistoryApi('fake')
            with self.assertRaises(HistoryRequestError):
                other_process_client.get_intra_day_candle_data('KEY','minutes',15)
            self.assertEqual(request.call_count,1)

    def test_both_endpoints_encode_keys_and_bound_response_reads(self):
        calls = []
        def open_request(request, **kwargs):
            calls.append((request, kwargs))
            return BytesIO(json.dumps({'data':{'candles':[['STAMP',1,2,1,2,10]]}}).encode())
        api = HistoryApi('fake-test-token')
        with patch('v2.backend.history_transport.urlopen', side_effect=open_request):
            historical = api.get_historical_candle_data1('NSE_INDEX|Nifty 50','minutes',15,'2026-10-25','2026-10-01')
            current = api.get_intra_day_candle_data('NSE_INDEX|Nifty 50','minutes',15)
        self.assertEqual(historical.data.candles, current.data.candles)
        self.assertTrue(calls[0][0].full_url.endswith('/NSE_INDEX%7CNifty%2050/minutes/15/2026-10-25/2026-10-01'))
        self.assertIn('/intraday/NSE_INDEX%7CNifty%2050/', calls[1][0].full_url)
        self.assertEqual([call[1]['timeout'] for call in calls], [20,20])
        self.assertNotIn('fake-test-token', calls[0][0].full_url)

    def test_provider_error_exposes_status_without_headers_or_body(self):
        with patch('v2.backend.history_transport.urlopen', side_effect=HTTPError('url',401,'secret',{},None)):
            with self.assertRaises(HistoryRequestError) as caught:
                HistoryApi('fake').get_intra_day_candle_data('KEY','minutes',15)
        self.assertEqual(caught.exception.status,401)
        self.assertNotIn('secret',str(caught.exception))

    def test_oversized_and_invalid_responses_are_rejected(self):
        for payload in [b'{"data":{}}',b'xxx']:
            with patch('v2.backend.history_transport.urlopen', return_value=BytesIO(payload)):
                with self.assertRaises(ValueError):
                    HistoryApi('fake').get_intra_day_candle_data('KEY','minutes',15)
        with patch('v2.backend.history_transport.MAX_HISTORY_BYTES', 2), patch('v2.backend.history_transport.urlopen', return_value=BytesIO(b'abc')):
            with self.assertRaises(ValueError):
                HistoryApi('fake').get_intra_day_candle_data('KEY','minutes',15)
