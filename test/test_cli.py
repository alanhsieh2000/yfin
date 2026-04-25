from __future__ import annotations

import csv
from contextlib import chdir
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timezone
from io import StringIO
import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from yfinance_watchlist.cli import main
from yfinance_watchlist.models import PriceHistoryRow, QuoteSnapshot


class CliTestCase(TestCase):
    def test_show_command_prints_current_watchlist(self) -> None:
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\nSPY,S&P 500 ETF\n", encoding="utf-8")

            with redirect_stdout(stdout):
                exit_code = main(["show", "--watchlist", str(watchlist)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            stdout.getvalue().strip().splitlines(),
            [
                f"Watchlist: {watchlist}",
                "AAPL,Apple",
                "SPY,S&P 500 ETF",
            ],
        )

    def test_show_command_reports_empty_watchlist(self) -> None:
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"

            with redirect_stdout(stdout):
                exit_code = main(["show", "--watchlist", str(watchlist)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            stdout.getvalue().strip().splitlines(),
            [
                f"Watchlist: {watchlist}",
                "No symbols configured.",
            ],
        )

    def test_add_command_writes_watchlist_csv(self) -> None:
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"

            with redirect_stdout(stdout):
                exit_code = main(["add", "AAPL", "Apple", "--watchlist", str(watchlist)])

            with open(watchlist, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"Saved AAPL,Apple to {watchlist}")
        self.assertEqual(rows, [{"symbol": "AAPL", "label": "Apple"}])

    def test_add_command_normalizes_trailing_comma_in_symbol(self) -> None:
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"

            with redirect_stdout(stdout):
                exit_code = main(["add", "AAPL,", "Apple Inc.", "--watchlist", str(watchlist)])

            with open(watchlist, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"Saved AAPL,Apple Inc. to {watchlist}")
        self.assertEqual(rows, [{"symbol": "AAPL", "label": "Apple Inc."}])

    def test_add_command_rejects_existing_symbol_when_input_symbol_has_trailing_comma(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\n", encoding="utf-8")

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["add", "AAPL,", "Apple Inc.", "--watchlist", str(watchlist)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Error: symbol AAPL is already in the watchlist with label Apple", stderr.getvalue())

    def test_add_command_writes_watchlist_csv_without_label(self) -> None:
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"

            with redirect_stdout(stdout):
                exit_code = main(["add", "SPY", "--watchlist", str(watchlist)])

            with open(watchlist, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"Saved SPY to {watchlist}")
        self.assertEqual(rows, [{"symbol": "SPY", "label": ""}])

    def test_add_command_rejects_existing_symbol_with_different_case(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\naapl,Apple\n", encoding="utf-8")

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["add", "AAPL", "Apple Inc", "--watchlist", str(watchlist)])

            with open(watchlist, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Error: symbol AAPL is already in the watchlist with label Apple", stderr.getvalue())
        self.assertEqual(rows, [{"symbol": "aapl", "label": "Apple"}])

    def test_remove_command_deletes_symbol(self) -> None:
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\nSPY,S&P 500 ETF\n", encoding="utf-8")

            with redirect_stdout(stdout):
                exit_code = main(["remove", "SPY", "--watchlist", str(watchlist)])

            with open(watchlist, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"Removed SPY,S&P 500 ETF from {watchlist}")
        self.assertEqual(rows, [{"symbol": "AAPL", "label": "Apple"}])

    def test_remove_command_deletes_symbol_without_label(self) -> None:
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\nSPY,\n", encoding="utf-8")

            with redirect_stdout(stdout):
                exit_code = main(["remove", "SPY", "--watchlist", str(watchlist)])

            with open(watchlist, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"Removed SPY from {watchlist}")
        self.assertEqual(rows, [{"symbol": "AAPL", "label": "Apple"}])

    def test_fetch_command_defaults_to_watchlist_csv(self) -> None:
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\n", encoding="utf-8")

            with patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_quote") as fetch_quote, patch(
                "yfinance_watchlist.cli.YahooFinanceClient.fetch_history_year"
            ) as fetch_history_year, patch(
                "yfinance_watchlist.cli._utc_now",
                return_value=datetime(2026, 4, 24, 9, 5, tzinfo=timezone.utc),
            ):
                fetch_quote.return_value = QuoteSnapshot(
                    symbol="AAPL",
                    currency="USD",
                    market_price=123.45,
                    market_time=datetime(2026, 4, 24, tzinfo=timezone.utc),
                )
                fetch_history_year.return_value = [self._history_row("2026-01-02T00:00:00+00:00", 0.0)]

                with chdir(tmpdir), redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "fetch",
                            "--output",
                            tmpdir,
                            "--start-year",
                            "2026",
                            "--end-year",
                            "2026",
                        ]
                    )

        self.assertEqual(exit_code, 0)
        self.assertIn("Loaded 1 symbols from watchlist.csv", stdout.getvalue())

    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_quote")
    def test_quote_command_prints_summary(self, fetch_quote) -> None:
        fetch_quote.return_value = QuoteSnapshot(
            symbol="AAPL",
            currency="USD",
            market_price=123.45,
            market_time=datetime(2026, 4, 24, tzinfo=timezone.utc),
        )
        stdout = StringIO()

        with redirect_stdout(stdout):
            exit_code = main(["quote", "AAPL"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            stdout.getvalue().strip().splitlines(),
            [
                "Symbol: AAPL",
                "Currency: USD",
                "Market Price: 123.45",
                "Market Time: 2026-04-24T00:00:00+00:00",
            ],
        )

    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_quote")
    def test_quote_command_prints_error(self, fetch_quote) -> None:
        fetch_quote.side_effect = ValueError("quote data for AAPL is missing regular market price")
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["quote", "AAPL"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Error: quote data for AAPL is missing regular market price", stderr.getvalue())

    @patch("yfinance_watchlist.cli._utc_now", return_value=datetime(2026, 4, 24, 9, 5, tzinfo=timezone.utc))
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_history_year")
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_quote")
    def test_fetch_command_updates_manifest(self, fetch_quote, fetch_history_year, _utc_now) -> None:
        fetch_quote.side_effect = [
            QuoteSnapshot("AAPL", "USD", 123.45, datetime(2026, 4, 24, tzinfo=timezone.utc)),
            QuoteSnapshot("SPY", "USD", 456.78, datetime(2026, 4, 24, tzinfo=timezone.utc)),
        ]
        fetch_history_year.side_effect = [
            [self._history_row("2025-01-02T00:00:00+00:00", 0.0)],
            [self._history_row("2026-01-02T00:00:00+00:00", 0.0)],
            [self._history_row("2025-01-02T00:00:00+00:00", 0.0)],
            [self._history_row("2026-01-02T00:00:00+00:00", 0.0)],
        ]
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\nSPY,S&P 500 ETF\n", encoding="utf-8")

            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "fetch",
                        "--watchlist",
                        str(watchlist),
                        "--output",
                        tmpdir,
                        "--start-year",
                        "2025",
                        "--end-year",
                        "2026",
                    ]
                )

            manifest_path = Path(tmpdir) / "2026-04-24T09-05Z" / "manifest.json"
            quotes_path = Path(tmpdir) / "2026-04-24T09-05Z" / "quotes.csv"
            history_index = Path(tmpdir) / "cache" / "history_index.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertTrue(quotes_path.exists())
            self.assertTrue(history_index.exists())
            self.assertEqual(len(manifest["years"]), 4)
            self.assertTrue(all(item["source"] == "fetched" for item in manifest["years"]))
            self.assertEqual(manifest["status"], "success")
            self.assertEqual(manifest["fetched_years"], 4)
            self.assertEqual(manifest["failed_years"], 0)

        self.assertEqual(exit_code, 0)
        self.assertIn("Completed: 0 cache hit, 0 refreshed, 4 fetched, 0 failed", stdout.getvalue())

    @patch("yfinance_watchlist.cli._utc_now", return_value=datetime(2026, 4, 24, 9, 5, tzinfo=timezone.utc))
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_history_year")
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_quote")
    @patch("yfinance_watchlist.cli.YahooFinanceClient._today", return_value=date(2026, 4, 24))
    def test_fetch_command_reports_mixed_sources_and_failure(
        self,
        _today,
        fetch_quote,
        fetch_history_year,
        _utc_now,
    ) -> None:
        fetch_quote.side_effect = [
            QuoteSnapshot("AAPL", "USD", 123.45, datetime(2026, 4, 24, tzinfo=timezone.utc)),
            QuoteSnapshot("MSFT", "USD", 456.78, datetime(2026, 4, 24, tzinfo=timezone.utc)),
            ValueError("quote data for BAD is missing regular market price"),
        ]
        fetch_history_year.side_effect = [
            [self._history_row("2026-04-24T00:00:00+00:00", 0.0)],
            [self._history_row("2026-04-24T00:00:00+00:00", 0.0)],
            [self._history_row("2026-04-24T00:00:00+00:00", 0.0)],
        ]
        stdout = StringIO()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            watchlist = cache_root / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\nMSFT,Microsoft\nBAD,Bad\n", encoding="utf-8")

            from yfinance_watchlist.cache import HistoryCache
            cache = HistoryCache(tmpdir)
            cache.write_year("AAPL", 2025, [self._history_row("2025-01-02T00:00:00+00:00", 0.0)])
            cache.write_year("AAPL", 2026, [self._history_row("2026-04-23T00:00:00+00:00", 0.0)])

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "fetch",
                        "--watchlist",
                        str(watchlist),
                        "--output",
                        tmpdir,
                        "--start-year",
                        "2025",
                        "--end-year",
                        "2026",
                    ]
                )

            manifest_path = Path(tmpdir) / "2026-04-24T09-05Z" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(manifest["status"], "partial_success")
        self.assertEqual(manifest["cached_years"], 1)
        self.assertEqual(manifest["refreshed_years"], 1)
        self.assertEqual(manifest["fetched_years"], 2)
        self.assertEqual(manifest["failed_years"], 2)
        self.assertEqual(
            [item["source"] for item in manifest["years"]],
            ["cache_hit", "cache_refresh", "fetched", "fetched", "failed", "failed"],
        )
        self.assertIn("Completed: 1 cache hit, 1 refreshed, 2 fetched, 2 failed", stdout.getvalue())
        self.assertIn("quote data for BAD is missing regular market price", stderr.getvalue())

    @patch("yfinance_watchlist.cli._utc_now", return_value=datetime(2026, 4, 24, 9, 5, tzinfo=timezone.utc))
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_quote")
    def test_fetch_command_returns_non_zero_when_all_years_fail(self, fetch_quote, _utc_now) -> None:
        fetch_quote.side_effect = ValueError("quote data for BAD is missing regular market price")
        stdout = StringIO()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nBAD,Bad\n", encoding="utf-8")

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "fetch",
                        "--watchlist",
                        str(watchlist),
                        "--output",
                        tmpdir,
                        "--start-year",
                        "2025",
                        "--end-year",
                        "2026",
                    ]
                )

            manifest_path = Path(tmpdir) / "2026-04-24T09-05Z" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["failed_years"], 2)
        self.assertIn("Completed: 0 cache hit, 0 refreshed, 0 fetched, 2 failed", stdout.getvalue())

    @patch("yfinance_watchlist.cli._utc_now", return_value=datetime(2026, 4, 24, 9, 5, tzinfo=timezone.utc))
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_history_year")
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_quote")
    def test_fetch_command_honors_fail_fast(self, fetch_quote, fetch_history_year, _utc_now) -> None:
        fetch_quote.side_effect = [
            QuoteSnapshot("AAPL", "USD", 123.45, datetime(2026, 4, 24, tzinfo=timezone.utc)),
            ValueError("quote data for BAD is missing regular market price"),
            QuoteSnapshot("MSFT", "USD", 456.78, datetime(2026, 4, 24, tzinfo=timezone.utc)),
        ]
        fetch_history_year.return_value = [self._history_row("2025-01-02T00:00:00+00:00", 0.0)]

        stdout = StringIO()
        stderr = StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\nBAD,Bad\nMSFT,Microsoft\n", encoding="utf-8")

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "fetch",
                        "--watchlist",
                        str(watchlist),
                        "--output",
                        tmpdir,
                        "--start-year",
                        "2025",
                        "--end-year",
                        "2026",
                        "--fail-fast",
                    ]
                )
            manifest_path = Path(tmpdir) / "2026-04-24T09-05Z" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertTrue(manifest["stopped_early"])
        self.assertEqual(len(manifest["years"]), 3)
        self.assertEqual(manifest["years"][-1]["source"], "failed")
        self.assertIn("quote data for BAD is missing regular market price", stderr.getvalue())

    def test_remove_command_prints_error_for_missing_symbol(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\n", encoding="utf-8")

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["remove", "SPY", "--watchlist", str(watchlist)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Error: symbol SPY is not in the watchlist", stderr.getvalue())

    @staticmethod
    def _history_row(timestamp: str, dividend: float) -> PriceHistoryRow:
        value = datetime.fromisoformat(timestamp)
        return PriceHistoryRow(
            timestamp=value,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000,
            dividend=dividend,
            stock_splits=0.0,
        )
