"""Volume metrics from observed completed candles and dated Upstox history."""

from datetime import timedelta
from math import isfinite


class CompactSameSlotVolumeHistory:
    """Columnar 20-session 5-minute volume archive for low-memory scanners."""

    __slots__ = ("slots", "row_count")

    def __init__(self, slots, row_count):
        self.slots = slots
        self.row_count = row_count


def compact_same_slot_volume_rows(historical_rows, reference_sessions=20):
    """Keep only date and volume by time slot in compact numeric arrays.

    Upstox returns OHLC fields as well as volume. The setup scanner only needs
    the historical date, 5-minute slot, and volume for its RVOL baseline.
    Retaining those fields avoids holding every full API candle in memory.
    """
    from array import array
    from datetime import datetime
    from zoneinfo import ZoneInfo

    if (not isinstance(reference_sessions, int) or isinstance(reference_sessions, bool)
            or reference_sessions < 1):
        raise ValueError("reference_sessions must be a positive integer")
    ist = ZoneInfo("Asia/Kolkata")
    by_slot = {}
    for row in historical_rows or ():
        try:
            stamp = row[0]
            if isinstance(stamp, str):
                stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if stamp.tzinfo is not None:
                stamp = stamp.astimezone(ist).replace(tzinfo=None)
            volume = float(row[5])
            if not isfinite(volume) or volume < 0:
                continue
            slot = (stamp.hour, stamp.minute)
            by_slot.setdefault(slot, {})[stamp.date().toordinal()] = volume
        except (IndexError, TypeError, ValueError, OverflowError, AttributeError):
            continue

    packed = {}
    for slot, by_date in by_slot.items():
        ordered = sorted(by_date.items())[-reference_sessions:]
        values = array("d")
        for ordinal, volume in ordered:
            values.extend((ordinal, volume))
        packed[slot] = values
    return CompactSameSlotVolumeHistory(packed, sum(len(v) // 2 for v in packed.values()))


def verified_relative_volume(candles, reference_bars=19):
    """Return one-minute RVOL only for a complete, same-session comparison.

    RVOL is the latest completed candle's actual volume divided by the mean
    volume of the preceding ``reference_bars`` consecutive completed candles.
    Missing candles, overnight crossings, invalid values, and zero baselines
    produce no result rather than an estimated ratio.
    """
    if (isinstance(reference_bars, bool) or not isinstance(reference_bars, int)
            or reference_bars < 1):
        raise ValueError("reference_bars must be a positive integer")

    window = list(candles)[-(reference_bars + 1):]
    if len(window) != reference_bars + 1:
        return None

    timestamps = [getattr(candle, "timestamp", None) for candle in window]
    if any(stamp is None for stamp in timestamps):
        return None
    if any(stamp.date() != timestamps[-1].date() for stamp in timestamps):
        return None
    if any(timestamps[i] - timestamps[i - 1] != timedelta(minutes=1)
           for i in range(1, len(timestamps))):
        return None

    try:
        volumes = [float(candle.volume) for candle in window]
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None
    if not all(isfinite(volume) and volume >= 0 for volume in volumes):
        return None

    baseline = sum(volumes[:-1]) / reference_bars
    if baseline <= 0:
        return None
    current = volumes[-1]
    return {
        "relative_volume": current / baseline,
        "current_volume": current,
        "baseline_volume": baseline,
        "reference_bars": reference_bars,
    }



def completed_intraday_bars(candles, interval_minutes=15, *, include_all_sessions=False):
    """Aggregate full contiguous one-minute bars into intraday bars.

    By default only the latest session is returned, preserving existing callers.
    ``include_all_sessions`` is for verified historical same-slot baselines.
    """
    if (isinstance(interval_minutes, bool) or not isinstance(interval_minutes, int)
            or interval_minutes < 1):
        raise ValueError("interval_minutes must be a positive integer")
    from collections import defaultdict

    timed = [c for c in candles if getattr(c, "timestamp", None) is not None]
    if not timed:
        return []
    day = timed[-1].timestamp.date()
    buckets = defaultdict(list)
    for candle in timed:
        stamp = candle.timestamp
        if not include_all_sessions and stamp.date() != day:
            continue
        minute_bucket = (stamp.hour * 60 + stamp.minute) // interval_minutes
        start_minute = minute_bucket * interval_minutes
        bucket_time = stamp.replace(
            hour=start_minute // 60, minute=start_minute % 60,
            second=0, microsecond=0,
        )
        buckets[bucket_time].append(candle)

    result = []
    for bucket_time in sorted(buckets):
        group = sorted(buckets[bucket_time], key=lambda c: c.timestamp)
        if len(group) != interval_minutes:
            continue
        if any(
            group[i].timestamp - group[i - 1].timestamp != timedelta(minutes=1)
            for i in range(1, len(group))
        ):
            continue
        result.append({
            "timestamp": bucket_time,
            "open": float(group[0].open),
            "high": max(float(c.high) for c in group),
            "low": min(float(c.low) for c in group),
            "close": float(group[-1].close),
            "volume": sum(float(c.volume) for c in group),
        })
    return result


def verified_same_slot_relative_volume(current_bar, historical_rows,
                                       reference_sessions=20):
    """Compare a completed intraday bar with the same time slot over prior sessions.

    Historical rows use Upstox candle arrays: timestamp, open, high, low,
    close, volume, optional open interest. A full 20-session baseline is
    required; partial history is unavailable, never guessed.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    if (not isinstance(reference_sessions, int) or isinstance(reference_sessions, bool)
            or reference_sessions < 1):
        raise ValueError("reference_sessions must be a positive integer")
    if not current_bar:
        return None
    stamp = current_bar.get("timestamp")
    if stamp is None:
        return None
    try:
        current_volume = float(current_bar["volume"])
        current_open = float(current_bar["open"])
        current_close = float(current_bar["close"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not all(isfinite(x) and x >= 0 for x in (current_volume, current_open, current_close)):
        return None

    ist = ZoneInfo("Asia/Kolkata")
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(ist).replace(tzinfo=None)
    slot = (stamp.hour, stamp.minute)
    if isinstance(historical_rows, CompactSameSlotVolumeHistory):
        packed = historical_rows.slots.get(slot, ())
        current_ordinal = stamp.date().toordinal()
        observations = [
            packed[index + 1]
            for index in range(0, len(packed), 2)
            if int(packed[index]) < current_ordinal
        ][-reference_sessions:]
        if len(observations) != reference_sessions:
            return None
        baseline = sum(observations) / reference_sessions
        if baseline <= 0:
            return None
        return {
            "relative_volume": current_volume / baseline,
            "current_volume": current_volume,
            "baseline_volume": baseline,
            "reference_sessions": reference_sessions,
            "slot": f"{slot[0]:02d}:{slot[1]:02d}",
            "candle_direction": ("BULLISH" if current_close > current_open
                                 else "BEARISH" if current_close < current_open
                                 else "FLAT"),
        }

    by_date = {}
    for row in historical_rows or ():
        try:
            history_stamp = row[0]
            if isinstance(history_stamp, str):
                history_stamp = datetime.fromisoformat(history_stamp.replace("Z", "+00:00"))
            if history_stamp.tzinfo is not None:
                history_stamp = history_stamp.astimezone(ist).replace(tzinfo=None)
            if history_stamp.date() >= stamp.date():
                continue
            if (history_stamp.hour, history_stamp.minute) != slot:
                continue
            volume = float(row[5])
            if not isfinite(volume) or volume < 0:
                continue
            by_date[history_stamp.date()] = volume
        except (IndexError, TypeError, ValueError, OverflowError):
            continue

    observations = [by_date[day] for day in sorted(by_date)[-reference_sessions:]]
    if len(observations) != reference_sessions:
        return None
    baseline = sum(observations) / reference_sessions
    if baseline <= 0:
        return None
    return {
        "relative_volume": current_volume / baseline,
        "current_volume": current_volume,
        "baseline_volume": baseline,
        "reference_sessions": reference_sessions,
        "slot": f"{slot[0]:02d}:{slot[1]:02d}",
        "candle_direction": ("BULLISH" if current_close > current_open
                             else "BEARISH" if current_close < current_open
                             else "FLAT"),
    }


def confirmed_range_breakout(bars, direction, *, prior_bars=3, min_buffer_pct=0.10):
    """Confirm the latest completed bar clears the prior range with a buffer."""
    if len(bars) < prior_bars + 1:
        return False
    window = list(bars[-(prior_bars + 1):])
    stamps = [bar.get("timestamp") for bar in window]
    if any(stamp is None for stamp in stamps):
        return False
    interval = timedelta(minutes=15)
    if any(stamps[i] - stamps[i - 1] != interval
           for i in range(1, len(stamps))):
        return False
    try:
        prior = window[:-1]
        high = max(float(bar["high"]) for bar in prior)
        low = min(float(bar["low"]) for bar in prior)
        latest_close = float(window[-1]["close"])
        ranges = [float(bar["high"]) - float(bar["low"]) for bar in prior]
        if latest_close <= 0 or not all(isfinite(x) and x >= 0 for x in [high, low, *ranges]):
            return False
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    buffer = max(latest_close * float(min_buffer_pct) / 100,
                 0.25 * (sum(ranges) / len(ranges)))
    if direction == "BUY":
        return latest_close > high + buffer
    if direction == "SELL":
        return latest_close < low - buffer
    return False
