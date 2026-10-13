"""Opt-in isolated gap scheduling for websocket-fed candle state.

Never calls broker APIs on the feed thread. No production scanner imports.
"""
from datetime import timedelta

from isolated_live_tick_candles import IsolatedTickCandles
from v2.backend.gap_recovery_worker import GapRecoveryWorker


class IsolatedStreamRecovery:
    def __init__(self, instrument, fetch_rows, *, cooldown=120,
                 max_pending=1, min_request_spacing=1.0):
        self.candles = IsolatedTickCandles(instrument)
        self.instrument = instrument
        self.worker = GapRecoveryWorker(
            fetch_rows, self.candles.manager.recovery_snapshot,
            self.candles.manager.merge_recovered, cooldown=cooldown,
            max_pending=max_pending, min_request_spacing=min_request_spacing)
        self.gap_requests = 0

    def on_message(self, payload):
        # Compare active minute before/after under the manager lock. The
        # worker's request() only schedules; broker I/O runs on its own thread.
        from isolated_live_tick_candles import extract_tick
        tick = extract_tick(payload, self.instrument)
        if tick is None:
            return False
        manager = self.candles.manager
        with manager.lock:
            before = manager.current.get(self.instrument)
            previous = before["minute"] if before else None
            accepted = self.candles.on_message(payload)
            after = manager.current.get(self.instrument)
            current = after["minute"] if after else None
            if (accepted and previous is not None and current is not None
                    and current.date() == previous.date()
                    and current - previous > timedelta(minutes=1)):
                # Schedule before releasing manager lock so concurrent callbacks
                # cannot race and silently skip a detected minute jump.
                if self.worker.request(self.instrument):
                    self.gap_requests += 1
        return accepted
