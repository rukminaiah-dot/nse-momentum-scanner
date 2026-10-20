import unittest
from unittest.mock import patch

from v2.backend.upstox_quote_client import _request_json, fetch_full_quotes, fetch_quote_groups


class UpstoxQuoteClientTests(unittest.TestCase):
    def test_uses_v3_when_available(self):
        calls = []

        def request(path, token, keys):
            calls.append((path, token, keys))
            return {"status": "success", "data": {"GLOBAL_INDEX:GIFT NIFTY": {"last_price": 1}}}

        data, source = fetch_full_quotes(["GLOBAL_INDEX|GIFT NIFTY"], ["token"], request_json=request)

        self.assertIn("GLOBAL_INDEX:GIFT NIFTY", data)
        self.assertEqual(source, "Upstox Full Market Quotes V3")
        self.assertEqual([call[0] for call in calls], ["/v3/market-quote/quotes"])

    def test_uses_v2_when_v3_is_rejected(self):
        calls = []

        def request(path, _token, _keys):
            calls.append(path)
            if path.startswith("/v3/"):
                raise PermissionError("V3 unavailable")
            return {"status": "success", "data": {"NSE_INDEX:India VIX": {"last_price": 14}}}

        data, source = fetch_full_quotes(["NSE_INDEX|India VIX"], ["token"], request_json=request)

        self.assertIn("NSE_INDEX:India VIX", data)
        self.assertEqual(source, "Upstox Full Market Quotes V2")
        self.assertEqual(calls, ["/v3/market-quote/quotes", "/v2/market-quote/quotes"])

    def test_tries_compatibility_paths_before_next_configured_token(self):
        calls = []

        def request(path, token, _keys):
            calls.append((path, token))
            if token == "first":
                raise PermissionError("not authorized")
            return {"status": "success", "data": {}}

        _data, source = fetch_full_quotes(["GLOBAL_INDEX|GIFT NIFTY"], ["first", "second"], request_json=request)

        self.assertEqual(source, "Upstox Full Market Quotes V3")
        self.assertEqual(calls, [
            ("/v3/market-quote/quotes", "first"),
            ("/v2/market-quote/quotes", "first"),
            ("/v3/market-quote/quotes", "second"),
        ])

    def test_never_returns_success_with_invalid_payload(self):
        def request(_path, _token, _keys):
            return {"status": "success", "data": []}

        with self.assertRaisesRegex(ValueError, "not successful"):
            fetch_full_quotes(["GLOBAL_INDEX|GIFT NIFTY"], ["token"], request_json=request)

    def test_failure_keeps_only_endpoint_status_diagnostics(self):
        def request(path, _token, _keys):
            error = PermissionError("private provider response text")
            error.code = 403
            raise error

        with self.assertRaises(PermissionError) as raised:
            fetch_full_quotes(["GLOBAL_INDEX|GIFT NIFTY"], ["secret-token"], request_json=request)

        self.assertEqual(raised.exception.upstox_attempts, [
            {"api": "v3", "status_code": 403, "error": None},
            {"api": "v2", "status_code": 403, "error": None},
        ])
        self.assertNotIn("secret-token", repr(raised.exception.upstox_attempts))
        self.assertNotIn("private provider response text", repr(raised.exception.upstox_attempts))

    def test_one_feed_failure_does_not_hide_other_quote_groups(self):
        def request(path, _token, keys):
            if "GLOBAL_INDEX" in keys[0]:
                error = PermissionError("global feed unavailable")
                error.code = 403
                raise error
            return {"status": "success", "data": {"NSE_INDEX:India VIX": {"last_price": 14}}}

        groups, errors = fetch_quote_groups({
            "global_indices": ["GLOBAL_INDEX|GIFT NIFTY"],
            "sector_indices": ["NSE_INDEX|Nifty Bank"],
            "india_vix": ["NSE_INDEX|India VIX"],
        }, ["token"], request_json=request)

        self.assertNotIn("global_indices", groups)
        self.assertEqual(set(groups), {"sector_indices", "india_vix"})
        self.assertEqual(set(errors), {"global_indices"})

    def test_upstox_request_uses_the_known_working_user_agent(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"status":"success","data":{}}'

        with patch("v2.backend.upstox_quote_client.urllib.request.urlopen", return_value=Response()) as opener:
            _request_json("/v3/market-quote/quotes", "token", ["NSE_INDEX|India VIX"])

        request = opener.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), "Mozilla/5.0 NSE-Momentum-Scanner/1.0")

    def test_financial_services_uses_upstox_index_instrument_name(self):
        from pathlib import Path

        api = (Path(__file__).resolve().parents[1] / "v2/backend/api.py").read_text(encoding="utf-8")
        self.assertIn('"NIFTY FINANCIAL SERVICES": "NSE_INDEX|Nifty Fin Service"', api)


if __name__ == "__main__":
    unittest.main()
