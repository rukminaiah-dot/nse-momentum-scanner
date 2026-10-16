"""Offline snapshot-copy benchmark. No broker, network, or production dependencies.

Usage: python scripts/benchmark_candle_snapshots.py --symbols 50 --history 390 --iterations 200
"""
import argparse
import statistics
import time
from datetime import datetime, timedelta
from v2.backend.candle_manager import CandleManager
from v2.backend.candles import Candle


def benchmark(symbols, history, iterations):
    manager = CandleManager()
    start = datetime(2026, 10, 16, 9, 15)
    for index in range(symbols):
        candles = []
        for minute in range(history):
            candle = Candle(100.0 + minute % 10, 0)
            candle.timestamp = start + timedelta(minutes=minute)
            candles.append(candle)
        manager.preload_completed(f"SYM{index}", candles)
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
    print("Scope: sequential snapshot latency only; no concurrent tick or RSS measurement.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=int, default=50)
    parser.add_argument("--history", type=int, default=390)
    parser.add_argument("--iterations", type=int, default=200)
    args = parser.parse_args()
    if min(args.symbols, args.history, args.iterations) < 1:
        parser.error("all values must be positive")
    benchmark(args.symbols, args.history, args.iterations)
