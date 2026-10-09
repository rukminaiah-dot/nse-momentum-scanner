from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
WATCH_START = time(14, 0)
WATCH_END = time(15, 20)

# Scheduled weekly expiries; exchange holidays may shift these dates.
EXPIRY_WEEKDAYS = {
    "NIFTY 50": 1,  # Tuesday
    "SENSEX": 3,    # Thursday
}


def expiry_watch_status(index_name, now=None):
    now = now or datetime.now(IST)

    if index_name not in EXPIRY_WEEKDAYS:
        return "UNSUPPORTED"

    if now.weekday() != EXPIRY_WEEKDAYS[index_name]:
        return "NOT_EXPIRY_DAY"

    if not WATCH_START <= now.time() <= WATCH_END:
        return "OUTSIDE_WINDOW"

    return "WATCH"


if __name__ == "__main__":
    for index in EXPIRY_WEEKDAYS:
        print(index, expiry_watch_status(index))
