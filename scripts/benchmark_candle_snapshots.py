"""Offline snapshot-copy benchmark. No broker, network, or production dependencies.

Usage: python -m scripts.benchmark_candle_snapshots --symbols 50 --history 390 --iterations 200
"""
import argparse
import resource
import sys
import statistics
import time
from datetime import datetime, timedelta
from threading import Event, Thread
from v2.backend.candle_manager import CandleManager
from v2.backend.candles import Candle


def benchmark(symbols, history, iterations):
    baseline_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    manager = CandleManager()
    start = datetime(2026, 10, 16, 9, 15)
    for index in range(symbols):
        candles = []
        for minute in range(history):
            candle = Candle(100.0 + minute % 10, 0)
            candle.timestamp = start + timedelta(minutes=minute)
            candles.append(candle)
        manager.preload_completed(f"SYM{index}", candles)
    populated_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    samples_ms = []
    start_ns = time.perf_counter_ns()
    for iteration in range(iterations):
        key = f"SYM{iteration % symbols}"
        before = time.perf_counter_ns()
        completed, active = manager.snapshot(key)
        samples_ms.append((time.perf_counter_ns() - before) / 1e6)
        assert len(completed) == history and active is None
    elapsed_s = (time.perf_counter_ns() - start_ns) / 1e9
    samples_ms.sort()
    percentile = lambda p: samples_ms[min(len(samples_ms) - 1, int((len(samples_ms) - 1) * p))]
    print(f"symbols={symbols} history={history} iterations={iterations} elapsed_s={elapsed_s:.3f}")
    print(f"snapshot_ms p50={statistics.median(samples_ms):.4f} p95={percentile(.95):.4f} p99={percentile(.99):.4f}")
    # Linux reports ru_maxrss in KiB; macOS reports bytes. This is a process
    # high-water mark, not retained heap size or per-symbol allocation.
    rss_unit = 1024 if sys.platform == "darwin" else 1
    print(f"peak_rss_mib={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / rss_unit / 1024:.2f} "
          f"baseline_rss_mib={baseline_rss_kb / rss_unit / 1024:.2f} "
          f"after_preload_peak_rss_mib={populated_rss_kb / rss_unit / 1024:.2f}")
    print("Scope: sequential snapshot latency; process peak RSS is a high-water mark, not retained heap.")
    # A separate updater thread contends for the same manager lock. Measure
    # end-to-end update latency, including time waiting for snapshots.
    ready = Event()
    tick_ms = []
    tick_key = "SYM0"
    tick_time = datetime(2026, 10, 16, 10, 0).timestamp() * 1000
    def updates():
        ready.wait()
        for i in range(iterations):
            before = time.perf_counter_ns()
            manager.update(tick_key, 100.0 + i % 10, tick_time)
            tick_ms.append((time.perf_counter_ns() - before) / 1e6)
    thread = Thread(target=updates)
    thread.start()
    ready.set()
    for i in range(iterations):
        manager.snapshot(f"SYM{i % symbols}")
    thread.join()
    tick_ms.sort()
    print(f"concurrent_update_ms p50={statistics.median(tick_ms):.4f} "
          f"p95={tick_ms[int((len(tick_ms)-1)*.95)]:.4f} "
          f"p99={tick_ms[int((len(tick_ms)-1)*.99)]:.4f}")
    print("Scope: synthetic two-thread contention; not live websocket throughput.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=int, default=50)
    parser.add_argument("--history", type=int, default=390)
    parser.add_argument("--iterations", type=int, default=200)
    args = parser.parse_args()
    if min(args.symbols, args.history, args.iterations) < 1:
        parser.error("all values must be positive")
    benchmark(args.symbols, args.history, args.iterations)
