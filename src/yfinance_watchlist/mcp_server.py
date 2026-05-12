from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import sys
import os

from fastmcp import FastMCP
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token

if __package__ in (None, ""):
    package_root = str(Path(__file__).resolve().parents[1])
    if package_root not in sys.path:
        sys.path.insert(0, package_root)
    __package__ = "yfinance_watchlist"

from .cli import DEFAULT_KEEP_RUNS, DEFAULT_WATCHLIST_PATH, run_fetch_workflow
from .client import YahooFinanceClient
from .models import PriceHistoryRow, QuoteSnapshot, WatchlistEntry
from .watchlist import WatchlistStore


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_PATH = "/mcp/"


def create_server(base_dir: Path | str = Path.cwd()) -> FastMCP:
    root = Path(base_dir).resolve()
    auth = GoogleProvider(
        client_id=os.environ["FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID"],
        client_secret=os.environ["FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET"],
        base_url=os.environ["FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL"],
        required_scopes=["openid"],
    )
    server = FastMCP("yfinance-watchlist", auth=auth)

    @server.tool
    def get_quote(symbol: str) -> dict:
        """Fetch a single Yahoo Finance quote."""
        quote = YahooFinanceClient().fetch_quote(symbol)
        return _quote_to_dict(quote)

    @server.tool
    def get_history(symbol: str, start_year: int, end_year: int) -> dict:
        """Fetch normalized daily price history for an inclusive year range."""
        rows = YahooFinanceClient().fetch_history(symbol, start_year, end_year)
        return {
            "symbol": symbol,
            "start_year": start_year,
            "end_year": end_year,
            "row_count": len(rows),
            "rows": [_history_row_to_dict(row) for row in rows],
        }

    @server.tool
    def list_watchlist(watchlist_path: str = DEFAULT_WATCHLIST_PATH) -> dict:
        """Return entries from a watchlist CSV file under the server base directory."""
        resolved_watchlist = _resolve_relative_path(root, watchlist_path, "watchlist_path")
        entries = WatchlistStore().load_entries(str(resolved_watchlist))
        return {
            "watchlist_path": str(resolved_watchlist),
            "count": len(entries),
            "entries": [_watchlist_entry_to_dict(entry) for entry in entries],
        }

    @server.tool
    def add_watchlist_symbol(
        symbol: str,
        label: str | None = None,
        watchlist_path: str = DEFAULT_WATCHLIST_PATH,
    ) -> dict:
        """Add a symbol and optional label to a watchlist CSV file under the server base directory."""
        resolved_watchlist = _resolve_relative_path(root, watchlist_path, "watchlist_path")
        store = WatchlistStore()
        entry = store.add_entry(str(resolved_watchlist), symbol, label)
        entries = store.load_entries(str(resolved_watchlist))
        return {
            "watchlist_path": str(resolved_watchlist),
            "entry": _watchlist_entry_to_dict(entry),
            "count": len(entries),
        }

    @server.tool
    def remove_watchlist_symbol(
        symbol: str,
        watchlist_path: str = DEFAULT_WATCHLIST_PATH,
    ) -> dict:
        """Remove a symbol from a watchlist CSV file under the server base directory."""
        resolved_watchlist = _resolve_relative_path(root, watchlist_path, "watchlist_path")
        store = WatchlistStore()
        entry = store.remove_entry(str(resolved_watchlist), symbol)
        entries = store.load_entries(str(resolved_watchlist))
        return {
            "watchlist_path": str(resolved_watchlist),
            "entry": _watchlist_entry_to_dict(entry),
            "count": len(entries),
        }

    @server.tool
    def fetch_watchlist(
        start_year: int,
        end_year: int,
        watchlist_path: str = DEFAULT_WATCHLIST_PATH,
        output_dir: str = "data",
        fail_fast: bool = False,
        keep_runs: int = DEFAULT_KEEP_RUNS,
    ) -> dict:
        """Fetch quotes and yearly history for a watchlist under the server base directory."""
        resolved_watchlist = _resolve_relative_path(root, watchlist_path, "watchlist_path")
        resolved_output = _resolve_relative_path(root, output_dir, "output_dir")
        return run_fetch_workflow(
            str(resolved_watchlist),
            str(resolved_output),
            start_year,
            end_year,
            fail_fast=fail_fast,
            keep_runs=keep_runs,
        )

    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yfinance_watchlist.mcp_server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--base-dir", default=".")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    server = create_server(args.base_dir)
    server.run(transport="http", host=args.host, port=args.port, path=args.path)
    return 0


def _resolve_relative_path(base_dir: Path, value: str, name: str) -> Path:
    raw_path = Path(value)
    if raw_path.is_absolute():
        raise ValueError(f"{name} must be a relative path under {base_dir}")

    resolved = (base_dir / raw_path).resolve()
    try:
        resolved.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError(f"{name} must stay under {base_dir}") from exc
    return resolved


def _quote_to_dict(quote: QuoteSnapshot) -> dict:
    return {
        "symbol": quote.symbol,
        "currency": quote.currency,
        "market_price": quote.market_price,
        "market_time": quote.market_time.isoformat(),
    }


def _history_row_to_dict(row: PriceHistoryRow) -> dict:
    payload = asdict(row)
    payload["timestamp"] = row.timestamp.isoformat()
    return payload


def _watchlist_entry_to_dict(entry: WatchlistEntry) -> dict:
    return {
        "symbol": entry.symbol,
        "label": entry.label,
    }


mcp = create_server()


if __name__ == "__main__":
    raise SystemExit(main())
