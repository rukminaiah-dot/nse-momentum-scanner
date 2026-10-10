"""NSE official CM-UDiFF bhavcopy reader. No unofficial quote providers.

Public NSE archive downloads can be restricted; failures are surfaced, never replaced
with invented candles. Persist downloaded sessions on durable storage for 70+ sessions.
"""
import csv
import io
import urllib.request
import zipfile
from datetime import date, timedelta

ARCHIVE = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{day}_F_0000.csv.zip"

def download_session(day, timeout=12):
    url = ARCHIVE.format(day=day.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0",
        "Accept":"application/zip,*/*", "Referer":"https://www.nseindia.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        blob = response.read(5_000_001)
    if len(blob) > 5_000_000:
        raise ValueError("NSE_ARCHIVE_TOO_LARGE")
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [name for name in z.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError("UNEXPECTED_NSE_ARCHIVE")
        with z.open(names[0]) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
            required = {"TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol"}
            if not required.issubset(set(reader.fieldnames or [])):
                raise ValueError("UNEXPECTED_NSE_CSV_COLUMNS")
            output = {}
            for row in reader:
                if row["SctySrs"] != "EQ":
                    continue
                symbol = row["TckrSymb"].strip()
                output[symbol] = {"date":day.isoformat(),
                    "open":float(row["OpnPric"]), "high":float(row["HghPric"]),
                    "low":float(row["LwPric"]), "close":float(row["ClsPric"]),
                    "volume":float(row["TtlTradgVol"])}
            if not output:
                raise ValueError("EMPTY_NSE_EQUITY_REPORT")
            return output

def probe_latest(reference=None, days_back=7):
    reference = reference or date.today()
    attempts = []
    for n in range(days_back):
        day = reference - timedelta(days=n)
        if day.weekday() >= 5:
            continue
        try:
            stocks = download_session(day)
            return {"status":"ACCESSIBLE", "session":day.isoformat(),
                    "equity_symbols":len(stocks), "sample_BEL":stocks.get("BEL"),
                    "source":"NSE CM-UDiFF official daily bhavcopy"}
        except Exception as exc:
            attempts.append({"date":day.isoformat(), "error":type(exc).__name__,
                             "http_status":getattr(exc, "code", None)})
    return {"status":"UNAVAILABLE", "reason":"NO_VERIFIED_NSE_SESSION",
            "attempts":attempts, "source":"NSE CM-UDiFF official daily bhavcopy"}
