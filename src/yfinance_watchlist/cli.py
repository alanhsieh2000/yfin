from __future__ import annotations

import argparse
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import sys

from .cache import HistoryCache
from .client import YahooFinanceClient
from .results import FetchRunSummary, SymbolYearResult
from .store import FileStore
from .watchlist import WatchlistReader


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yfinance_watchlist")
    subparsers = parser.add_subparsers(dest="command", required=True)

    quote_parser = subparsers.add_parser("quote", help="Fetch and print a single quote")
    quote_parser.add_argument("symbol")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch quotes and yearly history for a watchlist")
    fetch_parser.add_argument("--watchlist", required=True)
    fetch_parser.add_argument("--output", required=True)
    fetch_parser.add_argument("--start-year", type=int, required=True)
    fetch_parser.add_argument("--end-year", type=int, required=True)
    fetch_parser.add_argument("--fail-fast", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "quote":
        client = YahooFinanceClient()
        try:
            quote = client.fetch_quote(args.symbol)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        print(f"Symbol: {quote.symbol}")
        print(f"Currency: {quote.currency}")
        print(f"Market Price: {quote.market_price}")
        print(f"Market Time: {quote.market_time.isoformat()}")
        return 0

    if args.command == "fetch":
        return run_fetch_command(
            args.watchlist,
            args.output,
            args.start_year,
            args.end_year,
            fail_fast=args.fail_fast,
        )

    parser.error(f"unsupported command: {args.command}")
    return 2


def run_fetch_command(
    watchlist_path: str,
    output_dir: str,
    start_year: int,
    end_year: int,
    fail_fast: bool = False,
) -> int:
    if start_year > end_year:
        print("Error: start_year must be less than or equal to end_year", file=sys.stderr)
        return 1

    client = YahooFinanceClient()
    reader = WatchlistReader()
    store = FileStore()
    cache = HistoryCache(output_dir)

    try:
        entries = reader.load(watchlist_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    run_dir = _make_run_dir(output_dir)
    summary = FetchRunSummary(run_dir=run_dir)
    quotes = []
    stop_processing = False
    for entry in entries:
        quote_error: str | None = None
        try:
            quotes.append(client.fetch_quote(entry.symbol))
        except ValueError as exc:
            quote_error = str(exc)
            print(f"Error: {quote_error}", file=sys.stderr)

        for year in range(start_year, end_year + 1):
            if quote_error is not None:
                summary.add_result(
                    SymbolYearResult(
                        symbol=entry.symbol,
                        label=entry.label,
                        year=year,
                        status="failed",
                        source="failed",
                        error=quote_error,
                    )
                )
                if fail_fast:
                    summary.stopped_early = True
                    stop_processing = True
                    break
                continue

            try:
                source, path, row_count, last_timestamp = _resolve_history(client, cache, entry.symbol, year)
                summary.add_result(
                    SymbolYearResult(
                        symbol=entry.symbol,
                        label=entry.label,
                        year=year,
                        status="success",
                        source=source,
                        path=path,
                        row_count=row_count,
                        last_timestamp=last_timestamp,
                    )
                )
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                summary.add_result(
                    SymbolYearResult(
                        symbol=entry.symbol,
                        label=entry.label,
                        year=year,
                        status="failed",
                        source="failed",
                        error=str(exc),
                    )
                )
                if fail_fast:
                    summary.stopped_early = True
                    stop_processing = True
                    break
        if stop_processing:
            break

    quotes_path = store.write_quotes(run_dir, quotes, entries)
    manifest = {
        "generated_at": _utc_now().isoformat(),
        "watchlist": watchlist_path,
        "run_dir": run_dir,
        "quotes_path": quotes_path,
        "start_year": start_year,
        "end_year": end_year,
        **summary.to_manifest_dict(),
    }
    manifest_path = store.write_manifest(run_dir, manifest)

    print(f"Loaded {len(entries)} symbols from {watchlist_path}")
    print(f"Wrote outputs to {run_dir}")
    print(f"History cache updated under {Path(output_dir) / 'cache' / 'history'}")
    print(f"Manifest: {manifest_path}")
    print(
        "Completed: "
        f"{summary.cached_years} cache hit, "
        f"{summary.refreshed_years} refreshed, "
        f"{summary.fetched_years} fetched, "
        f"{summary.failed_years} failed"
    )
    return 0 if summary.satisfied_years > 0 else 1


def _resolve_history(
    client: YahooFinanceClient,
    cache: HistoryCache,
    symbol: str,
    year: int,
) -> tuple[str, str, int, datetime | None]:
    today = client._today()
    is_current_year = year == today.year
    if cache.has_year(symbol, year):
        if not is_current_year:
            path = cache.year_path(symbol, year)
            last_timestamp = cache.latest_timestamp(symbol, year)
            return "cache_hit", str(path), len(cache.read_year(symbol, year)), last_timestamp

        latest = cache.latest_timestamp(symbol, year)
        if latest is not None and latest.date() >= today:
            path = cache.year_path(symbol, year)
            return "cache_hit", str(path), len(cache.read_year(symbol, year)), latest

        start_date = date(year, 1, 1) if latest is None else latest.date() + timedelta(days=1)
        end_date = today + timedelta(days=1)
        new_rows = client.fetch_history_year(symbol, year, start_date=start_date, end_date=end_date)
        if not new_rows:
            path = cache.year_path(symbol, year)
            last_timestamp = cache.latest_timestamp(symbol, year)
            return "cache_hit", str(path), len(cache.read_year(symbol, year)), last_timestamp
        path = cache.merge_year(symbol, year, new_rows)
        last_timestamp = cache.latest_timestamp(symbol, year)
        return "cache_refresh", path, len(cache.read_year(symbol, year)), last_timestamp

    rows = client.fetch_history_year(symbol, year)
    path = cache.write_year(symbol, year, rows)
    last_timestamp = cache.latest_timestamp(symbol, year)
    return "fetched", path, len(rows), last_timestamp


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_run_dir(output_dir: str) -> str:
    run_dir = Path(output_dir) / _utc_now().strftime("%Y-%m-%dT%H-%MZ")
    counter = 1
    while run_dir.exists():
        run_dir = Path(output_dir) / f"{_utc_now().strftime('%Y-%m-%dT%H-%MZ')}-{counter}"
        counter += 1
    run_dir.mkdir(parents=True, exist_ok=False)
    return str(run_dir)


if __name__ == "__main__":
    raise SystemExit(main())
