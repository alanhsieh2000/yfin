from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import os
import sys

from fastmcp import FastMCP
from fastmcp.server.auth import AuthProvider
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token

if __package__ in (None, ""):
    package_root = str(Path(__file__).resolve().parents[1])
    if package_root not in sys.path:
        sys.path.insert(0, package_root)
    __package__ = "yfinance_watchlist"

from .cli import DEFAULT_KEEP_RUNS, run_fetch_workflow
from .client import YahooFinanceClient
from .mcp_user_data import (
    USER_KEY_SECRET_ENV,
    McpUserDataPaths,
    resolve_mcp_user_data_paths,
)
from .models import PriceHistoryRow, QuoteSnapshot, WatchlistEntry
from .watchlist import WatchlistStore


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_PATH = "/mcp/"
_DEFAULT_AUTH = object()


def create_server(
    base_dir: Path | str = Path.cwd(),
    auth: AuthProvider | None | object = _DEFAULT_AUTH,
) -> FastMCP:
    root = Path(base_dir).resolve()
    auth_provider = _build_google_auth_from_env(required=False) if auth is _DEFAULT_AUTH else auth
    server = FastMCP("yfinance-watchlist", auth=auth_provider)

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
    def list_watchlist() -> dict:
        """Return entries from the caller's watchlist CSV file."""
        paths = _current_user_paths(root)
        entries = WatchlistStore().load_entries(str(paths.watchlist_path))
        return {
            "watchlist_path": str(paths.watchlist_path),
            "count": len(entries),
            "entries": [_watchlist_entry_to_dict(entry) for entry in entries],
        }

    @server.tool
    def add_watchlist_symbol(
        symbol: str,
        label: str | None = None,
    ) -> dict:
        """Add a symbol and optional label to the caller's watchlist CSV file."""
        paths = _current_user_paths(root)
        store = WatchlistStore()
        entry = store.add_entry(str(paths.watchlist_path), symbol, label)
        entries = store.load_entries(str(paths.watchlist_path))
        return {
            "watchlist_path": str(paths.watchlist_path),
            "entry": _watchlist_entry_to_dict(entry),
            "count": len(entries),
        }

    @server.tool
    def remove_watchlist_symbol(symbol: str) -> dict:
        """Remove a symbol from the caller's watchlist CSV file."""
        paths = _current_user_paths(root)
        store = WatchlistStore()
        entry = store.remove_entry(str(paths.watchlist_path), symbol)
        entries = store.load_entries(str(paths.watchlist_path))
        return {
            "watchlist_path": str(paths.watchlist_path),
            "entry": _watchlist_entry_to_dict(entry),
            "count": len(entries),
        }

    @server.tool
    def fetch_watchlist(
        start_year: int,
        end_year: int,
        fail_fast: bool = False,
        keep_runs: int = DEFAULT_KEEP_RUNS,
    ) -> dict:
        """Fetch quotes and yearly history for the caller's watchlist."""
        paths = _current_user_paths(root)
        return run_fetch_workflow(
            str(paths.watchlist_path),
            str(paths.runs_root),
            start_year,
            end_year,
            fail_fast=fail_fast,
            keep_runs=keep_runs,
            cache_output_dir=str(paths.shared_cache_root),
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
    _require_user_key_secret_from_env()
    server = create_server(args.base_dir, auth=_build_google_auth_from_env(required=True))
    server.run(transport="http", host=args.host, port=args.port, path=args.path)
    return 0


def _build_google_auth_from_env(required: bool) -> AuthProvider | None:
    keys = [
        "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID",
        "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET",
        "FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL",
    ]
    values = {key: os.environ.get(key) for key in keys}
    missing = [key for key, value in values.items() if not value]
    if missing:
        if required:
            raise ValueError(f"missing required auth environment variables: {', '.join(missing)}")
        return None

    return GoogleProvider(
        client_id=values["FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID"] or "",
        client_secret=values["FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET"],
        base_url=values["FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL"] or "",
        required_scopes=["openid"],
    )


def _current_user_paths(root: Path) -> McpUserDataPaths:
    return resolve_mcp_user_data_paths(root, get_access_token())


def _require_user_key_secret_from_env() -> None:
    if not os.environ.get(USER_KEY_SECRET_ENV):
        raise ValueError(f"{USER_KEY_SECRET_ENV} is required")


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
