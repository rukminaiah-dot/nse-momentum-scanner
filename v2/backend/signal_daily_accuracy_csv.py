"""Daily BUY-to-SELL paper accuracy CSV, not broker execution P&L."""
import csv
import io

FIELDS = (
    "sell_date_ist", "stock_closed", "stock_wins", "stock_losses", "stock_flat",
    "stock_win_rate_pct", "index_closed", "index_wins", "index_losses",
    "index_flat", "index_win_rate_pct", "stock_price_difference_sum",
    "index_points_sum", "archive_reconciliation_status",
)
COUNTS = ("stock_closed", "stock_wins", "stock_losses", "stock_flat",
          "index_closed", "index_wins", "index_losses", "index_flat")
AMOUNTS = ("stock_price_difference_sum", "index_points_sum")

def _rate(wins, closed):
    return round(100 * wins / closed, 2) if closed else ""

def daily_accuracy_csv(report):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    totals = {name: 0 for name in COUNTS + AMOUNTS}
    for day, row in sorted(report.get("daily_by_sell_date", {}).items()):
        item = {
            "sell_date_ist": day,
            **{name: row.get(name, 0) for name in COUNTS},
            "stock_price_difference_sum": row.get("stock_points", 0),
            "index_points_sum": row.get("index_points", 0),
        }
        for name in COUNTS + AMOUNTS:
            totals[name] += item[name]
        item["stock_win_rate_pct"] = _rate(item["stock_wins"], item["stock_closed"])
        item["index_win_rate_pct"] = _rate(item["index_wins"], item["index_closed"])
        item["archive_reconciliation_status"] = report.get("archive_reconciliation_status", "NOT_VERIFIED_FOR_THIS_REQUEST")
        writer.writerow(item)
    writer.writerow({
        "sell_date_ist": "TOTAL", **totals,
        "archive_reconciliation_status": report.get("archive_reconciliation_status", "NOT_VERIFIED_FOR_THIS_REQUEST"),
        "stock_win_rate_pct": _rate(totals["stock_wins"], totals["stock_closed"]),
        "index_win_rate_pct": _rate(totals["index_wins"], totals["index_closed"]),
    })
    return output.getvalue()
