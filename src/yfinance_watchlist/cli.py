from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import sys

from .cache import HistoryCache
from .client import YahooFinanceClient
from .models import PriceHistoryRow
from .results import FetchRunSummary, SymbolYearResult
from .store import FileStore
from .watchlist import WatchlistReader, WatchlistStore


DEFAULT_WATCHLIST_PATH = "watchlist.csv"
DEFAULT_KEEP_RUNS = 10
_RUN_DIR_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}Z)(?:-(\d+))?$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yfinance_watchlist")
    subparsers = parser.add_subparsers(dest="command", required=True)

    quote_parser = subparsers.add_parser("quote", help="Fetch and print a single quote")
    quote_parser.add_argument("symbol")

    show_parser = subparsers.add_parser("show", help="Show the current watchlist")
    show_parser.add_argument("--watchlist", default=DEFAULT_WATCHLIST_PATH)

    add_parser = subparsers.add_parser("add", help="Add or update a symbol in the watchlist")
    add_parser.add_argument("symbol")
    add_parser.add_argument("label", nargs="?")
    add_parser.add_argument("--watchlist", default=DEFAULT_WATCHLIST_PATH)

    remove_parser = subparsers.add_parser("remove", help="Remove a symbol from the watchlist")
    remove_parser.add_argument("symbol")
    remove_parser.add_argument("--watchlist", default=DEFAULT_WATCHLIST_PATH)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch quotes and yearly history for a watchlist")
    fetch_parser.add_argument("--watchlist", default=DEFAULT_WATCHLIST_PATH)
    fetch_parser.add_argument("--output", required=True)
    fetch_parser.add_argument("--start-year", type=int, required=True)
    fetch_parser.add_argument("--end-year", type=int, required=True)
    fetch_parser.add_argument("--fail-fast", action="store_true")
    fetch_parser.add_argument("--keep-runs", type=int, default=DEFAULT_KEEP_RUNS)

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

    if args.command == "show":
        return run_show_command(args.watchlist)

    if args.command == "add":
        return run_add_command(args.watchlist, args.symbol, args.label)

    if args.command == "remove":
        return run_remove_command(args.watchlist, args.symbol)

    if args.command == "fetch":
        return run_fetch_command(
            args.watchlist,
            args.output,
            args.start_year,
            args.end_year,
            fail_fast=args.fail_fast,
            keep_runs=args.keep_runs,
        )

    parser.error(f"unsupported command: {args.command}")
    return 2


def run_show_command(watchlist_path: str) -> int:
    store = WatchlistStore()
    try:
        entries = store.load_entries(watchlist_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Watchlist: {watchlist_path}")
    if not entries:
        print("No symbols configured.")
        return 0

    for entry in entries:
        if entry.label:
            print(f"{entry.symbol},{entry.label}")
        else:
            print(entry.symbol)
    return 0


def run_add_command(watchlist_path: str, symbol: str, label: str | None) -> int:
    store = WatchlistStore()
    try:
        entry = store.add_entry(watchlist_path, symbol, label)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if entry.label:
        print(f"Saved {entry.symbol},{entry.label} to {watchlist_path}")
    else:
        print(f"Saved {entry.symbol} to {watchlist_path}")
    return 0


def run_remove_command(watchlist_path: str, symbol: str) -> int:
    store = WatchlistStore()
    try:
        entry = store.remove_entry(watchlist_path, symbol)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if entry.label:
        print(f"Removed {entry.symbol},{entry.label} from {watchlist_path}")
    else:
        print(f"Removed {entry.symbol} from {watchlist_path}")
    return 0


def run_fetch_command(
    watchlist_path: str,
    output_dir: str,
    start_year: int,
    end_year: int,
    fail_fast: bool = False,
    keep_runs: int = DEFAULT_KEEP_RUNS,
) -> int:
    if start_year > end_year:
        print("Error: start_year must be less than or equal to end_year", file=sys.stderr)
        return 1
    if keep_runs < 1:
        print("Error: keep_runs must be greater than or equal to 1", file=sys.stderr)
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

        if quote_error is not None:
            for year in range(start_year, end_year + 1):
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
            if stop_processing:
                break
            continue

        results = _resolve_symbol_history(client, cache, entry.symbol, start_year, end_year)
        for result in results:
            if result.error is not None:
                print(f"Error: {result.error}", file=sys.stderr)
            result.label = entry.label
            summary.add_result(result)
            if fail_fast:
                if result.source == "failed":
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
        "keep_runs": keep_runs,
        **summary.to_manifest_dict(),
    }
    manifest_path = store.write_manifest(run_dir, manifest)
    _prune_run_dirs(output_dir, keep_runs)

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


def _resolve_symbol_history(
    client: YahooFinanceClient,
    cache: HistoryCache,
    symbol: str,
    start_year: int,
    end_year: int,
) -> list[SymbolYearResult]:
    today = client._today()
    current_year = today.year
    cached_years = cache.years_for_symbol(symbol)
    symbol_has_cache = bool(cached_years)
    current_year_rows: list[PriceHistoryRow] | None = None
    refresh_cached_years = False
    refresh_check_error: str | None = None
    refreshed_rows_by_year: dict[int, list[PriceHistoryRow]] = {}
    refresh_errors_by_year: dict[int, str] = {}

    if symbol_has_cache:
        try:
            current_year_rows = client.fetch_history_year(symbol, current_year)
        except ValueError as exc:
            refresh_check_error = str(exc)
        else:
            cached_adjustment = cache.latest_adjustment_timestamp(symbol)
            latest_adjustment = _latest_adjustment_timestamp(current_year_rows)
            refresh_cached_years = (
                latest_adjustment is not None
                and (cached_adjustment is None or latest_adjustment > cached_adjustment)
            )

    if refresh_cached_years:
        for year in cached_years:
            try:
                rows = (
                    current_year_rows
                    if year == current_year and current_year_rows is not None
                    else client.fetch_history_year(symbol, year)
                )
            except ValueError as exc:
                refresh_errors_by_year[year] = str(exc)
                continue
            cache.write_year(symbol, year, rows)
            refreshed_rows_by_year[year] = rows

    results: list[SymbolYearResult] = []
    for year in range(start_year, end_year + 1):
        if year in refresh_errors_by_year:
            results.append(
                SymbolYearResult(
                    symbol=symbol,
                    label=None,
                    year=year,
                    status="failed",
                    source="failed",
                    error=refresh_errors_by_year[year],
                )
            )
            continue

        if year in refreshed_rows_by_year:
            rows = refreshed_rows_by_year[year]
            results.append(
                SymbolYearResult(
                    symbol=symbol,
                    label=None,
                    year=year,
                    status="success",
                    source="cache_refresh",
                    path=str(cache.year_path(symbol, year)),
                    row_count=len(rows),
                    last_timestamp=rows[-1].timestamp if rows else None,
                )
            )
            continue

        if refresh_check_error is not None and cache.has_year(symbol, year):
            results.append(
                SymbolYearResult(
                    symbol=symbol,
                    label=None,
                    year=year,
                    status="failed",
                    source="failed",
                    error=refresh_check_error,
                )
            )
            continue

        try:
            rows, source = _resolve_year_history(
                client=client,
                cache=cache,
                symbol=symbol,
                year=year,
                current_year=current_year,
                current_year_rows=current_year_rows,
                refresh_cached_years=refresh_cached_years,
            )
        except ValueError as exc:
            results.append(
                SymbolYearResult(
                    symbol=symbol,
                    label=None,
                    year=year,
                    status="failed",
                    source="failed",
                    error=str(exc),
                )
            )
            continue

        path = cache.year_path(symbol, year)
        last_timestamp = rows[-1].timestamp if rows else None
        results.append(
            SymbolYearResult(
                symbol=symbol,
                label=None,
                year=year,
                status="success",
                source=source,
                path=str(path),
                row_count=len(rows),
                last_timestamp=last_timestamp,
            )
        )
    return results


def _resolve_year_history(
    *,
    client: YahooFinanceClient,
    cache: HistoryCache,
    symbol: str,
    year: int,
    current_year: int,
    current_year_rows: list[PriceHistoryRow] | None,
    refresh_cached_years: bool,
) -> tuple[list[PriceHistoryRow], str]:
    is_current_year = year == current_year
    has_cached_year = cache.has_year(symbol, year)

    if refresh_cached_years and has_cached_year:
        rows = current_year_rows if is_current_year and current_year_rows is not None else client.fetch_history_year(symbol, year)
        cache.write_year(symbol, year, rows)
        return rows, "cache_refresh"

    if has_cached_year and not is_current_year:
        return cache.read_year(symbol, year), "cache_hit"

    if is_current_year:
        rows = current_year_rows if current_year_rows is not None else client.fetch_history_year(symbol, year)
        if not has_cached_year:
            cache.write_year(symbol, year, rows)
            return rows, "fetched"

        cached_rows = cache.read_year(symbol, year)
        if cached_rows == rows:
            return cached_rows, "cache_hit"

        cache.write_year(symbol, year, rows)
        return rows, "cache_refresh"

    rows = client.fetch_history_year(symbol, year)
    cache.write_year(symbol, year, rows)
    return rows, "fetched"


def _latest_adjustment_timestamp(rows: list[PriceHistoryRow]) -> datetime | None:
    timestamps = [row.timestamp for row in rows if row.dividend != 0 or row.stock_splits != 0]
    return max(timestamps, default=None)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_run_dir(output_dir: str) -> str:
    stamp = _utc_now().strftime("%Y-%m-%dT%H-%MZ")
    run_dir = Path(output_dir) / stamp
    counter = 1
    while run_dir.exists():
        run_dir = Path(output_dir) / f"{stamp}-{counter}"
        counter += 1
    run_dir.mkdir(parents=True, exist_ok=False)
    return str(run_dir)


def _prune_run_dirs(output_dir: str, keep_runs: int) -> None:
    run_dirs = sorted(_list_run_dirs(output_dir), key=_run_dir_sort_key, reverse=True)
    for path in run_dirs[keep_runs:]:
        shutil.rmtree(path)


def _list_run_dirs(output_dir: str) -> list[Path]:
    root = Path(output_dir)
    if not root.exists():
        return []
    return [path for path in root.iterdir() if path.is_dir() and _RUN_DIR_PATTERN.fullmatch(path.name)]


def _run_dir_sort_key(path: Path) -> tuple[datetime, int]:
    match = _RUN_DIR_PATTERN.fullmatch(path.name)
    if match is None:
        raise ValueError(f"invalid run directory name: {path.name}")
    stamp, suffix = match.groups()
    return datetime.strptime(stamp, "%Y-%m-%dT%H-%MZ"), int(suffix or 0)


if __name__ == "__main__":
    raise SystemExit(main())
