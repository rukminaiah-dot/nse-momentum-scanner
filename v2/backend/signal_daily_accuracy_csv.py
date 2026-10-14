"""CSV sheet for cumulative daily BUY-to-SELL paper signal accuracy.

Index point totals and stock price differences are not rupee P&L.
"""
import csv
import io

FIELDS = (
    "sell_date_ist", "stock_closed", "stock_wins", "stock_losses", "stock_flat",
    "index_closed", "index_wins", "index_losses", "index_flat",
    "stock_price_difference_sum", "index_points_sum",
)
COUNTS = FIELDS[1:9]
AMOUNTS = FIELDS[9:]

def daily_accuracy_csv(report):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    totals = {name: 0 for name in FIELDS[1:]}
    for day, row in sorted(report.get("daily_by_sell_date", {}).items()):
        item = {
            "sell_date_ist": day,
            **{name: row.get(name, 0) for name in COUNTS},
            "stock_price_difference_sum": row.get("stock_points", 0),
            "index_points_sum": row.get("index_points", 0),
        }
        writer.writerow(item)
        for name in COUNTS:
            totals[name] += item[name]
        for name in AMOUNTS:
            totals[name] += item[name]
    writer.writerow({"sell_date_ist": "TOTAL", **totals})
    return output.getvalue()
