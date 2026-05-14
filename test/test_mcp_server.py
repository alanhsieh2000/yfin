from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import os
from pathlib import Path
import runpy
import sys
import tempfile
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from fastmcp import Client

from yfinance_watchlist.mcp_server import create_server
from yfinance_watchlist.mcp_user_data import derive_user_key
from yfinance_watchlist.models import PriceHistoryRow, QuoteSnapshot


TEST_USER_KEY_SECRET = "test-user-key-secret"


class FakeToken:
    def __init__(self, sub: str | None = "user-a") -> None:
        self.claims = {"sub": sub} if sub is not None else {}
        self.scopes = ["openid"]


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
            async with Client(create_server(tmpdir, auth=None)) as client:
                tools = await client.list_tools()

        names = {tool.name for tool in tools}
        self.assertIn("get_quote", names)
        self.assertIn("get_history", names)
        self.assertIn("list_watchlist", names)
        self.assertIn("add_watchlist_symbol", names)
        self.assertIn("remove_watchlist_symbol", names)
        self.assertIn("fetch_watchlist", names)

    async def test_file_tools_do_not_expose_path_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            async with Client(create_server(tmpdir, auth=None)) as client:
                tools = await client.list_tools()

        tools_by_name = {tool.name: tool for tool in tools}
        for name in [
            "list_watchlist",
            "add_watchlist_symbol",
            "remove_watchlist_symbol",
            "fetch_watchlist",
        ]:
            properties = tools_by_name[name].inputSchema.get("properties", {})
            self.assertNotIn("watchlist_path", properties)
            self.assertNotIn("output_dir", properties)

    async def test_get_quote_returns_serialized_quote(self) -> None:
        with patch("yfinance_watchlist.mcp_server.YahooFinanceClient.fetch_quote") as fetch_quote:
            fetch_quote.return_value = QuoteSnapshot(
                symbol="AAPL",
                currency="USD",
                market_price=123.45,
                market_time=datetime(2026, 4, 24, tzinfo=timezone.utc),
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                async with Client(create_server(tmpdir, auth=None)) as client:
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
                async with Client(create_server(tmpdir, auth=None)) as client:
                    result = await client.call_tool(
                        "get_history",
                        {"symbol": "AAPL", "start_year": 2026, "end_year": 2026},
                    )

        self.assertEqual(result.data["symbol"], "AAPL")
        self.assertEqual(result.data["row_count"], 1)
        self.assertEqual(result.data["rows"][0]["timestamp"], "2026-01-02T00:00:00+00:00")

    async def test_list_watchlist_reads_authenticated_user_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            user_key = derive_user_key("user-a", TEST_USER_KEY_SECRET)
            watchlist = Path(tmpdir) / "data" / "users" / user_key / "watchlist.csv"
            watchlist.parent.mkdir(parents=True)
            watchlist.write_text("symbol,label\nAAPL,Apple\nSPY,S&P 500 ETF\n", encoding="utf-8")

            with mcp_user("user-a"):
                async with Client(create_server(tmpdir, auth=None)) as client:
                    result = await client.call_tool("list_watchlist", {})

        self.assertEqual(result.data["count"], 2)
        self.assertEqual(result.data["watchlist_path"], str(watchlist))
        self.assertEqual(
            result.data["entries"],
            [
                {"symbol": "AAPL", "label": "Apple"},
                {"symbol": "SPY", "label": "S&P 500 ETF"},
            ],
        )

    async def test_add_watchlist_symbol_writes_authenticated_user_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            user_key = derive_user_key("user-a", TEST_USER_KEY_SECRET)
            watchlist = Path(tmpdir) / "data" / "users" / user_key / "watchlist.csv"

            with mcp_user("user-a"):
                async with Client(create_server(tmpdir, auth=None)) as client:
                    result = await client.call_tool(
                        "add_watchlist_symbol",
                        {"symbol": "aapl,", "label": ", Apple Inc."},
                    )
                    list_result = await client.call_tool("list_watchlist", {})
            watchlist_exists = watchlist.exists()

        self.assertEqual(result.data["entry"], {"symbol": "AAPL", "label": "Apple Inc."})
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["watchlist_path"], str(watchlist))
        self.assertEqual(list_result.data["entries"], [{"symbol": "AAPL", "label": "Apple Inc."}])
        self.assertTrue(watchlist_exists)

    async def test_remove_watchlist_symbol_writes_authenticated_user_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            user_key = derive_user_key("user-a", TEST_USER_KEY_SECRET)
            watchlist = Path(tmpdir) / "data" / "users" / user_key / "watchlist.csv"
            watchlist.parent.mkdir(parents=True)
            watchlist.write_text("symbol,label\nAAPL,Apple\nSPY,S&P 500 ETF\n", encoding="utf-8")

            with mcp_user("user-a"):
                async with Client(create_server(tmpdir, auth=None)) as client:
                    result = await client.call_tool("remove_watchlist_symbol", {"symbol": "spy"})
                    list_result = await client.call_tool("list_watchlist", {})

        self.assertEqual(result.data["entry"], {"symbol": "SPY", "label": "S&P 500 ETF"})
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["watchlist_path"], str(watchlist))
        self.assertEqual(list_result.data["entries"], [{"symbol": "AAPL", "label": "Apple"}])

    async def test_mcp_watchlists_are_isolated_by_authenticated_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mcp_user("user-a"):
                async with Client(create_server(tmpdir, auth=None)) as client:
                    add_result = await client.call_tool(
                        "add_watchlist_symbol",
                        {"symbol": "AAPL", "label": "Apple"},
                    )

            with mcp_user("user-b"):
                async with Client(create_server(tmpdir, auth=None)) as client:
                    user_b_result = await client.call_tool("list_watchlist", {})

            with mcp_user("user-a"):
                async with Client(create_server(tmpdir, auth=None)) as client:
                    user_a_result = await client.call_tool("list_watchlist", {})

        self.assertEqual(add_result.data["count"], 1)
        self.assertEqual(user_b_result.data["count"], 0)
        self.assertEqual(user_b_result.data["entries"], [])
        self.assertEqual(user_a_result.data["entries"], [{"symbol": "AAPL", "label": "Apple"}])
        self.assertNotEqual(user_a_result.data["watchlist_path"], user_b_result.data["watchlist_path"])

    async def test_fetch_watchlist_writes_user_run_and_shared_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            user_key = derive_user_key("user-a", TEST_USER_KEY_SECRET)
            user_root = Path(tmpdir) / "data" / "users" / user_key
            watchlist = user_root / "watchlist.csv"
            watchlist.parent.mkdir(parents=True)
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

                with mcp_user("user-a"):
                    async with Client(create_server(tmpdir, auth=None)) as client:
                        result = await client.call_tool(
                            "fetch_watchlist",
                            {"start_year": 2026, "end_year": 2026},
                        )

            manifest_path = Path(result.data["manifest_path"])
            quotes_path = Path(result.data["quotes_path"])
            cache_path = Path(tmpdir) / "data" / "shared" / "cache" / "history" / "AAPL" / "2026.csv"
            manifest_exists = manifest_path.exists()
            quotes_exists = quotes_path.exists()
            cache_exists = cache_path.exists()

        self.assertEqual(result.data["exit_code"], 0)
        self.assertEqual(result.data["manifest"]["status"], "success")
        self.assertEqual(result.data["manifest"]["fetched_years"], 1)
        self.assertEqual(manifest_path.parent, user_root / "runs" / "2026-04-24T09-05Z")
        self.assertEqual(quotes_path.parent, manifest_path.parent)
        self.assertEqual(result.data["manifest"]["years"][0]["path"], str(cache_path))
        self.assertTrue(manifest_exists)
        self.assertTrue(quotes_exists)
        self.assertTrue(cache_exists)

    async def test_file_tools_require_authenticated_google_subject(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"YFIN_USER_KEY_SECRET": TEST_USER_KEY_SECRET}), patch(
                "yfinance_watchlist.mcp_server.get_access_token",
                return_value=None,
            ):
                async with Client(create_server(tmpdir, auth=None)) as client:
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        missing_token_result = await client.call_tool(
                            "list_watchlist",
                            {},
                            raise_on_error=False,
                        )

            with patch.dict(os.environ, {"YFIN_USER_KEY_SECRET": TEST_USER_KEY_SECRET}), patch(
                "yfinance_watchlist.mcp_server.get_access_token",
                return_value=FakeToken(sub=None),
            ):
                async with Client(create_server(tmpdir, auth=None)) as client:
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        missing_sub_result = await client.call_tool(
                            "add_watchlist_symbol",
                            {"symbol": "AAPL"},
                            raise_on_error=False,
                        )

        self.assertTrue(missing_token_result.is_error)
        self.assertIn("authenticated Google subject is required", missing_token_result.content[0].text)
        self.assertTrue(missing_sub_result.is_error)
        self.assertIn("authenticated Google subject is required", missing_sub_result.content[0].text)


@contextmanager
def mcp_user(sub: str):
    with patch.dict(os.environ, {"YFIN_USER_KEY_SECRET": TEST_USER_KEY_SECRET}), patch(
        "yfinance_watchlist.mcp_server.get_access_token",
        return_value=FakeToken(sub),
    ):
        yield
