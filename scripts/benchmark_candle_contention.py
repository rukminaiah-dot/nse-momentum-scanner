"""Synthetic offline multi-thread contention for one CandleManager lock.

This measures end-to-end operation latency (including lock wait), not lock
hold time, websocket throughput, broker fetch, or recovery verification.
"""
import argparse
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from zoneinfo import ZoneInfo

from v2.backend.candle_manager import CandleManager
from v2.backend.candles import Candle


def summary(samples):
    values = sorted(samples)
    return (statistics.median(values), values[int((len(values)-1)*.95)],
            values[int((len(values)-1)*.99)])


def benchmark(symbols=50, history=390, workers=4, iterations=100):
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 1
           for n in (symbols, history, workers, iterations)):
        raise ValueError("all arguments must be positive integers")
    start = datetime(2026, 10, 16, 9, 15)
    manager = CandleManager()
    for symbol in range(symbols):
        bars = []
        for minute in range(history):
            item = Candle(100 + minute % 7, 10)
            item.timestamp = start + timedelta(minutes=minute)
            bars.append(item)
        manager.preload_completed(f"SYM{symbol}", bars)
    active = start + timedelta(minutes=history)
    active_ms = active.replace(tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000
    # All worker operations use a single active minute, so updates cannot
    # emit closed candles or trigger trading. Recovery candidates are empty.
    manager.update("SYM0", 100, active_ms)
    barrier = Barrier(workers)
    def task(worker):
        samples = {"snapshot": [], "update": [], "merge": []}
        barrier.wait(timeout=15)
        for iteration in range(iterations):
            kind = ("snapshot", "update", "merge")[(iteration + worker) % 3]
            before = time.perf_counter_ns()
            if kind == "snapshot":
                bars, _ = manager.snapshot(f"SYM{(worker + iteration) % symbols}")
                assert len(bars) == history
            elif kind == "update":
                manager.update("SYM0", 100 + worker % 3, active_ms)
            else:
                assert manager.merge_verified_recovery("SYM0", {}, active) == 0
            samples[kind].append((time.perf_counter_ns() - before) / 1e6)
        return samples
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outputs = list(pool.map(task, range(workers)))
    print(f"symbols={symbols} history={history} workers={workers} iterations_per_worker={iterations}")
    for kind in ("snapshot", "update", "merge"):
        samples = [sample for result in outputs for sample in result[kind]]
        p50, p95, p99 = summary(samples)
        print(f"{kind}_end_to_end_ms count={len(samples)} p50={p50:.4f} p95={p95:.4f} p99={p99:.4f}")
    print("Scope: synthetic multi-thread contention, no actual missing-candle merge or network.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=int, default=50)
    parser.add_argument("--history", type=int, default=390)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()
    benchmark(args.symbols, args.history, args.workers, args.iterations)
