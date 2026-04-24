# Harden the workflow for repeatable local use, cache-aware manifests, and current-year refreshes

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `/PLANS.md`.

## Purpose / Big Picture

The first two milestones establish a working package and a useful batch workflow, but a tool that downloads market data is only practical if it behaves predictably when data is incomplete, one symbol-year fails, or the same command is rerun. After this plan is implemented, a newcomer will be able to run the fetch command against a mixed-quality watchlist and understand exactly which years were served from cache, which were refreshed for the current year, which were newly fetched, and which failed.

The observable outcome is a resilient fetch command. When one symbol-year succeeds and another fails, the command should still write the successful outputs, write a `manifest.json` that records year-level status, and print a summary showing the counts. The command should return a non-zero exit code only when no requested symbol-year was satisfied. The README should then explain the setup and operator workflow end to end, including why the current year may refresh on later runs.

## Progress

- [x] (2026-04-24T09:05Z) Drafted the original hardening plan, including defaults for partial failures, reruns, and operator-facing documentation.
- [x] (2026-04-24T09:05Z) Revised the plan to track year-level results, cache hits, current-year refreshes, and dividend-aware historical outputs.
- [x] (2026-04-24T13:00Z) Added year-level status tracking and a run summary type to the package.
- [x] (2026-04-24T13:00Z) Extended the CLI with failure policy flags and clearer completion summaries.
- [x] (2026-04-24T13:01Z) Added tests for mixed cache hits, refreshes, fresh fetches, all-failure runs, and reruns into the same output base directory.
- [x] (2026-04-24T13:02Z) Updated `/README.md` so a newcomer can set up the project and run the full workflow without reading the plans.

## Surprises & Discoveries

- Observation: Yahoo Finance payloads are not guaranteed to contain the same fields for every symbol and fund type, so the client layer must define which fields are required and how missing data is reported.
  Evidence: The repository references `yfinance`, whose responses are known to be dictionary-like and field-variable across instruments; this risk exists even before implementation.

- Observation: The repository goal includes both stocks and ETFs, which increases the chance of mixed data quality and partial fetch failures.
  Evidence: `/README.md` explicitly names “stocks and ETFs in the watchlist.”

- Observation: A current-year cache hit is not a terminal outcome until the cached latest date has been compared with today.
  Evidence: The current-year refresh requirement means a local file may exist but still need newer rows appended.

## Decision Log

- Decision: Continue the batch when one symbol-year fails, record the failure in `manifest.json`, and return non-zero only if no requested symbol-year succeeded, was reused, or was refreshed.
  Rationale: This preserves useful data from successful years while still signaling catastrophic runs to automation.
  Date/Author: 2026-04-24 / Codex

- Decision: Add a `--fail-fast` flag that stops on the first symbol-year failure, but keep it disabled by default.
  Rationale: Manual operators usually want partial results, while debugging sessions may prefer immediate stop behavior.
  Date/Author: 2026-04-24 / Codex

- Decision: Distinguish `cache_hit`, `cache_refresh`, and `fetched` in manifests and summaries.
  Rationale: Operators need to know whether a run used prior data unchanged, extended current-year data, or downloaded a new year from Yahoo Finance.
  Date/Author: 2026-04-24 / Codex

## Outcomes & Retrospective

This milestone should turn the project from a prototype into a dependable local tool. If it succeeds, the operator-facing workflow will be documented in `/README.md`, failures will be visible and attributable at the year level, and reruns will not damage earlier outputs. After completion, future work can focus on optional enhancements such as richer query surfaces, not on core correctness.

Implementation completed on 2026-04-24. The repository now records year-level outcomes through repository-owned result types, writes manifests with explicit counts for `cache_hit`, `cache_refresh`, `fetched`, and `failed`, supports `--fail-fast`, and documents the full setup and operating workflow in `/README.md`.

## Context and Orientation

By the time this plan starts, the package under `/src/yfinance_watchlist/` should already support single-symbol fetching, CSV watchlists, a `fetch` command, run-directory output, and persistent yearly cache files under `data/cache/history/`. The remaining problem is operational clarity. A user needs to know what happened during a run without reading Python code, and the package needs types that make those outcomes testable.

In this plan, a “partial failure” means that at least one requested symbol-year completed successfully, was served from cache, or was refreshed, and at least one requested symbol-year did not. A “run summary” is a Python object that collects counts and statuses for the overall fetch command. A “year result” is one entry in the manifest that says whether a specific symbol-year was a `cache_hit`, `cache_refresh`, `fetched`, or `failed`.

## Plan of Work

Add `/src/yfinance_watchlist/results.py` and define `FetchRunSummary`, plus a lightweight per-year record such as `SymbolYearResult`. `FetchRunSummary` should track the run directory, total requested symbol-years, counts for cached years, refreshed years, fetched years, and failed years, and a list of year-level records. `SymbolYearResult` should include the symbol, optional label, year, a status string, a source string, the output path, the row count, the last timestamp written, and an error message for failures.

Update `/src/yfinance_watchlist/client.py` so missing required quote fields and history rows are raised as repository-controlled `ValueError` messages. Keep the error text stable and human-readable because those messages will appear in the manifest. Do not let raw `KeyError` or DataFrame-specific exceptions leak to the CLI unless they are wrapped with symbol and year context.

Extend `/src/yfinance_watchlist/cli.py` with `--fail-fast`, `--start-year`, and `--end-year` defaults that are printed or recorded consistently. The `fetch` command should create a `FetchRunSummary`, append one result per symbol-year, and always attempt to write `manifest.json` before exiting. When `--fail-fast` is absent, continue to the next symbol-year after recording a failure. When it is present, stop immediately after the first failure, record that stop condition in the manifest, and return a non-zero exit code.

Update the cache and manifest writing paths so they persist predictable JSON structures. The manifest should include top-level run metadata and a `years` array for per-year results. Preserve stable key names because operators and future automation may read this file directly. The manifest must distinguish these sources exactly: `cache_hit` for an unchanged reused year, `cache_refresh` for the current year when new rows were appended, `fetched` for a brand-new year file, and `failed` for a requested year that could not be satisfied.

Add tests that model mixed outcomes. In `/test/test_cli.py`, create a scenario where one patched symbol-year is a past-year cache hit, one is a current-year refresh, one is a brand-new fetch, and one raises `ValueError`; assert that the CLI summary reports all four categories correctly and that the exit code is still `0`. Add another test where every requested symbol-year fails and assert that the exit code is non-zero. Add a rerun test in `/test/test_cache.py` or `/test/test_cli.py` that runs the same current-year command twice and confirms the first rerun appends only missing suffix rows while the second rerun becomes a no-op `cache_hit` if the cache is already current.

Finally, update `/README.md` so a novice can follow one linear workflow: install dependencies, create `watchlist.csv`, run the `fetch` command with year bounds, inspect `data/<run-date>/`, inspect `data/cache/history/`, and interpret `manifest.json`. Keep the README aligned with the actual CLI flags, cache layout, and source labels.

## Concrete Steps

Run all commands from `/workspace`.

1. Execute the full unit test suite while developing:

    PYTHONPATH=src python -m unittest discover -s test -v

2. Prepare a watchlist that includes one valid symbol and one intentionally problematic symbol:

    printf 'symbol,label\nAAPL,Apple\nNOT_A_REAL_SYMBOL,Bad\n' > watchlist.csv

3. Run the resilient batch command:

    PYTHONPATH=src python -m yfinance_watchlist.cli fetch --watchlist watchlist.csv --output data --start-year 2025 --end-year 2026

    Expected shape of success:

        Loaded 2 symbols from watchlist.csv
        Wrote outputs to data/2026-04-24T09-05Z
        Completed: 1 cache hit, 1 refreshed, 1 fetched, 1 failed

4. Inspect the manifest:

    sed -n '1,220p' data/2026-04-24T09-05Z/manifest.json

    Expected shape of success:

        {
          "status": "partial_success",
          "cached_years": 1,
          "refreshed_years": 1,
          "fetched_years": 1,
          "failed_years": 1,
          "years": [
            {"symbol": "AAPL", "year": 2025, "source": "cache_hit", ...},
            {"symbol": "AAPL", "year": 2026, "source": "cache_refresh", ...},
            {"symbol": "NOT_A_REAL_SYMBOL", "year": 2025, "source": "failed", "error": "..."}
          ]
        }

5. Prove reruns are safe:

    PYTHONPATH=src python -m yfinance_watchlist.cli fetch --watchlist watchlist.csv --output data --start-year 2025 --end-year 2026
    find data -maxdepth 2 -mindepth 2 -type d | sort

    Expected shape of success:

        data/2026-04-24T09-05Z
        data/2026-04-24T09-07Z

## Validation and Acceptance

Acceptance for this milestone requires five visible behaviors. First, a mixed watchlist run must keep successful outputs even when one symbol-year fails. Second, `manifest.json` must clearly report the year-level outcomes and the overall run status. Third, an all-failure run must return a non-zero exit code. Fourth, repeating the same command must create a new run directory instead of overwriting the old one. Fifth, when the requested range includes the current year, a rerun must either append only missing later rows or report that the current-year cache is already up to date.

The tests should demonstrate the internal policy choices, but the manual run and manifest inspection are equally important because they prove that an operator can understand the outcome without reading the source code. The updated README should be sufficient for a newcomer to follow the full workflow from setup to inspection.

## Idempotence and Recovery

This plan must remain safe to repeat. Each invocation should create a fresh run directory and should never rewrite prior manifests or quote CSV files. Cache updates for the current year must merge by `timestamp` so repeated refreshes do not duplicate rows. If writing the manifest fails, print a clear error and preserve any already written quote files and cache files so the user does not lose successful work. If a symbol-year fetch fails with an unexpected exception, catch it at the CLI boundary, record the exception text as a failure reason, and continue unless `--fail-fast` is active.

When a test or manual run reveals an ambiguous error message, refine the repository-owned exception text instead of expecting operators to interpret library internals. Record that refinement in `Decision Log` and `Surprises & Discoveries`.

## Artifacts and Notes

Record the first mixed-outcome run here once the implementation exists. Include a short CLI transcript and focused excerpts from `manifest.json` and one cached yearly CSV that shows a `dividend` column.

    $ PYTHONPATH=src python -m yfinance_watchlist.cli fetch --watchlist /tmp/yfplan3/watchlist.csv --output /tmp/yfplan3/data --start-year 2025 --end-year 2026
    Error: quote data for NOT_A_REAL_SYMBOL is missing currency
    Loaded 2 symbols from /tmp/yfplan3/watchlist.csv
    Wrote outputs to /tmp/yfplan3/data/2026-04-24T13-02Z
    Completed: 0 cache hit, 0 refreshed, 2 fetched, 2 failed

    $ sed -n '1,40p' /tmp/yfplan3/data/2026-04-24T13-02Z/manifest.json
    {
      "status": "partial_success",
      "cached_years": 0,
      "refreshed_years": 0,
      "fetched_years": 2,
      "failed_years": 2,
      "years": [
        {"symbol": "AAPL", "year": 2025, "source": "fetched"},
        {"symbol": "AAPL", "year": 2026, "source": "fetched"},
        {"symbol": "NOT_A_REAL_SYMBOL", "year": 2025, "source": "failed", "error": "quote data for NOT_A_REAL_SYMBOL is missing currency"}
      ]
    }

## Interfaces and Dependencies

Continue to use the package structure under `/src/yfinance_watchlist/` and the existing dependencies from `/requirements.txt`. Do not add a logging framework or external configuration library in this milestone.

At the end of the milestone, the following interfaces must exist:

- In `/src/yfinance_watchlist/results.py`, define:

    @dataclass
    class SymbolYearResult:
        symbol: str
        label: str | None
        year: int
        status: str
        source: str
        path: str | None = None
        row_count: int = 0
        last_timestamp: datetime | None = None
        error: str | None = None

    @dataclass
    class FetchRunSummary:
        run_dir: str
        requested_years: int
        cached_years: int
        refreshed_years: int
        fetched_years: int
        failed_years: int
        results: list[SymbolYearResult]

- In `/src/yfinance_watchlist/cli.py`, extend the fetch workflow so:

    python -m yfinance_watchlist.cli fetch --watchlist <path> --output <dir> --start-year <year> --end-year <year> [--fail-fast]

  returns `0` when at least one requested symbol-year is satisfied through `cache_hit`, `cache_refresh`, or `fetched`, and non-zero when all requested symbol-years fail or when the watchlist itself is invalid.

- In the manifest-writing path, serialize stable JSON keys for top-level counts and per-year statuses, including the exact source values `cache_hit`, `cache_refresh`, `fetched`, and `failed`.

Revision note: Revised on 2026-04-24 to replace symbol-level reporting with year-level cache-aware results and to account for current-year refresh behavior.
