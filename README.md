# Yahoo Finance API
The purpose of this project is to download the market data of stocks and ETFs in the watchlist from Yahoo! Finance's APIs. 

Inside the src sub-folder, there could be several needed python classes, each in its folder under the src sub-folder. By working together, these classes could be integrated into a python package.

Inside the test sub-folder, there could be serveral python classes that inherit 
TestCase class of unittest. These classes implement proper test cases for the python classes under the above src sub-folder.

# Implementation

## Setup

Install dependencies from the repository root:

    pip install -r requirements.txt

Run the test suite with:

    PYTHONPATH=src python -m unittest discover -s test -v

## Watchlist Format

The watchlist is a CSV file with a required `symbol` column and an optional `label` column. Duplicate symbols are ignored after the first occurrence.

Example:

    symbol,label
    AAPL,Apple
    SPY,S&P 500 ETF

## Commands

Fetch a single live quote:

    PYTHONPATH=src python -m yfinance_watchlist.cli quote AAPL

Show the current watchlist stored in `data/watchlist.csv`:

    PYTHONPATH=src python -m yfinance_watchlist.cli show

Add or update a symbol and optional label in `data/watchlist.csv`:

    PYTHONPATH=src python -m yfinance_watchlist.cli add AAPL Apple

If the label contains spaces, quote it so the shell passes it as one argument:

    PYTHONPATH=src python -m yfinance_watchlist.cli add AAPL "Apple Inc."

If you accidentally type a comma after the symbol, such as `AAPL,`, the command still stores the symbol as `AAPL`.

You can also add a symbol without a label:

    PYTHONPATH=src python -m yfinance_watchlist.cli add SPY

Remove a symbol from `data/watchlist.csv`:

    PYTHONPATH=src python -m yfinance_watchlist.cli remove AAPL

Fetch quotes plus yearly daily history for a watchlist:

    PYTHONPATH=src python -m yfinance_watchlist.cli fetch --output data --start-year 2025 --end-year 2026

By default, fetch keeps the 10 newest timestamped run directories under the output root. Override that limit when needed:

    PYTHONPATH=src python -m yfinance_watchlist.cli fetch --output data --start-year 2025 --end-year 2026 --keep-runs 20

To stop on the first symbol-year failure instead of continuing:

    PYTHONPATH=src python -m yfinance_watchlist.cli fetch --output data --start-year 2025 --end-year 2026 --fail-fast

All watchlist management commands default to `data/watchlist.csv`, and `fetch` reads the same file unless `--watchlist` is provided explicitly. This keeps mutable watchlist data in the same `data/` tree as fetch outputs and cache files, which is useful when `data/` is a read/write volume in a container.

## MCP Server

Start the local FastMCP HTTP server from the repository root:

    PYTHONPATH=src python -m yfinance_watchlist.mcp_server --host 127.0.0.1 --port 8000 --path /mcp/

MCP clients can connect to:

    http://127.0.0.1:8000/mcp/

The server exposes these tools:

- `get_quote(symbol)`: fetch a single live quote.
- `get_history(symbol, start_year, end_year)`: fetch normalized daily history rows for an inclusive year range.
- `list_watchlist(watchlist_path="data/watchlist.csv")`: read watchlist entries.
- `add_watchlist_symbol(symbol, label=null, watchlist_path="data/watchlist.csv")`: add a symbol and optional label to a watchlist.
- `remove_watchlist_symbol(symbol, watchlist_path="data/watchlist.csv")`: remove a symbol from a watchlist.
- `fetch_watchlist(start_year, end_year, watchlist_path="data/watchlist.csv", output_dir="data", fail_fast=false, keep_runs=10)`: run the same batch fetch workflow as the CLI and return the generated manifest and output paths.

For file arguments, the MCP server accepts relative paths under its base directory only. Use `--base-dir <path>` when starting the server to choose a different root for `watchlist_path` and `output_dir`.

For container deployments, mount a writable volume at the server base directory's `data/` folder. For example, if the application runs under `/workspace`, mount host storage to `/workspace/data` and start the server from `/workspace` or pass `--base-dir /workspace`.

## Output Layout

Each fetch command writes a new run directory under the chosen output root:

    data/watchlist.csv
    data/<run-date>/quotes.csv
    data/<run-date>/manifest.json

The fetch command automatically prunes older timestamped run directories after writing the current run. By default it keeps the newest 10 run directories, and `--keep-runs` changes that retention count. This cleanup only applies to timestamped run directories under the selected output root; it does not delete `data/cache/` or unrelated directories.

Historical cache files are shared across runs:

    data/cache/history/<symbol>/<year>.csv
    data/cache/history_index.json

Each yearly history row includes `timestamp`, auto-adjusted OHLC data, `volume`, `dividend`, and `stock_splits`. Past years are reused as `cache_hit` when already present. The current year is compared against a fresh Yahoo Finance pull, and any newly observed dividend or split forces `cache_refresh` for every cached year of that symbol because adjusted prices for earlier dates become stale.

## Manifest Interpretation

`manifest.json` records top-level counts and one entry per requested symbol-year. The `source` field uses these values:

- `cache_hit`: an existing year file that still matches the latest adjusted history
- `cache_refresh`: a cached year rewritten because the current year changed or a new dividend/split made older adjusted prices stale
- `fetched`: a year fetched from Yahoo Finance for the first time
- `failed`: a quote or history request that could not be satisfied

The fetch command exits with code `0` when at least one requested symbol-year is satisfied and non-zero when all requested symbol-years fail.


# Reference
Ran Aroussi, PyPI, 2026, https://pypi.org/project/yfinance/, release 1.3.0.
Ran Aroussi, GitHub, 2026, https://github.com/ranaroussi/yfinance, release 1.3.0.
Ran Aroussi, n.d., yfinance documentation, https://ranaroussi.github.io/yfinance/.
