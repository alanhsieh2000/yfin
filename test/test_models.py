from datetime import datetime, timezone
from unittest import TestCase

from yfinance_watchlist.models import PriceHistoryRow, QuoteSnapshot, WatchlistEntry


class ModelsTestCase(TestCase):
    def test_dataclasses_hold_expected_fields(self) -> None:
        entry = WatchlistEntry(symbol="AAPL", label="Apple")
        quote = QuoteSnapshot(
            symbol="AAPL",
            currency="USD",
            market_price=123.45,
            market_time=datetime(2026, 4, 24, tzinfo=timezone.utc),
        )
        row = PriceHistoryRow(
            timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
            open=100.0,
            high=101.0,
            low=99.5,
            close=100.5,
            volume=1000,
            dividend=0.25,
            stock_splits=2.0,
        )

        self.assertEqual(entry.symbol, "AAPL")
        self.assertEqual(quote.currency, "USD")
        self.assertEqual(row.dividend, 0.25)
        self.assertEqual(row.stock_splits, 2.0)
