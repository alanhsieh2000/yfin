# Add watchlist-driven batch download, yearly history storage, and cache reuse

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `/PLANS.md`.

## Purpose / Big Picture

The bootstrap milestone proves that one symbol can be fetched, but the README goal is broader: download market data for stocks and ETFs in a watchlist. After this plan is implemented, a newcomer will be able to place a CSV file in the repository, run one CLI command, and receive a dated output directory containing normalized quotes plus a persistent cache of yearly historical CSV files. If the same symbol and past year are requested again later, the tool should reuse the cached history instead of fetching duplicate data from Yahoo Finance.

The visible success case is a batch command such as `python -m yfinance_watchlist.cli fetch --watchlist watchlist.csv --output data --start-year 2024 --end-year 2026`. The command should create `data/<run-date>/quotes.csv`, populate or reuse `data/cache/history/<symbol>/<year>.csv`, update `data/cache/history_index.json`, and write a `manifest.json` file that records which years were fetched, reused from cache, or refreshed for the current year.

## Progress

- [x] (2026-04-24T09:05Z) Drafted the original batch-download plan with a CLI-first direction and a CSV watchlist format.
- [x] (2026-04-24T09:05Z) Revised the plan to require yearly history ranges, symbol-year cache reuse, and current-year suffix refresh behavior.
- [x] (2026-04-24T12:33Z) Extended the package with watchlist parsing, cache management, and file-writing modules.
- [x] (2026-04-24T12:33Z) Added the `fetch` CLI command and connected it to the existing `YahooFinanceClient`.
- [x] (2026-04-24T12:33Z) Added unit and end-to-end style tests for watchlist parsing, duplicate handling, cache hits, and current-year refresh behavior.
- [x] (2026-04-24T12:34Z) Ran the batch command with a sample watchlist and recorded the resulting directory tree and file excerpts.

## Surprises & Discoveries

- Observation: The repository does not define a watchlist format in `/README.md`, so the plan must choose one explicitly instead of leaving that decision to the implementer.
  Evidence: `/README.md` names a watchlist but does not describe file shape, headers, or file extension.

- Observation: The repository still lacks packaging metadata, so the commands in this plan should continue to rely on `PYTHONPATH=src` for direct module execution.
  Evidence: Repository inspection on 2026-04-24 found no `pyproject.toml`, `setup.cfg`, or `setup.py`.

- Observation: Cached data for the current year can become stale during later runs, unlike cached data for past years.
  Evidence: The new product requirement states that more current-year data may become available after an earlier cache hit and must be fetched and stored.

## Decision Log

- Decision: Standardize the first watchlist format as CSV with a required `symbol` column and an optional `label` column.
  Rationale: CSV is easy for newcomers to create, inspect, and version-control without adding parser dependencies.
  Date/Author: 2026-04-24 / Codex

- Decision: Use `(symbol, year)` as the cache key for historical data.
  Rationale: The requested history API is yearly-only, so cache storage and deduplication should be aligned to the same unit.
  Date/Author: 2026-04-24 / Codex

- Decision: Treat past years as immutable cache hits, but treat the current year as refreshable.
  Rationale: Past years have fixed end dates, while the current year may gain new rows after a previous run.
  Date/Author: 2026-04-24 / Codex

## Outcomes & Retrospective

This milestone should convert the prototype into the first useful operator workflow. If it succeeds, a user can hand the tool a list of symbols and a year range, receive structured output on disk, and avoid duplicate history fetches for already cached past years. Remaining work after this milestone is expected to focus on richer manifest reporting, partial-failure handling, and README guidance rather than on basic capability.

Implementation completed on 2026-04-24. The repository now supports CSV watchlists, run-specific quote output, persistent symbol-year cache files, and reruns that convert past-year requests into `cache_hit` results while refreshing the current year when newer data may exist.

## Context and Orientation

This plan builds on the package introduced by the bootstrap milestone. The existing client should already know how to normalize one quote and one or more years of daily history rows, including dividend values. The missing capabilities are reading many symbols from a watchlist file, storing yearly histories durably, consulting that local store before making a network call, and refreshing only the missing suffix for the current year.

In this plan, a “history cache” means persistent on-disk yearly CSV files plus a small JSON index that records what has already been fetched. A “cache hit” means the requested symbol-year already exists locally and can be reused without a new Yahoo Finance call. A “current-year refresh” means the requested symbol-year is the current year, local data already exists, and the tool fetches only the missing later rows between the last cached date and today.

The implementation should stay inside `/src/yfinance_watchlist/` and `/test/`. Do not introduce a top-level `scripts/` directory for core logic; keep the behavior importable and testable through the package.

## Plan of Work

Add `/src/yfinance_watchlist/watchlist.py` and define `class WatchlistReader` with `load(path: str) -> list[WatchlistEntry]`. Parse CSV using the standard library `csv` module. Require a header row with `symbol`, and allow an optional `label` column. Trim whitespace, ignore blank rows, and treat duplicate symbols as a single logical entry by preserving the first occurrence and skipping later duplicates. If the file is missing the `symbol` header or contains no usable rows, raise `ValueError` with a clear message.

Add `/src/yfinance_watchlist/cache.py` and define a repository-owned `HistoryCache` component. It should read and write `data/cache/history_index.json`, manage `data/cache/history/<symbol>/<year>.csv`, and expose methods to check whether a symbol-year is cached, read cached rows, write a new year file, and merge new rows into an existing current-year file without duplicating timestamps. The cache index should record at least the symbol, year, file path, and latest cached `timestamp` so the current-year refresh logic can decide whether additional rows may be needed.

Add or extend `/src/yfinance_watchlist/store.py` so it handles run-specific outputs such as `quotes.csv` and `manifest.json`, while the yearly history cache is handled through `HistoryCache`. Keep quote output in `data/<run-date>/quotes.csv`. Keep cached yearly histories in `data/cache/history/<symbol>/<year>.csv`.

Extend `/src/yfinance_watchlist/client.py` with a helper that can fetch a single year or suffix of a year at daily resolution, for example `fetch_history_year(symbol: str, year: int, start_date: date | None = None, end_date: date | None = None) -> list[PriceHistoryRow]`. Use that helper inside `fetch_history(symbol: str, start_year: int, end_year: int)` so the current-year refresh path can fetch only missing rows instead of refetching the entire year.

Extend `/src/yfinance_watchlist/cli.py` with a new subcommand `fetch`. The command should accept `--watchlist`, `--output`, `--start-year`, and `--end-year` as required arguments. It should create a run directory named with the UTC date and time, load the deduplicated watchlist, fetch quotes for each symbol, and then process each requested year. For past years, reuse the cached file if present. For the current year, inspect the latest cached date; if newer dates could exist through today, fetch only the missing suffix, merge it into the cached CSV, and mark the year as refreshed. If a symbol-year is missing entirely, fetch it from Yahoo Finance and write a new year file.

Add tests in `/test/test_watchlist.py`, `/test/test_cache.py`, `/test/test_store.py`, and extend `/test/test_cli.py`. The watchlist tests should cover a valid file, a file with blank rows, a file with duplicate symbols, and a file missing the `symbol` header. The cache tests should verify cache hits for past years, no duplicate fetch for repeated past-year requests, merge behavior for current-year suffix refresh, and stable handling of duplicate timestamps. The CLI tests should patch the client and cache layers so the command can be exercised without live network calls.

## Concrete Steps

Run all commands from `/workspace`.

1. Prepare a sample watchlist after implementing the reader:

    printf 'symbol,label\nAAPL,Apple\nSPY,S&P 500 ETF\n' > watchlist.csv

2. Run the full test suite:

    PYTHONPATH=src python -m unittest discover -s test -v

    Expected shape of success:

        test_load_watchlist_skips_duplicates ... ok
        test_cache_hit_skips_refetch_for_past_year ... ok
        test_current_year_refresh_merges_new_rows ... ok
        test_fetch_command_updates_manifest ... ok
        ...
        OK

3. Run the batch command:

    PYTHONPATH=src python -m yfinance_watchlist.cli fetch --watchlist watchlist.csv --output data --start-year 2025 --end-year 2026

    Expected shape of success:

        Loaded 2 symbols from watchlist.csv
        Wrote outputs to data/2026-04-24T09-05Z
        History cache updated under data/cache/history
        Completed: 4 symbol-years satisfied

4. Inspect the created files:

    find data -maxdepth 4 -type f | sort

    Expected shape of success:

        data/2026-04-24T09-05Z/manifest.json
        data/2026-04-24T09-05Z/quotes.csv
        data/cache/history/AAPL/2025.csv
        data/cache/history/AAPL/2026.csv
        data/cache/history/SPY/2025.csv
        data/cache/history/SPY/2026.csv
        data/cache/history_index.json

5. Re-run the same command and verify that past years are reused and the current year is either refreshed or treated as already current:

    PYTHONPATH=src python -m yfinance_watchlist.cli fetch --watchlist watchlist.csv --output data --start-year 2025 --end-year 2026

## Validation and Acceptance

Acceptance for this milestone is that a newcomer can create a two-line CSV watchlist, run one CLI command, and inspect durable outputs on disk. Passing tests alone are not enough; the implementation must also demonstrate the real cache layout and file names described above.

Before implementation, the `fetch` command should not exist and the watchlist reader, cache, and store modules should be absent. After implementation, `PYTHONPATH=src python -m unittest discover -s test` should pass, and the batch command should produce a quote file, a manifest, and one yearly history CSV per requested symbol-year. A second identical run should show no duplicate fetches for already cached past years. If the requested range includes the current year, the second run should refresh only the missing suffix when newer dates are available and otherwise leave the current-year file unchanged.

## Idempotence and Recovery

This plan is safe to run repeatedly because each CLI invocation writes run-specific summary outputs into a new dated run directory, while the cache layer updates only symbol-year files and the shared index. When merging current-year rows into an existing CSV, deduplicate by `timestamp` so repeated refreshes do not append duplicates. If a cache write fails unexpectedly, leave the previously committed year file untouched and write the replacement through a temporary file before renaming it into place.

If the watchlist file is malformed, the command should exit before creating partial run outputs and print a readable error to standard error. If a current-year refresh fails after a cache hit has already been found, preserve the existing cached file and record the refresh failure in the run manifest instead of deleting working data.

## Artifacts and Notes

Record the first successful end-to-end run here once the implementation exists. Include a short tree listing and short excerpts from `quotes.csv`, `history_index.json`, and one yearly history CSV that shows a `dividend` column.

    $ find /tmp/yfplan2/data -maxdepth 4 -type f | sort
    /tmp/yfplan2/data/2026-04-24T12-34Z/manifest.json
    /tmp/yfplan2/data/2026-04-24T12-34Z/quotes.csv
    /tmp/yfplan2/data/cache/history/AAPL/2025.csv
    /tmp/yfplan2/data/cache/history/AAPL/2026.csv
    /tmp/yfplan2/data/cache/history/SPY/2025.csv
    /tmp/yfplan2/data/cache/history/SPY/2026.csv
    /tmp/yfplan2/data/cache/history_index.json

    $ sed -n '1,3p' /tmp/yfplan2/data/2026-04-24T12-34Z/quotes.csv
    symbol,label,currency,market_price,market_time
    AAPL,Apple,USD,273.43,2026-04-23T20:00:01+00:00
    SPY,S&P 500 ETF,USD,708.45,2026-04-23T20:00:00+00:00

    $ sed -n '1,4p' /tmp/yfplan2/data/cache/history/AAPL/2026.csv
    timestamp,open,high,low,close,volume,dividend
    2026-01-02T05:00:00+00:00,272.260009765625,277.8399963378906,269.0,271.010009765625,37838100,0.0
    2026-01-05T05:00:00+00:00,270.6400146484375,271.510009765625,266.1400146484375,267.260009765625,45647200,0.0

    $ sed -n '1,20p' /tmp/yfplan2/data/2026-04-24T12-34Z-1/manifest.json
    {
      "years": [
        {"symbol": "AAPL", "year": 2025, "source": "cache_hit", ...},
        {"symbol": "AAPL", "year": 2026, "source": "cache_refresh", ...}
      ]
    }

## Interfaces and Dependencies

Use the existing `YahooFinanceClient` from the bootstrap milestone. Continue to use only dependencies already listed in `/requirements.txt` and the Python standard library.

At the end of the milestone, the following interfaces must exist:

- In `/src/yfinance_watchlist/watchlist.py`, define:

    class WatchlistReader:
        def load(self, path: str) -> list[WatchlistEntry]: ...

- In `/src/yfinance_watchlist/cache.py`, define a repository-owned cache component with methods equivalent to:

    class HistoryCache:
        def has_year(self, symbol: str, year: int) -> bool: ...
        def read_year(self, symbol: str, year: int) -> list[PriceHistoryRow]: ...
        def latest_timestamp(self, symbol: str, year: int) -> datetime | None: ...
        def write_year(self, symbol: str, year: int, rows: list[PriceHistoryRow]) -> str: ...
        def merge_year(self, symbol: str, year: int, rows: list[PriceHistoryRow]) -> str: ...

- In `/src/yfinance_watchlist/client.py`, define or extend:

    class YahooFinanceClient:
        def fetch_quote(self, symbol: str) -> QuoteSnapshot: ...
        def fetch_history(self, symbol: str, start_year: int, end_year: int) -> list[PriceHistoryRow]: ...
        def fetch_history_year(self, symbol: str, year: int, start_date=None, end_date=None) -> list[PriceHistoryRow]: ...

- In `/src/yfinance_watchlist/store.py`, define or extend:

    class FileStore:
        def write_quotes(self, run_dir: str, quotes: list[QuoteSnapshot], entries: list[WatchlistEntry]) -> str: ...
        def write_manifest(self, run_dir: str, manifest: dict) -> str: ...

- In `/src/yfinance_watchlist/cli.py`, extend `main` to support:

    python -m yfinance_watchlist.cli fetch --watchlist <path> --output <dir> --start-year <year> --end-year <year>

The command output should state the resolved run directory and whether the cache was reused, refreshed, or populated so the user can navigate and understand the result without reading code.

Revision note: Revised on 2026-04-24 to replace free-form history output with persistent symbol-year cache reuse and current-year suffix refresh behavior.
