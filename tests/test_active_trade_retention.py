"""Offline regression for active-trade retention beyond history pagination."""
import sqlite3
import unittest


class ActiveTradeRetentionTests(unittest.TestCase):
    def test_open_trade_is_not_truncated_by_closed_history(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY, status TEXT, symbol TEXT)")
        con.execute("INSERT INTO trades VALUES (1, 'OPEN', 'OLDEST_OPEN')")
        con.executemany("INSERT INTO trades VALUES (?, 'CLOSED', ?)",
                        [(i, f"CLOSED_{i}") for i in range(2, 153)])
        rows = con.execute(
            "SELECT * FROM trades WHERE status != 'CLOSED' "
            "UNION ALL SELECT * FROM (SELECT * FROM trades WHERE status = 'CLOSED' "
            "ORDER BY id DESC LIMIT 100) ORDER BY id DESC"
        ).fetchall()
        self.assertEqual(len(rows), 101)
        self.assertIn((1, "OPEN", "OLDEST_OPEN"), rows)
        self.assertNotIn((2, "CLOSED", "CLOSED_2"), rows)
        con.close()


if __name__ == "__main__":
    unittest.main()
