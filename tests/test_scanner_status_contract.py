"""Offline contract checks for the scanner-status API; no live services or orders."""
import ast
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException


def _status_handler():
    source = Path(__file__).resolve().parents[1] / "v2/backend/api.py"
    module = ast.parse(source.read_text(encoding="utf-8"))
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef)
                    and node.name == "get_scanner_status")
    function.decorator_list = []  # Route registration is tested by the real API; isolate handler logic here.
    isolated = ast.Module(body=[function], type_ignores=[])
    namespace = {"sqlite3": sqlite3, "DB_PATH": ":memory:"}
    exec(compile(isolated, str(source), "exec"), namespace)
    return namespace["get_scanner_status"]


def test_scanner_status_empty_and_populated(tmp_path):
    database = tmp_path / "scanner.sqlite"
    with sqlite3.connect(database) as con:
        con.execute("CREATE TABLE scanner_results (updated_at TEXT)")
    handler = _status_handler()
    with patch.dict(handler.__globals__, DB_PATH=str(database)):
        empty = handler()
        assert empty["status"] == "NO_STORED_RESULTS"
        assert empty["result_count"] == 0
        assert empty["latest_result_updated_at"] is None
        with sqlite3.connect(database) as con:
            con.executemany("INSERT INTO scanner_results VALUES (?)",
                            [("2026-10-15T10:00:00",), ("2026-10-16T10:00:00",)])
        populated = handler()
    assert populated["status"] == "STORED_RESULTS_AVAILABLE"
    assert populated["result_count"] == 2
    assert populated["latest_result_updated_at"] == "2026-10-16T10:00:00"
    assert populated["live_feed_verified"] is False
    assert populated["signal_freshness_verified"] is False
    assert populated["order_execution_enabled"] is False


def test_scanner_status_missing_storage_fails_closed(tmp_path):
    handler = _status_handler()
    with patch.dict(handler.__globals__, DB_PATH=str(tmp_path / "missing.sqlite")):
        with pytest.raises(HTTPException) as error:
            handler()
    assert error.value.status_code == 503
    assert error.value.detail == "Scanner result storage unavailable"
