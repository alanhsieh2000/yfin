from __future__ import annotations

import csv
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase

from yfinance_watchlist.cache import HistoryCache
from yfinance_watchlist.models import PriceHistoryRow


class HistoryCacheTestCase(TestCase):
    def test_cache_hit_skips_refetch_for_past_year(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HistoryCache(tmpdir)
            cache.write_year("AAPL", 2025, [self._row("2025-01-02T00:00:00+00:00", 0.0)])

            self.assertTrue(cache.has_year("AAPL", 2025))
            self.assertEqual(cache.latest_timestamp("AAPL", 2025), datetime(2025, 1, 2, tzinfo=timezone.utc))
            self.assertEqual(len(cache.read_year("AAPL", 2025)), 1)

    def test_current_year_refresh_merges_new_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HistoryCache(tmpdir)
            cache.write_year("AAPL", 2026, [self._row("2026-01-02T00:00:00+00:00", 0.0)])

            cache.merge_year(
                "AAPL",
                2026,
                [
                    self._row("2026-01-02T00:00:00+00:00", 0.0),
                    self._row("2026-01-03T00:00:00+00:00", 0.25, 2.0),
                ],
            )

            rows = cache.read_year("AAPL", 2026)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1].dividend, 0.25)
        self.assertEqual(rows[-1].stock_splits, 2.0)
        self.assertEqual(rows[-1].timestamp, datetime(2026, 1, 3, tzinfo=timezone.utc))

    def test_current_year_cache_is_noop_when_latest_timestamp_is_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HistoryCache(tmpdir)
            row = self._row("2026-04-24T00:00:00+00:00", 0.0)
            cache.write_year("AAPL", 2026, [row])

            latest = cache.latest_timestamp("AAPL", 2026)
            rows = cache.read_year("AAPL", 2026)

        self.assertEqual(latest, datetime(2026, 4, 24, tzinfo=timezone.utc))
        self.assertEqual(rows, [row])

    def test_latest_adjustment_timestamp_tracks_latest_dividend_or_split_for_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HistoryCache(tmpdir)
            cache.write_year("AAPL", 2025, [self._row("2025-01-02T00:00:00+00:00", 0.25)])
            cache.write_year("AAPL", 2026, [self._row("2026-01-03T00:00:00+00:00", 0.0, 2.0)])

            latest_adjustment = cache.latest_adjustment_timestamp("AAPL")
            years = cache.years_for_symbol("AAPL")

        self.assertEqual(latest_adjustment, datetime(2026, 1, 3, tzinfo=timezone.utc))
        self.assertEqual(years, [2025, 2026])

    def test_write_year_stores_history_values_rounded_to_two_decimals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = HistoryCache(tmpdir)
            row = PriceHistoryRow(
                timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
                open=47.06,
                high=47.06,
                low=46.48,
                close=46.49,
                volume=1000,
                dividend=0.12,
                stock_splits=4.0,
            )

            cache.write_year("AAPL", 2026, [row])

            with open(Path(tmpdir) / "cache" / "history" / "AAPL" / "2026.csv", newline="", encoding="utf-8") as handle:
                stored = next(csv.DictReader(handle))

        self.assertEqual(stored["open"], "47.06")
        self.assertEqual(stored["high"], "47.06")
        self.assertEqual(stored["low"], "46.48")
        self.assertEqual(stored["close"], "46.49")
        self.assertEqual(stored["dividend"], "0.12")
        self.assertEqual(stored["stock_splits"], "4.0")

    @staticmethod
    def _row(timestamp: str, dividend: float, stock_splits: float = 0.0) -> PriceHistoryRow:
        value = datetime.fromisoformat(timestamp)
        return PriceHistoryRow(
            timestamp=value,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000,
            dividend=dividend,
            stock_splits=stock_splits,
        )
