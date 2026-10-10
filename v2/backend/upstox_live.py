import os
import upstox_client

from .market_config import INDICES
from .stock_universe import NIFTY_200


class UpstoxLiveV3:
    def __init__(self, on_tick=None):
        self.on_tick = on_tick
        token = os.getenv("UPSTOX_ACCESS_TOKEN")
        if not token:
            raise RuntimeError("UPSTOX_ACCESS_TOKEN missing")

        config = upstox_client.Configuration()
        config.access_token = token

        self.api_client = upstox_client.ApiClient(config)
        self.instrument_keys = list(INDICES.values()) + list(NIFTY_200.values())
        print('V2 LIVE UNIVERSE:', len(self.instrument_keys), 'instruments')

        self.streamer = upstox_client.MarketDataStreamerV3(
            self.api_client,
            self.instrument_keys,
            "full",
        )

        self.streamer.on("open", self._on_open)
        self.streamer.on("message", self._on_message)
        self.streamer.on("error", self._on_error)
        self.streamer.on("close", self._on_close)


    def _connection_event(self, status):
        import json
        from datetime import datetime
        from pathlib import Path
        from zoneinfo import ZoneInfo
        try:
            path = Path("/tmp/nse_200_connection_health.json")
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"status": status, "event_at_ist": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()}))
            tmp.replace(path)
        except OSError as exc:
            print("CONNECTION_HEALTH_WRITE_ERROR:", type(exc).__name__, flush=True)

    def _on_close(self, *args):
        self._connection_event("CLOSED")
        print("V2_UPSTOX_V3_CLOSED", flush=True)

    def _on_open(self):
        self._connection_event("CONNECTED")
        print("V2_UPSTOX_V3_CONNECTED")

    def _on_message(self, message):
        if message.get("type") == "market_info":
            return

        if not hasattr(self, "_raw_structure_logged") and message.get("feeds"):
            feeds_sample = message["feeds"]
            sample = next(iter(feeds_sample.values()))
            print("UPSTOX_RAW_STRUCTURE:", {
                "message_keys": list(message.keys()),
                "feed_keys": list(sample.keys()),
                "full_feed_keys": list(sample.get("fullFeed", {}).keys()),
            }, flush=True)
            self._raw_structure_logged = True

        feeds = message.get("feeds", {})

        for instrument_key, feed in feeds.items():
            ltpc = feed.get("ltpc") or (feed.get("ff") or feed.get("fullFeed") or {}).get("marketFF", {}).get("ltpc") or (feed.get("ff") or feed.get("fullFeed") or {}).get("indexFF", {}).get("ltpc")
            if not ltpc:
                continue

            if self.on_tick:
                tick = dict(ltpc)
                market_ff = (feed.get("ff") or feed.get("fullFeed") or {}).get("marketFF", {})
                tick["vtt"] = market_ff.get("vtt")
                if market_ff and not hasattr(self, "_volume_sample_logged"):
                    print("UPSTOX_FEED_STRUCTURE:", {
                        "feed_keys": list(feed.keys()),
                        "full_feed_keys": list((feed.get("ff") or feed.get("fullFeed") or {}).keys()),
                        "market_ff_keys": list(market_ff.keys()),
                        "details": market_ff.get("eFeedDetails")
                    }, flush=True)
                    self._volume_sample_logged = True
                self.on_tick(instrument_key, tick)

    def _on_error(self, error):
        self._connection_event("ERROR")
        print("V2_UPSTOX_V3_ERROR:", error)

    def connect(self):
        self._connection_event("CONNECTING")
        self.streamer.connect()


if __name__ == "__main__":
    UpstoxLiveV3().connect()
