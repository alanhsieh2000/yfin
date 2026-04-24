# Bootstrap the package and prove a single-symbol quote plus yearly history normalization

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `/PLANS.md`.

## Purpose / Big Picture

The repository currently describes a Yahoo Finance downloader in `/README.md`, but there is no Python package, no CLI entrypoint, and no tests. After this plan is implemented, a newcomer will be able to install the dependencies, run one command for a single symbol such as `AAPL`, and see normalized quote data printed in the terminal. The same package will also be able to normalize one or more years of daily historical data, including dividend amounts on the dates they were distributed.

The proof is simple and observable. From `/workspace`, run the unit tests, then run `python -m yfinance_watchlist.cli quote AAPL`. The command should print the symbol, currency, latest market price, and a timestamp in a stable format. The tests should also prove that yearly history rows include a `dividend` field and that the history API uses calendar-year windows instead of free-form periods.

## Progress

- [x] (2026-04-24T09:05Z) Drafted the original bootstrap plan against the current repository state: `/src` and `/test` exist but are empty, `requirements.txt` already includes `numpy`, `pandas`, and `yfinance`, and `/PLANS.md` is present.
- [x] (2026-04-24T09:05Z) Revised the plan to require yearly history windows, dividend-aware normalized rows, and removal of free-form `period` and `interval` arguments.
- [x] (2026-04-24T09:17Z) Created the Python package in `/src/yfinance_watchlist/` with `models.py`, `client.py`, and `cli.py`.
- [x] (2026-04-24T09:17Z) Added `unittest` coverage in `/test` for quote normalization, yearly history normalization, and CLI output formatting.
- [x] (2026-04-24T09:18Z) Ran the tests and the `quote` command, then recorded the observed output in `Artifacts and Notes`.

## Surprises & Discoveries

- Observation: The repository already has empty `/src` and `/test` directories, so the implementation should build on that layout instead of inventing a different top-level structure.
  Evidence: Repository inspection on 2026-04-24 showed `/workspace/src` and `/workspace/test` with no files beneath them.

- Observation: The repository does not include packaging metadata such as `pyproject.toml`, so the first milestone should avoid packaging ceremony and rely on `PYTHONPATH=src` or direct module execution during development.
  Evidence: Repository inspection on 2026-04-24 found only `/README.md`, `/requirements.txt`, `/Dockerfile`, `/PLANS.md`, and `/AGENTS.md` at the root.

- Observation: The current year is inherently incomplete, so yearly history cannot be treated as equally final for all requested years.
  Evidence: A request for yearly history now requires the current year to cover January 1 through today, while past years still cover January 1 through December 31.

## Decision Log

- Decision: Make the first milestone CLI-first instead of library-only.
  Rationale: The README speaks in terms of downloading market data, so an observable command-line action is the shortest path to proving useful behavior.
  Date/Author: 2026-04-24 / Codex

- Decision: Use standard-library `unittest` instead of introducing `pytest`.
  Rationale: `/README.md` explicitly mentions `TestCase`, and adding a second test framework would create unnecessary setup work for an empty repository.
  Date/Author: 2026-04-24 / Codex

- Decision: Replace free-form history parameters with `start_year` and `end_year`.
  Rationale: The requested product behavior is yearly-only, daily-only history, so the API should encode that policy directly instead of accepting unsupported periods and intervals.
  Date/Author: 2026-04-24 / Codex

- Decision: Store dividends directly in each normalized historical row.
  Rationale: The user wants dividend data attached to the row for the matching `timestamp`, which makes later CSV writing and cache reuse straightforward.
  Date/Author: 2026-04-24 / Codex

## Outcomes & Retrospective

The intended outcome of this milestone is a narrow but real behavior: one command prints one normalized quote, while the client layer also proves it can normalize yearly historical rows with dividend values. If the milestone succeeds, the repository will have a package skeleton that later milestones can extend into watchlist processing, persistent yearly caching, and current-year refresh behavior.

Implementation completed on 2026-04-24. The repository now has the first working package surface under `/src/yfinance_watchlist/`, nine passing unit tests, and a live `quote` command that produced a real Yahoo Finance response for `AAPL`.

## Context and Orientation

This repository is a Python 3.12 project, as shown by `/Dockerfile`. Dependencies are listed in `/requirements.txt` and currently include `yfinance`, `pandas`, and `numpy`. `/README.md` states that the project should download stock and ETF market data from Yahoo Finance and that Python classes should live under `/src`, with `unittest.TestCase` tests under `/test`.

In this plan, a “normalized” quote means a small Python object whose fields use repository-owned names and Python-native types instead of the larger, loosely shaped dictionary returned by `yfinance`. A “normalized history row” means one daily record with repository-owned field names. The package created by this plan should live at `/src/yfinance_watchlist/`.

Yearly history now has fixed semantics. For a past year, the requested date window is January 1 through December 31 inclusive. For the current year, the effective window is January 1 through the current date. All history requests use daily data only, and each returned row must include a `dividend` value that is `0` when no distribution occurred on that date.

## Plan of Work

Start by creating `/src/yfinance_watchlist/__init__.py` so the directory is importable. Add `/src/yfinance_watchlist/models.py` and define three dataclasses: `WatchlistEntry`, `QuoteSnapshot`, and `PriceHistoryRow`. `WatchlistEntry` should support `symbol` and optional `label` so later milestones do not need to rename interfaces. `QuoteSnapshot` should hold `symbol`, `currency`, `market_price`, and `market_time`. `PriceHistoryRow` should hold `timestamp`, `open`, `high`, `low`, `close`, `volume`, and `dividend`.

Add `/src/yfinance_watchlist/client.py` and define `class YahooFinanceClient`. Implement `fetch_quote(symbol: str) -> QuoteSnapshot` by calling `yfinance.Ticker(symbol)` and reading a minimal, stable subset of quote fields. Convert the returned payload into `QuoteSnapshot`, raising `ValueError` with a clear message if required fields are missing.

In the same class, implement `fetch_history(symbol: str, start_year: int, end_year: int) -> list[PriceHistoryRow]`. This method should validate that `start_year <= end_year`, derive one or more yearly windows, fetch Yahoo Finance history at daily resolution only, and normalize each returned row into `PriceHistoryRow`. For past years, fetch January 1 through December 31. For the current year, fetch January 1 through the current date. Map a dividend column into the `dividend` field, defaulting to `0` when Yahoo Finance reports no dividend on that date.

Add `/src/yfinance_watchlist/cli.py` with `def main(argv: list[str] | None = None) -> int`. Use `argparse` from the standard library. Create a single subcommand, `quote`, that accepts one positional `symbol`. The command should instantiate `YahooFinanceClient`, call `fetch_quote`, print a four-line human-readable summary, and return exit code `0`. On expected failures such as unknown symbols or missing fields, print a concise message to standard error and return a non-zero exit code.

Create `/test/test_models.py`, `/test/test_client.py`, and `/test/test_cli.py`. The tests should not make live network calls. Patch `yfinance.Ticker` with `unittest.mock` so the tests control the response. In `test_client.py`, verify that `fetch_quote` maps a representative Yahoo Finance payload into `QuoteSnapshot`, that `fetch_history` constructs correct yearly windows for past years and the current year, and that dividend-bearing and non-dividend days both normalize correctly. In `test_cli.py`, patch the client layer so the CLI test focuses on argument parsing, output formatting, and exit codes.

## Concrete Steps

Run all commands from `/workspace`.

1. Install dependencies if they are not present:

    pip install -r requirements.txt

2. After creating the package files, run the test suite with the package on the import path:

    PYTHONPATH=src python -m unittest discover -s test -v

    Expected shape of success:

        test_fetch_quote_maps_required_fields ... ok
        test_fetch_history_uses_year_windows ... ok
        test_fetch_history_maps_dividends ... ok
        test_quote_command_prints_summary ... ok
        ...
        OK

3. Exercise the CLI manually:

    PYTHONPATH=src python -m yfinance_watchlist.cli quote AAPL

    Expected shape of success:

        Symbol: AAPL
        Currency: USD
        Market Price: 123.45
        Market Time: 2026-04-24T00:00:00+00:00

4. If history normalization fails because Yahoo Finance omits a field, rerun after adding the missing-field guard and make sure the failing test reports a repository-owned error message instead of a raw library exception.

## Validation and Acceptance

Acceptance for this plan is behavioral, not structural. A novice should be able to clone the repository, install the listed dependencies, run `PYTHONPATH=src python -m unittest discover -s test`, and see the new tests pass. Those tests must prove three things: yearly date-window construction for one year and multiple consecutive years, dividend normalization for a date with a distribution and a date without one, and stable quote normalization.

The same novice should then be able to run `PYTHONPATH=src python -m yfinance_watchlist.cli quote AAPL` and observe a readable summary with symbol, currency, price, and timestamp. The tests should fail before the package is created because the modules do not exist. After implementation, the tests should pass without requiring network access because they patch the `yfinance` boundary.

## Idempotence and Recovery

The file-creation steps are additive and safe to repeat. Re-running the tests should not modify repository-tracked files. If a test fails because `PYTHONPATH` was omitted, rerun the command with `PYTHONPATH=src`. If a live CLI smoke test fails because Yahoo Finance changes its payload, update the normalization code and the missing-field error message, then record the discovery in `Surprises & Discoveries`.

If current-year history tests depend on the current date, freeze the date in the test with a patched helper instead of relying on the machine clock. That keeps the acceptance stable over time.

## Artifacts and Notes

Record the first passing test run and the first successful CLI output here once implementation starts. Keep the snippets short and focused.

    $ PYTHONPATH=src python -m unittest discover -s test -v
    test_quote_command_prints_error (test_cli.CliTestCase.test_quote_command_prints_error) ... ok
    test_quote_command_prints_summary (test_cli.CliTestCase.test_quote_command_prints_summary) ... ok
    test_fetch_history_maps_dividends (test_client.YahooFinanceClientTestCase.test_fetch_history_maps_dividends) ... ok
    ...
    OK

    $ PYTHONPATH=src python -m yfinance_watchlist.cli quote AAPL
    Symbol: AAPL
    Currency: USD
    Market Price: 273.43
    Market Time: 2026-04-23T20:00:01+00:00

## Interfaces and Dependencies

Use only the dependencies already declared in `/requirements.txt` plus the Python standard library. Do not add new packages in this milestone.

At the end of the milestone, the following interfaces must exist:

- In `/src/yfinance_watchlist/models.py`, define `WatchlistEntry`, `QuoteSnapshot`, and `PriceHistoryRow` as dataclasses, with `PriceHistoryRow.dividend` present on every row.
- In `/src/yfinance_watchlist/client.py`, define:

    class YahooFinanceClient:
        def fetch_quote(self, symbol: str) -> QuoteSnapshot: ...
        def fetch_history(self, symbol: str, start_year: int, end_year: int) -> list[PriceHistoryRow]: ...

- In `/src/yfinance_watchlist/cli.py`, define:

    def main(argv: list[str] | None = None) -> int: ...

    if __name__ == "__main__":
        raise SystemExit(main())

The CLI should use the client interface instead of calling `yfinance` directly. That separation matters because later milestones will add watchlist parsing, yearly cache reuse, and current-year refresh behavior around the same client.

Revision note: Revised on 2026-04-24 to replace free-form history fetching with yearly windows and to require dividend-aware normalized history rows.
