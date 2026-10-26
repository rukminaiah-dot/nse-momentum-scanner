import unittest
from types import SimpleNamespace
from v2.backend.history_transport import BoundedHistoryApi


class HistoryTransportTests(unittest.TestCase):
    def test_both_history_methods_receive_connection_and_read_deadlines(self):
        calls = []
        def request(*args, **kwargs):
            calls.append((args, kwargs))
            return 'response'
        api = BoundedHistoryApi(SimpleNamespace(get_historical_candle_data1=request,
                                               get_intra_day_candle_data=request))
        self.assertEqual(api.get_historical_candle_data1('KEY','minutes',15,'2026-10-25','2026-10-01'), 'response')
        self.assertEqual(api.get_intra_day_candle_data('KEY','minutes',15), 'response')
        self.assertEqual([call[1]['_request_timeout'] for call in calls], [(5,15),(5,15)])
        self.assertEqual(calls[0][0][-2:], ('2026-10-25','2026-10-01'))
