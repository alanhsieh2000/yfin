from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from yfinance_watchlist.watchlist import WatchlistReader


class WatchlistReaderTestCase(TestCase):
    def test_load_watchlist_skips_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"
            path.write_text("symbol,label\nAAPL,Apple\nAAPL,Duplicate\nSPY,ETF\n", encoding="utf-8")

            entries = WatchlistReader().load(str(path))

        self.assertEqual([entry.symbol for entry in entries], ["AAPL", "SPY"])
        self.assertEqual(entries[0].label, "Apple")

    def test_load_watchlist_requires_symbol_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"
            path.write_text("ticker,label\nAAPL,Apple\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required symbol header"):
                WatchlistReader().load(str(path))

