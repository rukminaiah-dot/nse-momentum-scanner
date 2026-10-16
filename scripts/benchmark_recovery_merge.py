"""Synthetic offline recovery merge latency; no scanner, broker or network.

Run: python -m scripts.benchmark_recovery_merge --history 390 --iterations 100
"""
import argparse
import platform
import statistics
import time
from datetime import datetime, timedelta
from v2.backend.candle_manager import CandleManager
from v2.backend.candles import Candle


def percentiles(samples):
    values = sorted(samples)
    return (statistics.median(values),
            values[int((len(values) - 1) * .95)],
            values[int((len(values) - 1) * .99)])


def benchmark(history=390, iterations=100):
    if isinstance(history, bool) or isinstance(iterations, bool) or history < 30 or iterations < 1:
        raise ValueError("history >= 30 and iterations >= 1 required")
    start = datetime(2026, 10, 16, 9, 15)
    # At most 50 missing minutes per batch, below the worker's 60 cap.
    all_minutes = [start + timedelta(minutes=i) for i in range(history)]
    missing = set(all_minutes[::max(10, (history + 49) // 50)])
    existing = []
    recovered = {}
    for minute in all_minutes:
        candle = Candle(100.0, 10)
        candle.timestamp = minute
        if minute in missing:
            recovered[minute] = candle
        else:
            existing.append(candle)
    active_minute = all_minutes[-1] + timedelta(minutes=1)
    active_ms = active_minute.replace(tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata")).timestamp() * 1000
    samples = []
    inserted = []
    for _ in range(iterations):
        manager = CandleManager()
        manager.preload_completed("TEST", existing)
        manager.update("TEST", 100.0, active_ms)
        before = time.perf_counter_ns()
        count = manager.merge_verified_recovery("TEST", recovered, active_minute)
        samples.append((time.perf_counter_ns() - before) / 1e6)
        inserted.append(count)
        merged, active = manager.snapshot("TEST")
        assert count == len(missing) and len(merged) == history and active == active_minute
        assert manager.merge_verified_recovery("TEST", recovered, active_minute) == 0
    p50, p95, p99 = percentiles(samples)
    assert all(n == len(missing) for n in inserted)
    print(f"python={platform.python_version()} platform={platform.platform()}")
    print(f"history={history} iterations={iterations} missing_per_merge={len(missing)}")
    print(f"recovery_merge_ms p50={p50:.4f} p95={p95:.4f} p99={p99:.4f}")
    print("Scope: single-threaded synthetic merge only; excludes API fetch, row verification, and competing workers.")
    return samples


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=int, default=390)
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()
    benchmark(args.history, args.iterations)
