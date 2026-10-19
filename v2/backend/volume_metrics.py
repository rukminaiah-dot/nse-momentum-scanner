"""Verified relative volume from real completed one-minute candles."""

from datetime import timedelta
from math import isfinite


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
