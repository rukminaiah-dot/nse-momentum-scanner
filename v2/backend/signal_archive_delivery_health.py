"""Read-only snapshot of archive delivery health.

Never mistake a zero pending queue for a complete historical archive.
"""
from .signal_archive_dispatch import archive_queue_status

def archive_delivery_health():
    state = archive_queue_status()
    failures = state.get("failed", 0)
    drops = state.get("dropped", 0)
    return {
        "status": "REPLAY_REQUIRED" if failures or drops else (
            "NOT_STARTED" if not state["started"] else (
                "PENDING" if state.get("pending", 0) else "NO_KNOWN_DELIVERY_FAILURES"
            )
        ),
        "queue": state,
        "historical_completeness_verified": False,
        "note": "Queue counters are process-local; verify PostgreSQL against available SQLite before trusting reports.",
    }
