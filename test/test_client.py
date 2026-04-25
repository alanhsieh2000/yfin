from __future__ import annotations

from datetime import date, datetime, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch

import pandas as pd

from yfinance_watchlist.client import YahooFinanceClient


class YahooFinanceClientTestCase(TestCase):
    @patch("yfinance_watchlist.client.yf.Ticker")
    def test_fetch_quote_maps_required_fields(self, ticker_cls: MagicMock) -> None:
        ticker = ticker_cls.return_value
        ticker.info = {
            "currency": "USD",
            "regularMarketPrice": 123.45,
            "regularMarketTime": 1776988800,
        }

        quote = YahooFinanceClient().fetch_quote("AAPL")

        self.assertEqual(quote.symbol, "AAPL")
        self.assertEqual(quote.currency, "USD")
        self.assertEqual(quote.market_price, 123.45)
        self.assertEqual(quote.market_time, datetime.fromtimestamp(1776988800, tz=timezone.utc))

    @patch("yfinance_watchlist.client.yf.Ticker")
    def test_fetch_quote_falls_back_to_fast_info_and_history_metadata(
        self, ticker_cls: MagicMock
    ) -> None:
        ticker = ticker_cls.return_value
        ticker.info = {}
        ticker.fast_info.items.return_value = {
            "currency": "USD",
            "lastPrice": 234.56,
        }.items()
        ticker.get_history_metadata.return_value = {
            "currentTradingPeriod": {"regular": {"start": 1776988800}},
        }

        quote = YahooFinanceClient().fetch_quote("AAPL")

        self.assertEqual(quote.symbol, "AAPL")
        self.assertEqual(quote.currency, "USD")
        self.assertEqual(quote.market_price, 234.56)
        self.assertEqual(quote.market_time, datetime.fromtimestamp(1776988800, tz=timezone.utc))

    @patch("yfinance_watchlist.client.yf.Ticker")
    def test_fetch_quote_rejects_empty_quote_payload(self, ticker_cls: MagicMock) -> None:
        ticker = ticker_cls.return_value
        ticker.info = {}
        ticker.fast_info.items.return_value = {}.items()
        ticker.get_history_metadata.return_value = {}
        ticker.history.return_value = pd.DataFrame()

        with self.assertRaisesRegex(ValueError, "quote data for APPL is unavailable"):
            YahooFinanceClient().fetch_quote("APPL")

    @patch("yfinance_watchlist.client.yf.Ticker")
    def test_fetch_history_uses_year_windows_for_past_years(self, ticker_cls: MagicMock) -> None:
        ticker = ticker_cls.return_value
        ticker.history.return_value = self._history_frame()
        client = YahooFinanceClient()

        rows = client.fetch_history("AAPL", 2024, 2025)

        self.assertEqual(len(rows), 4)
        calls = ticker.history.call_args_list
        self.assertEqual(calls[0].kwargs["start"], "2024-01-01")
        self.assertEqual(calls[0].kwargs["end"], "2025-01-01")
        self.assertEqual(calls[0].kwargs["interval"], "1d")
        self.assertEqual(calls[1].kwargs["start"], "2025-01-01")
        self.assertEqual(calls[1].kwargs["end"], "2026-01-01")

    @patch("yfinance_watchlist.client.yf.Ticker")
    def test_fetch_history_uses_current_year_through_today(self, ticker_cls: MagicMock) -> None:
        ticker = ticker_cls.return_value
        ticker.history.return_value = self._history_frame()
        client = YahooFinanceClient()

        with patch.object(client, "_today", return_value=date(2026, 4, 24)):
            client.fetch_history("AAPL", 2026, 2026)

        call = ticker.history.call_args
        self.assertEqual(call.kwargs["start"], "2026-01-01")
        self.assertEqual(call.kwargs["end"], "2026-04-25")

    @patch("yfinance_watchlist.client.yf.Ticker")
    def test_fetch_history_maps_dividends(self, ticker_cls: MagicMock) -> None:
        ticker = ticker_cls.return_value
        ticker.history.return_value = self._history_frame()

        rows = YahooFinanceClient().fetch_history("AAPL", 2025, 2025)

        self.assertEqual(rows[0].dividend, 0.0)
        self.assertEqual(rows[1].dividend, 0.25)
        self.assertEqual(rows[0].timestamp, datetime(2025, 1, 2, tzinfo=timezone.utc))

    @patch("yfinance_watchlist.client.yf.Ticker")
    def test_fetch_history_rounds_float_fields_to_two_decimals(self, ticker_cls: MagicMock) -> None:
        ticker = ticker_cls.return_value
        ticker.history.return_value = pd.DataFrame(
            {
                "Open": [47.060001373291016],
                "High": [47.064999999999998],
                "Low": [46.47999954223633],
                "Close": [46.48500000000001],
                "Volume": [1000],
                "Dividends": [0.125],
            },
            index=pd.to_datetime(["2025-01-02"]),
        )

        rows = YahooFinanceClient().fetch_history("AAPL", 2025, 2025)

        self.assertEqual(rows[0].open, 47.06)
        self.assertEqual(rows[0].high, 47.06)
        self.assertEqual(rows[0].low, 46.48)
        self.assertEqual(rows[0].close, 46.49)
        self.assertEqual(rows[0].dividend, 0.12)

    @patch("yfinance_watchlist.client.yf.Ticker")
    def test_fetch_history_rejects_future_year(self, ticker_cls: MagicMock) -> None:
        ticker_cls.return_value.history.return_value = self._history_frame()
        client = YahooFinanceClient()

        with patch.object(client, "_today", return_value=date(2026, 4, 24)):
            with self.assertRaisesRegex(ValueError, "future year 2027"):
                client.fetch_history("AAPL", 2027, 2027)

    @patch("yfinance_watchlist.client.yf.Ticker")
    def test_fetch_history_requires_expected_columns(self, ticker_cls: MagicMock) -> None:
        ticker = ticker_cls.return_value
        ticker.history.return_value = pd.DataFrame({"Open": [1.0]})

        with self.assertRaisesRegex(ValueError, "missing required fields"):
            YahooFinanceClient().fetch_history("AAPL", 2025, 2025)

    @staticmethod
    def _history_frame() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [101.0, 102.0],
                "Low": [99.0, 100.0],
                "Close": [100.5, 101.5],
                "Volume": [1000, 1200],
                "Dividends": [0.0, 0.25],
            },
            index=pd.to_datetime(["2025-01-02", "2025-01-03"]),
        )
