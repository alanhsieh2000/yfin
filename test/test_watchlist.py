from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from unittest import TestCase

from yfinance_watchlist.watchlist import WatchlistReader, WatchlistStore


class WatchlistReaderTestCase(TestCase):
    def test_load_watchlist_skips_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"
            path.write_text("symbol,label\nAAPL,Apple\nAAPL,Duplicate\nSPY,ETF\n", encoding="utf-8")

            entries = WatchlistReader().load(str(path))

        self.assertEqual([entry.symbol for entry in entries], ["AAPL", "SPY"])
        self.assertEqual(entries[0].label, "Apple")

    def test_load_watchlist_skips_duplicates_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"
            path.write_text("symbol,label\naapl,Apple\nAAPL,Duplicate\n", encoding="utf-8")

            entries = WatchlistReader().load(str(path))

        self.assertEqual([entry.symbol for entry in entries], ["AAPL"])
        self.assertEqual(entries[0].label, "Apple")

    def test_load_watchlist_requires_symbol_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"
            path.write_text("ticker,label\nAAPL,Apple\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required symbol header"):
                WatchlistReader().load(str(path))


class WatchlistStoreTestCase(TestCase):
    def test_load_entries_returns_empty_list_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"

            entries = WatchlistStore().load_entries(str(path))

        self.assertEqual(entries, [])

    def test_add_entry_creates_watchlist_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"

            entry = WatchlistStore().add_entry(str(path), "aapl", "Apple")
            with open(path, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(entry.symbol, "AAPL")
        self.assertEqual(entry.label, "Apple")
        self.assertEqual(rows, [{"symbol": "AAPL", "label": "Apple"}])

    def test_add_entry_allows_missing_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"

            entry = WatchlistStore().add_entry(str(path), "spy")
            with open(path, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(entry.symbol, "SPY")
        self.assertIsNone(entry.label)
        self.assertEqual(rows, [{"symbol": "SPY", "label": ""}])

    def test_add_entry_normalizes_trailing_comma_in_symbol_and_label_separator(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"

            entry = WatchlistStore().add_entry(str(path), "aapl,", ", Apple Inc.")
            with open(path, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(entry.symbol, "AAPL")
        self.assertEqual(entry.label, "Apple Inc.")
        self.assertEqual(rows, [{"symbol": "AAPL", "label": "Apple Inc."}])

    def test_load_entries_normalizes_trailing_comma_in_existing_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"
            path.write_text('symbol,label\n"AAPL,",Apple\nAAPL,Duplicate\n', encoding="utf-8")

            entries = WatchlistStore().load_entries(str(path))

        self.assertEqual([entry.symbol for entry in entries], ["AAPL"])
        self.assertEqual(entries[0].label, "Apple")

    def test_add_entry_raises_for_existing_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"
            path.write_text("symbol,label\nAAPL,Apple\nSPY,ETF\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "symbol AAPL is already in the watchlist with label Apple"):
                WatchlistStore().add_entry(str(path), "AAPL", "Apple Inc")
            entries = WatchlistStore().load_entries(str(path))

        self.assertEqual(entries[0].label, "Apple")
        self.assertEqual([item.symbol for item in entries], ["AAPL", "SPY"])

    def test_add_entry_raises_for_existing_symbol_with_different_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"
            path.write_text("symbol,label\naapl,Apple\nSPY,ETF\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "symbol AAPL is already in the watchlist with label Apple"):
                WatchlistStore().add_entry(str(path), "AAPL", "Apple Inc")
            with open(path, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(
            rows,
            [
                {"symbol": "aapl", "label": "Apple"},
                {"symbol": "SPY", "label": "ETF"},
            ],
        )

    def test_remove_entry_deletes_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"
            path.write_text("symbol,label\nAAPL,Apple\nSPY,ETF\n", encoding="utf-8")

            removed = WatchlistStore().remove_entry(str(path), "spy")
            entries = WatchlistStore().load_entries(str(path))

        self.assertEqual(removed.symbol, "SPY")
        self.assertEqual([item.symbol for item in entries], ["AAPL"])

    def test_remove_entry_deletes_symbol_without_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"
            path.write_text("symbol,label\nAAPL,Apple\nSPY,\n", encoding="utf-8")

            removed = WatchlistStore().remove_entry(str(path), "spy")
            entries = WatchlistStore().load_entries(str(path))

        self.assertEqual(removed.symbol, "SPY")
        self.assertIsNone(removed.label)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].symbol, "AAPL")
        self.assertEqual(entries[0].label, "Apple")

    def test_remove_entry_raises_for_missing_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "watchlist.csv"
            path.write_text("symbol,label\nAAPL,Apple\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "symbol SPY is not in the watchlist"):
                WatchlistStore().remove_entry(str(path), "SPY")
