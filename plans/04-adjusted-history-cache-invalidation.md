# Adjust history prices and invalidate stale symbol caches

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document follows `/workspace/PLANS.md`, which defines how ExecPlans in this repository must be written and maintained.

## Purpose / Big Picture

The downloader currently stores raw open, high, low, and close values from Yahoo Finance history. That makes any later return calculation wrong after dividends or stock splits, because older prices are not adjusted to the current share basis. After this change, cached yearly CSV files will contain adjusted OHLC values, and a fetch run will rewrite every cached year for a symbol when a newly observed dividend or split means the older adjusted history is stale.

The behavior is visible in two ways. First, unit tests will prove that history requests now use `auto_adjust=True`. Second, a fetch run with an existing cache and a newly observed dividend in the current year will report `cache_refresh` for all cached requested years of that symbol instead of reusing stale past-year files.

## Progress

- [x] (2026-04-25 00:00Z) Inspected `src/yfinance_watchlist/client.py`, `src/yfinance_watchlist/cli.py`, `src/yfinance_watchlist/cache.py`, and the affected tests to map the existing append-only current-year refresh behavior.
- [x] (2026-04-25 00:00Z) Updated history fetching to request auto-adjusted prices, extended the cache index with adjustment timestamps, and replaced the symbol-year append logic with symbol-level refresh decisions.
- [x] (2026-04-25 00:00Z) Ran `PYTHONPATH=src python -m unittest discover -s test` from `/workspace`; all 48 tests passed.
- [x] (2026-04-25 00:00Z) Recorded the verified outcome and final notes in this plan.

## Surprises & Discoveries

- Observation: The stale-cache bug is larger than the current-year append path. A newly observed dividend in the current year also invalidates cached past years even when the command only requested past years.
  Evidence: `src/yfinance_watchlist/cli.py` previously treated past years as unconditional `cache_hit` whenever a file existed, and only refreshed the current year by appending rows after the latest cached timestamp.

## Decision Log

- Decision: Refresh logic is now symbol-level instead of year-level.
  Rationale: A dividend or stock split changes adjusted prices for earlier dates across the full symbol history, so the decision to reuse cache cannot be made independently per year.
  Date/Author: 2026-04-25 / Codex

- Decision: Store `latest_adjustment_timestamp` in the cache index for each year and derive the symbol-wide maximum from those entries.
  Rationale: The refresh decision only needs to know whether the latest observed dividend or split is newer than what the cache has already seen. This avoids a separate metadata file and keeps the existing cache layout intact.
  Date/Author: 2026-04-25 / Codex

## Outcomes & Retrospective

Implementation is complete and verified. The downloader now stores auto-adjusted OHLC values, and the fetch flow no longer treats yearly cache files as independently reusable when a symbol has a newly observed dividend or split. The test suite passed with 48 tests, which covers the adjusted request flag, the new cache metadata, and the regression case where a current-year dividend forces older cached years to refresh.

## Context and Orientation

The user-facing fetch flow starts in `src/yfinance_watchlist/cli.py`. `run_fetch_command` loads the watchlist, fetches quotes, and writes one manifest entry per requested symbol-year. The yearly cache lives in `src/yfinance_watchlist/cache.py`, where `HistoryCache` writes `data/cache/history/<symbol>/<year>.csv` and maintains `data/cache/history_index.json`. Yahoo Finance access is wrapped in `src/yfinance_watchlist/client.py`; this file owns the request parameters passed to `yfinance.Ticker.history()` and normalizes each returned row into the repository-owned `PriceHistoryRow` dataclass from `src/yfinance_watchlist/models.py`.

In this repository, a "cache refresh" means rewriting an existing yearly CSV file instead of reusing it unchanged. A "corporate action" means either a dividend distribution or a stock split, which Yahoo Finance exposes through the `Dividends` and `Stock Splits` columns in the history frame. When `auto_adjust=True`, Yahoo Finance rewrites older OHLC values to account for those actions, so a newly observed action means earlier cached rows are no longer correct.

## Plan of Work

First, update `src/yfinance_watchlist/client.py` so the history reader calls `ticker.history(..., actions=True, auto_adjust=True)`. Keep the existing normalization path because the required columns stay the same and the repository still needs dividend and split values on each row.

Next, extend `src/yfinance_watchlist/cache.py` so each cached year records the latest row timestamp that carries a non-zero dividend or split. Add helper methods that return the latest adjustment timestamp seen for a symbol and the list of cached years for that symbol. These helpers let the CLI decide whether a symbol-wide refresh is required without changing the cache file layout.

Then, restructure `src/yfinance_watchlist/cli.py`. Replace the append-only `_resolve_history` function with a symbol-level resolver that can do three things: read a fresh current-year history snapshot when any cache exists for the symbol, compare the newest observed dividend or split against the cache metadata, and if a newer action exists, rewrite every cached requested year for that symbol. If there is no new action, keep past cached years as `cache_hit`, and treat the current year as `cache_hit` or `cache_refresh` based on a full-row comparison between the cached file and the fresh current-year fetch.

Finally, update tests in `test/test_client.py`, `test/test_cache.py`, and `test/test_cli.py` to pin the new behavior. The client tests must assert that `auto_adjust=True` is passed to Yahoo Finance. The cache tests must prove that the index tracks the latest dividend or split date per symbol. The CLI tests must cover the regression case where an existing multi-year cache receives a new current-year dividend and every requested cached year becomes `cache_refresh`.

## Concrete Steps

From `/workspace`, edit the following files:

1. `src/yfinance_watchlist/client.py`
   Change the history request to `auto_adjust=True`.

2. `src/yfinance_watchlist/cache.py`
   Add `latest_adjustment_timestamp(symbol)` and `years_for_symbol(symbol)`, and persist `latest_adjustment_timestamp` into the cache index during `write_year`.

3. `src/yfinance_watchlist/cli.py`
   Replace year-local cache resolution with a symbol-level flow that can refresh all cached requested years after a newly observed dividend or split.

4. `test/test_client.py`
   Assert that history fetches request adjusted data.

5. `test/test_cache.py`
   Assert that cache metadata tracks the latest dividend or split date for a symbol.

6. `test/test_cli.py`
   Add a regression test where a new current-year dividend forces both the current year and an older cached year to refresh.

7. `README.md`
   Update the cache semantics section so it matches the new adjusted-history behavior.

Then run:

    cd /workspace
    PYTHONPATH=src python -m unittest discover -s test

Expected result after implementation:

    ................................................
    ----------------------------------------------------------------------
    Ran 48 tests in 0.075s

    OK

## Validation and Acceptance

Acceptance is behavioral. Run `PYTHONPATH=src python -m unittest discover -s test` from `/workspace` and expect the suite to pass. The important new proof points are:

- `test_fetch_history_uses_year_windows_for_past_years` now proves that Yahoo Finance history requests include `auto_adjust=True`.
- `test_latest_adjustment_timestamp_tracks_latest_dividend_or_split_for_symbol` proves the cache index records the most recent corporate action date for a symbol.
- `test_fetch_command_refreshes_all_cached_years_after_new_dividend` proves that when a new current-year dividend is observed, previously cached requested years for that symbol are rewritten and reported as `cache_refresh`.

## Idempotence and Recovery

The code edits are idempotent because rerunning the same patch leaves the repository in the same state. The test suite is safe to rerun repeatedly. If the implementation fails midway, the safe recovery path is to rerun the failing tests, inspect the affected file, and continue from this plan because all required paths and expected behaviors are described here. Existing cache files under `data/cache` are test fixtures for local inspection only and do not need manual migration because the code rewrites cached years as needed.

## Artifacts and Notes

Important observable manifest behavior after this change:

    "source": "cache_refresh"

This result now means either the current-year rows changed or a new dividend/split required rewriting older cached years for the same symbol.

## Interfaces and Dependencies

The implementation keeps the existing public interfaces intact:

- `yfinance_watchlist.client.YahooFinanceClient.fetch_history(symbol, start_year, end_year) -> list[PriceHistoryRow]`
- `yfinance_watchlist.client.YahooFinanceClient.fetch_history_year(symbol, year, start_date=None, end_date=None) -> list[PriceHistoryRow]`
- `yfinance_watchlist.cache.HistoryCache.write_year(symbol, year, rows) -> str`

The new cache helpers that must exist at the end of the work are:

    def latest_adjustment_timestamp(self, symbol: str) -> datetime | None: ...
    def years_for_symbol(self, symbol: str) -> list[int]: ...

Revision note: Created on 2026-04-25 to fix inaccurate unadjusted OHLC history and stale cache reuse after dividends or stock splits.

Revision note: Updated on 2026-04-25 after implementation to record the passing 48-test validation run and the final verified behavior.
