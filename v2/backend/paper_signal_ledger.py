"""Read-only paper signal ledger. No broker order placement or database connection."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass(frozen=True)
class Signal:
    instrument: str
    kind: str
    side: str
    price: float
    timestamp: datetime

@dataclass(frozen=True)
class ClosedCall:
    instrument: str
    kind: str
    bought_at: datetime
    sold_at: datetime
    buy_price: float
    sell_price: float
    points: float
    return_pct: float

class PaperLedger:
    """One long position per instrument; duplicate BUYs do not create trades."""
    def __init__(self):
        self.open = {}
        self.closed = []
        self.events = []
        self.rejected = []

    def record(self, signal: Signal) -> Optional[ClosedCall]:
        if (not isinstance(signal.timestamp, datetime) or
            signal.timestamp.tzinfo is not None or
            signal.kind not in ("stock", "index") or
            signal.side not in ("BUY", "SELL") or
            not isinstance(signal.instrument, str) or not signal.instrument.strip() or
            isinstance(signal.price, bool) or
            not isinstance(signal.price, (int, float))):
            raise ValueError("invalid signal")
        import math
        if not math.isfinite(signal.price) or signal.price <= 0:
            raise ValueError("price must be finite and positive")
        self.events.append(signal)
        prior = self.open.get(signal.instrument)
        if prior is not None and (prior.kind != signal.kind or signal.timestamp <= prior.timestamp):
            self.rejected.append((signal, "kind mismatch or non-increasing timestamp"))
            return None
        if signal.side == "BUY":
            if prior is not None:
                self.rejected.append((signal, "duplicate BUY"))
            else:
                self.open[signal.instrument] = signal
            return None
        if prior is None:
            self.rejected.append((signal, "SELL without BUY"))
            return None
        points = signal.price - prior.price
        result = ClosedCall(signal.instrument, signal.kind, prior.timestamp,
                            signal.timestamp, prior.price, signal.price,
                            points, 100 * points / prior.price)
        self.closed.append(result)
        del self.open[signal.instrument]
        return result

    def summary(self, kind=None):
        calls = [c for c in self.closed if kind is None or c.kind == kind]
        wins = sum(c.points > 0 for c in calls)
        losses = sum(c.points < 0 for c in calls)
        flat = len(calls) - wins - losses
        return {"closed_calls": len(calls), "wins": wins, "losses": losses,
                "flat": flat, "win_rate_pct": 100 * wins / len(calls) if calls else None,
                "open_calls": sum(s.kind == kind or kind is None for s in self.open.values()),
                "gross_positive_points": sum(max(c.points, 0) for c in calls),
                "gross_negative_points": sum(min(c.points, 0) for c in calls),
                "net_points": sum(c.points for c in calls)}
