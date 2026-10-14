"""CSV export for observed paper signal calls. No broker execution or orders."""
import csv
import io

COLUMNS = ("symbol", "kind", "buy_time_ist", "sell_time_ist",
           "buy_price", "sell_price", "difference", "return_pct")

def closed_calls_csv(report):
    """Return a UTF-8 CSV string; no fabricated rupee P&L."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for call in report["closed_calls"]:
        writer.writerow({key: call.get(key) for key in COLUMNS})
    return buffer.getvalue()
