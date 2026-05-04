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

from yfinance_watchlist.cli import DEFAULT_KEEP_RUNS, DEFAULT_WATCHLIST_PATH, main
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

    def test_fetch_command_defaults_to_data_watchlist_csv(self) -> None:
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / DEFAULT_WATCHLIST_PATH
            watchlist.parent.mkdir()
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
        self.assertIn(f"Loaded 1 symbols from {DEFAULT_WATCHLIST_PATH}", stdout.getvalue())

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
            self.assertEqual(manifest["keep_runs"], DEFAULT_KEEP_RUNS)
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
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_history_year")
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_quote")
    @patch("yfinance_watchlist.cli.YahooFinanceClient._today", return_value=date(2026, 4, 24))
    def test_fetch_command_refreshes_all_cached_years_after_new_dividend(
        self,
        _today,
        fetch_quote,
        fetch_history_year,
        _utc_now,
    ) -> None:
        fetch_quote.return_value = QuoteSnapshot(
            "AAPL", "USD", 123.45, datetime(2026, 4, 24, tzinfo=timezone.utc)
        )
        fetch_history_year.side_effect = [
            [self._history_row("2026-01-02T00:00:00+00:00", 0.0), self._history_row("2026-04-24T00:00:00+00:00", 0.35)],
            [self._history_row("2025-01-02T00:00:00+00:00", 0.0)],
        ]
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\n", encoding="utf-8")

            from yfinance_watchlist.cache import HistoryCache

            cache = HistoryCache(tmpdir)
            cache.write_year("AAPL", 2025, [self._history_row("2025-01-02T00:00:00+00:00", 0.0)])
            cache.write_year("AAPL", 2026, [self._history_row("2026-01-02T00:00:00+00:00", 0.0)])

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
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual([item["source"] for item in manifest["years"]], ["cache_refresh", "cache_refresh"])
        self.assertEqual(manifest["cached_years"], 0)
        self.assertEqual(manifest["refreshed_years"], 2)
        self.assertIn("Completed: 0 cache hit, 2 refreshed, 0 fetched, 0 failed", stdout.getvalue())

    @patch("yfinance_watchlist.cli._utc_now", return_value=datetime(2026, 4, 24, 9, 5, tzinfo=timezone.utc))
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_history_year")
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_quote")
    @patch("yfinance_watchlist.cli.YahooFinanceClient._today", return_value=date(2026, 4, 24))
    def test_fetch_command_refreshes_prior_cached_years_when_fetching_new_year_after_new_dividend(
        self,
        _today,
        fetch_quote,
        fetch_history_year,
        _utc_now,
    ) -> None:
        fetch_quote.return_value = QuoteSnapshot(
            "AAPL", "USD", 123.45, datetime(2026, 4, 24, tzinfo=timezone.utc)
        )
        stdout = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\n", encoding="utf-8")

            from yfinance_watchlist.cache import HistoryCache

            cache = HistoryCache(tmpdir)
            original_2025_rows = [self._history_row("2025-01-02T00:00:00+00:00", 0.0)]
            cache.write_year("AAPL", 2025, original_2025_rows)
            refreshed_2025_payload = [
                PriceHistoryRow(
                    timestamp=datetime(2025, 1, 2, tzinfo=timezone.utc),
                    open=95.0,
                    high=96.0,
                    low=94.0,
                    close=95.5,
                    volume=1000,
                    dividend=0.0,
                    stock_splits=0.0,
                )
            ]
            fetch_history_year.side_effect = [
                [
                    self._history_row("2026-01-02T00:00:00+00:00", 0.0),
                    self._history_row("2026-04-24T00:00:00+00:00", 0.35),
                ],
                refreshed_2025_payload,
            ]

            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "fetch",
                        "--watchlist",
                        str(watchlist),
                        "--output",
                        tmpdir,
                        "--start-year",
                        "2026",
                        "--end-year",
                        "2026",
                    ]
                )

            manifest_path = Path(tmpdir) / "2026-04-24T09-05Z" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            refreshed_2025_rows = cache.read_year("AAPL", 2025)

        self.assertEqual(exit_code, 0)
        self.assertEqual([item["source"] for item in manifest["years"]], ["fetched"])
        self.assertEqual(manifest["cached_years"], 0)
        self.assertEqual(manifest["refreshed_years"], 0)
        self.assertEqual(manifest["fetched_years"], 1)
        self.assertEqual(fetch_history_year.call_count, 2)
        self.assertEqual(fetch_history_year.call_args_list[1].args, ("AAPL", 2025))
        self.assertEqual(refreshed_2025_rows, refreshed_2025_payload)
        self.assertIn("Completed: 0 cache hit, 0 refreshed, 1 fetched, 0 failed", stdout.getvalue())

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

    @patch("yfinance_watchlist.cli._utc_now", return_value=datetime(2026, 4, 24, 9, 5, tzinfo=timezone.utc))
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_history_year")
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_quote")
    def test_fetch_command_prunes_old_run_dirs_with_default_retention(
        self, fetch_quote, fetch_history_year, _utc_now
    ) -> None:
        fetch_quote.return_value = QuoteSnapshot(
            "AAPL", "USD", 123.45, datetime(2026, 4, 24, tzinfo=timezone.utc)
        )
        fetch_history_year.return_value = [self._history_row("2026-01-02T00:00:00+00:00", 0.0)]

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\n", encoding="utf-8")
            cache_dir = Path(tmpdir) / "cache" / "history"
            cache_dir.mkdir(parents=True)
            for index in range(DEFAULT_KEEP_RUNS):
                run_dir = Path(tmpdir) / f"2026-04-24T08-{index:02d}Z"
                run_dir.mkdir()
                (run_dir / "manifest.json").write_text("{}", encoding="utf-8")

            exit_code = main(
                [
                    "fetch",
                    "--watchlist",
                    str(watchlist),
                    "--output",
                    tmpdir,
                    "--start-year",
                    "2026",
                    "--end-year",
                    "2026",
                ]
            )

            run_dirs = self._run_dir_names(tmpdir)
            cache_exists = cache_dir.exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(run_dirs), DEFAULT_KEEP_RUNS)
        self.assertIn("2026-04-24T09-05Z", run_dirs)
        self.assertNotIn("2026-04-24T08-00Z", run_dirs)
        self.assertTrue(cache_exists)

    @patch("yfinance_watchlist.cli._utc_now", return_value=datetime(2026, 4, 24, 9, 5, tzinfo=timezone.utc))
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_history_year")
    @patch("yfinance_watchlist.cli.YahooFinanceClient.fetch_quote")
    def test_fetch_command_honors_keep_runs_override_and_preserves_unrelated_dirs(
        self, fetch_quote, fetch_history_year, _utc_now
    ) -> None:
        fetch_quote.return_value = QuoteSnapshot(
            "AAPL", "USD", 123.45, datetime(2026, 4, 24, tzinfo=timezone.utc)
        )
        fetch_history_year.return_value = [self._history_row("2026-01-02T00:00:00+00:00", 0.0)]

        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\n", encoding="utf-8")
            notes_dir = Path(tmpdir) / "notes"
            notes_dir.mkdir()
            for stamp in ["2026-04-24T08-00Z", "2026-04-24T08-01Z", "2026-04-24T08-02Z"]:
                (Path(tmpdir) / stamp).mkdir()

            exit_code = main(
                [
                    "fetch",
                    "--watchlist",
                    str(watchlist),
                    "--output",
                    tmpdir,
                    "--start-year",
                    "2026",
                    "--end-year",
                    "2026",
                    "--keep-runs",
                    "3",
                ]
            )

            run_dirs = self._run_dir_names(tmpdir)
            manifest = json.loads((Path(tmpdir) / "2026-04-24T09-05Z" / "manifest.json").read_text(encoding="utf-8"))
            notes_exists = notes_dir.exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(run_dirs, ["2026-04-24T08-01Z", "2026-04-24T08-02Z", "2026-04-24T09-05Z"])
        self.assertTrue(notes_exists)
        self.assertEqual(manifest["keep_runs"], 3)

    def test_fetch_command_rejects_keep_runs_less_than_one(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "fetch",
                        "--output",
                        tmpdir,
                        "--start-year",
                        "2026",
                        "--end-year",
                        "2026",
                        "--keep-runs",
                        "0",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Error: keep_runs must be greater than or equal to 1", stderr.getvalue())

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

    @staticmethod
    def _run_dir_names(root: str) -> list[str]:
        return sorted(path.name for path in Path(root).iterdir() if path.is_dir() and path.name[:4].isdigit())
