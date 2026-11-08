#!/usr/bin/env python3
"""Check data preservation on a disposable, rootable Android CI emulator."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from verify_signed_apk import PACKAGE


DATABASE = f"/data/user/0/{PACKAGE}/databases/paper_candles.db"
PREFERENCES = f"/data/user/0/{PACKAGE}/shared_prefs"
BUY_TIME = "2025-01-02T03:47:00Z"
SELL_TIME = "2025-01-02T04:15:00Z"
DASHBOARD_TRADES = [
    ("RELIANCE", BUY_TIME, 1, 1200.0),
    ("RELIANCE", SELL_TIME, -1, 1230.0),
]
OPENING_HISTORY = {
    "NSE_EQ|INE002A01018": {
        "day": "2025-01-02", "boughtToday": True, "quantity": 7,
        "trades": [[BUY_TIME, 1200.0, SELL_TIME, 1230.0, 7, "fixture"]],
    },
}
REVERSAL_HISTORY = {
    "NSE_EQ|INE002A01018": {
        "symbol": "RELIANCE", "quantity": 7,
        "trades": [[BUY_TIME, 1200.0, SELL_TIME, 1230.0, "fixture", "LEGACY_80", None, None, 7, False]],
    },
}


def adb(*args):
    return subprocess.check_output(["adb", *map(str, args)], text=True, timeout=30).strip()


def launch():
    result = adb("shell", "am", "start", "-W", "-n", f"{PACKAGE}/com.nsemomentum.paper.MainActivity")
    if "Status: ok" not in result:
        raise RuntimeError(f"Scanner launch failed: {result}")


def installed_version():
    details = adb("shell", "dumpsys", "package", PACKAGE)
    name = re.search(r"^\s*versionName=(\S+)", details, re.MULTILINE)
    code = re.search(r"^\s*versionCode=(\d+)", details, re.MULTILINE)
    if not name or not code:
        raise RuntimeError("Could not read installed scanner version")
    return name[1], int(code[1])


def wait_for_schema(local, version):
    for _ in range(30):
        try:
            adb("pull", DATABASE, local)
            with closing(sqlite3.connect(f"{local.as_uri()}?mode=ro", uri=True)) as db:
                if db.execute("PRAGMA user_version").fetchone() == (version,):
                    return
        except (subprocess.CalledProcessError, sqlite3.Error):
            pass
        time.sleep(1)
    raise RuntimeError(f"Scanner did not open a database at schema version {version}")


def verify_upgrade(previous, candidate, report, temp):
    adb("root")
    adb("wait-for-device")
    if adb("shell", "id", "-u") != "0":
        raise RuntimeError("The upgrade fixture requires a rootable CI emulator")

    adb("install", previous)
    if installed_version() != ("0.26.0-candidate", 31):
        raise RuntimeError("Expected signed v0.26.0 as the upgrade baseline")
    launch()
    local_db = temp / "paper_candles.db"
    wait_for_schema(local_db, 4)
    adb("shell", "am", "force-stop", PACKAGE)
    adb("pull", DATABASE, local_db)
    with closing(sqlite3.connect(local_db)) as db, db:
        db.executemany(
            "INSERT INTO paper_signal_events (symbol, signal_time, direction, price) VALUES (?, ?, ?, ?)",
            DASHBOARD_TRADES,
        )
    owner = adb("shell", "stat", "-c", "%u:%g", DATABASE)
    adb("push", local_db, "/data/local/tmp/scanner-upgrade.db")
    adb("shell", "cp", "/data/local/tmp/scanner-upgrade.db", DATABASE)

    adb("shell", "mkdir", "-p", PREFERENCES)
    adb("shell", "chown", owner, PREFERENCES)
    adb("shell", "chmod", "771", PREFERENCES)
    settings = {
        "paper_preferences": '<set name="favourites"><string>RELIANCE</string></set>',
        "opening_notification_settings": '<int name="quantity" value="7" />',
        "opening_momentum_paper_v1": f'<string name="state">{escape(json.dumps(OPENING_HISTORY))}</string>',
        "reversal_strategy_v1": f'<string name="state">{escape(json.dumps(REVERSAL_HISTORY))}</string>',
    }
    for name, content in settings.items():
        local = temp / f"{name}.xml"
        local.write_text(f'<?xml version="1.0" encoding="utf-8"?>\n<map>{content}</map>\n')
        adb("push", local, "/data/local/tmp/scanner-upgrade.xml")
        dest = f"{PREFERENCES}/{local.name}"
        adb("shell", "cp", "/data/local/tmp/scanner-upgrade.xml", dest)
        adb("shell", "chown", owner, dest)
        adb("shell", "chmod", "660", dest)
    adb("shell", "restorecon", "-R", PREFERENCES)

    adb("install", "-r", candidate)
    if installed_version() != (report["versionName"], report["versionCode"]):
        raise RuntimeError("Installed version differs from the verified signed candidate")
    launch()
    wait_for_schema(local_db, 5)
    adb("shell", "am", "force-stop", PACKAGE)
    adb("pull", DATABASE, local_db)
    with closing(sqlite3.connect(f"{local_db.as_uri()}?mode=ro", uri=True)) as db:
        rows = db.execute(
            "SELECT symbol, signal_time, direction, price, profit_review FROM paper_signal_events ORDER BY signal_time"
        ).fetchall()
    if rows != [(*trade, 0) for trade in DASHBOARD_TRADES]:
        raise RuntimeError("Dashboard trade history did not survive the SQLite migration")
    for name, expected in settings.items():
        prefs = ET.fromstring(adb("shell", "cat", f"{PREFERENCES}/{name}.xml"))
        setting = ET.fromstring(expected)
        actual = prefs.find(f"{setting.tag}[@name='{setting.get('name')}']")
        if actual is None or ET.tostring(actual).strip() != ET.tostring(setting).strip():
            raise RuntimeError(f"Upgrade did not preserve {name}")
    print("Signed v0.26.0 upgrade preserved Dashboard, Opening and Reversal paper history, favourites and paper quantity.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    if not any(adb("shell", "getprop", name) == "1" for name in ("ro.kernel.qemu", "ro.boot.qemu")):
        raise RuntimeError("Run this fixture only on a disposable CI emulator")
    report = json.loads(args.report.read_text())
    with tempfile.TemporaryDirectory() as directory:
        verify_upgrade(args.previous, args.candidate, report, Path(directory))
    report.update(deviceUpdateVerified=True, deviceUpdateDataPreserved=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
