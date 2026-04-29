from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
import runpy
import sys
import tempfile
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from fastmcp import Client

from yfinance_watchlist.mcp_server import create_server
from yfinance_watchlist.models import PriceHistoryRow, QuoteSnapshot


class McpServerTestCase(IsolatedAsyncioTestCase):
    async def test_server_file_loads_without_package_context(self) -> None:
        server_path = Path(__file__).resolve().parents[1] / "src" / "yfinance_watchlist" / "mcp_server.py"
        original_path = list(sys.path)
        try:
            module_globals = runpy.run_path(str(server_path))
        finally:
            sys.path[:] = original_path

        self.assertIn("create_server", module_globals)
        self.assertIn("mcp", module_globals)

    async def test_server_lists_expected_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            async with Client(create_server(tmpdir)) as client:
                tools = await client.list_tools()

        names = {tool.name for tool in tools}
        self.assertIn("get_quote", names)
        self.assertIn("get_history", names)
        self.assertIn("list_watchlist", names)
        self.assertIn("add_watchlist_symbol", names)
        self.assertIn("remove_watchlist_symbol", names)
        self.assertIn("fetch_watchlist", names)

    async def test_get_quote_returns_serialized_quote(self) -> None:
        with patch("yfinance_watchlist.mcp_server.YahooFinanceClient.fetch_quote") as fetch_quote:
            fetch_quote.return_value = QuoteSnapshot(
                symbol="AAPL",
                currency="USD",
                market_price=123.45,
                market_time=datetime(2026, 4, 24, tzinfo=timezone.utc),
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                async with Client(create_server(tmpdir)) as client:
                    result = await client.call_tool("get_quote", {"symbol": "AAPL"})

        self.assertEqual(
            result.data,
            {
                "symbol": "AAPL",
                "currency": "USD",
                "market_price": 123.45,
                "market_time": "2026-04-24T00:00:00+00:00",
            },
        )

    async def test_get_history_returns_serialized_rows(self) -> None:
        rows = [
            PriceHistoryRow(
                timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000,
                dividend=0.0,
                stock_splits=0.0,
            )
        ]

        with patch("yfinance_watchlist.mcp_server.YahooFinanceClient.fetch_history") as fetch_history:
            fetch_history.return_value = rows

            with tempfile.TemporaryDirectory() as tmpdir:
                async with Client(create_server(tmpdir)) as client:
                    result = await client.call_tool(
                        "get_history",
                        {"symbol": "AAPL", "start_year": 2026, "end_year": 2026},
                    )

        self.assertEqual(result.data["symbol"], "AAPL")
        self.assertEqual(result.data["row_count"], 1)
        self.assertEqual(result.data["rows"][0]["timestamp"], "2026-01-02T00:00:00+00:00")

    async def test_list_watchlist_reads_relative_path_under_base_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\nSPY,S&P 500 ETF\n", encoding="utf-8")

            async with Client(create_server(tmpdir)) as client:
                result = await client.call_tool("list_watchlist", {})

        self.assertEqual(result.data["count"], 2)
        self.assertEqual(
            result.data["entries"],
            [
                {"symbol": "AAPL", "label": "Apple"},
                {"symbol": "SPY", "label": "S&P 500 ETF"},
            ],
        )

    async def test_add_watchlist_symbol_writes_relative_path_under_base_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            async with Client(create_server(tmpdir)) as client:
                result = await client.call_tool(
                    "add_watchlist_symbol",
                    {"symbol": "aapl,", "label": ", Apple Inc."},
                )
                list_result = await client.call_tool("list_watchlist", {})

        self.assertEqual(result.data["entry"], {"symbol": "AAPL", "label": "Apple Inc."})
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(list_result.data["entries"], [{"symbol": "AAPL", "label": "Apple Inc."}])

    async def test_remove_watchlist_symbol_writes_relative_path_under_base_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\nSPY,S&P 500 ETF\n", encoding="utf-8")

            async with Client(create_server(tmpdir)) as client:
                result = await client.call_tool("remove_watchlist_symbol", {"symbol": "spy"})
                list_result = await client.call_tool("list_watchlist", {})

        self.assertEqual(result.data["entry"], {"symbol": "SPY", "label": "S&P 500 ETF"})
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(list_result.data["entries"], [{"symbol": "AAPL", "label": "Apple"}])

    async def test_fetch_watchlist_writes_manifest_and_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist = Path(tmpdir) / "watchlist.csv"
            watchlist.write_text("symbol,label\nAAPL,Apple\n", encoding="utf-8")

            with patch("yfinance_watchlist.cli._utc_now") as utc_now, patch(
                "yfinance_watchlist.cli.YahooFinanceClient.fetch_quote"
            ) as fetch_quote, patch(
                "yfinance_watchlist.cli.YahooFinanceClient.fetch_history_year"
            ) as fetch_history_year:
                utc_now.return_value = datetime(2026, 4, 24, 9, 5, tzinfo=timezone.utc)
                fetch_quote.return_value = QuoteSnapshot(
                    symbol="AAPL",
                    currency="USD",
                    market_price=123.45,
                    market_time=datetime(2026, 4, 24, tzinfo=timezone.utc),
                )
                fetch_history_year.return_value = [
                    PriceHistoryRow(
                        timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
                        open=100.0,
                        high=101.0,
                        low=99.0,
                        close=100.5,
                        volume=1000,
                        dividend=0.0,
                        stock_splits=0.0,
                    )
                ]

                async with Client(create_server(tmpdir)) as client:
                    result = await client.call_tool(
                        "fetch_watchlist",
                        {"start_year": 2026, "end_year": 2026},
                    )

            manifest_path = Path(result.data["manifest_path"])
            quotes_path = Path(result.data["quotes_path"])
            manifest_exists = manifest_path.exists()
            quotes_exists = quotes_path.exists()

        self.assertEqual(result.data["exit_code"], 0)
        self.assertEqual(result.data["manifest"]["status"], "success")
        self.assertEqual(result.data["manifest"]["fetched_years"], 1)
        self.assertTrue(manifest_exists)
        self.assertTrue(quotes_exists)

    async def test_file_tools_reject_paths_outside_base_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            async with Client(create_server(tmpdir)) as client:
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    parent_result = await client.call_tool(
                        "list_watchlist",
                        {"watchlist_path": "../watchlist.csv"},
                        raise_on_error=False,
                    )
                    absolute_result = await client.call_tool(
                        "fetch_watchlist",
                        {
                            "watchlist_path": "/tmp/watchlist.csv",
                            "output_dir": "data",
                            "start_year": 2026,
                            "end_year": 2026,
                        },
                        raise_on_error=False,
                    )
                    add_result = await client.call_tool(
                        "add_watchlist_symbol",
                        {
                            "watchlist_path": "../watchlist.csv",
                            "symbol": "AAPL",
                        },
                        raise_on_error=False,
                    )
                    remove_result = await client.call_tool(
                        "remove_watchlist_symbol",
                        {
                            "watchlist_path": "/tmp/watchlist.csv",
                            "symbol": "AAPL",
                        },
                        raise_on_error=False,
                    )

        self.assertTrue(parent_result.is_error)
        self.assertIn("watchlist_path must stay under", parent_result.content[0].text)
        self.assertTrue(absolute_result.is_error)
        self.assertIn("watchlist_path must be a relative path", absolute_result.content[0].text)
        self.assertTrue(add_result.is_error)
        self.assertIn("watchlist_path must stay under", add_result.content[0].text)
        self.assertTrue(remove_result.is_error)
        self.assertIn("watchlist_path must be a relative path", remove_result.content[0].text)
