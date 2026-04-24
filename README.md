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

Fetch quotes plus yearly daily history for a watchlist:

    PYTHONPATH=src python -m yfinance_watchlist.cli fetch --watchlist watchlist.csv --output data --start-year 2025 --end-year 2026

To stop on the first symbol-year failure instead of continuing:

    PYTHONPATH=src python -m yfinance_watchlist.cli fetch --watchlist watchlist.csv --output data --start-year 2025 --end-year 2026 --fail-fast

## Output Layout

Each fetch command writes a new run directory under the chosen output root:

    data/<run-date>/quotes.csv
    data/<run-date>/manifest.json

Historical cache files are shared across runs:

    data/cache/history/<symbol>/<year>.csv
    data/cache/history_index.json

Each yearly history row includes `timestamp`, OHLC data, `volume`, and `dividend`. Past years are reused as `cache_hit` when already present. The current year may be updated as `cache_refresh` when newer rows become available after an earlier run.

## Manifest Interpretation

`manifest.json` records top-level counts and one entry per requested symbol-year. The `source` field uses these values:

- `cache_hit`: an existing past-year file, or a current-year file already current through today
- `cache_refresh`: a current-year file that had newer rows appended
- `fetched`: a year fetched from Yahoo Finance for the first time
- `failed`: a quote or history request that could not be satisfied

The fetch command exits with code `0` when at least one requested symbol-year is satisfied and non-zero when all requested symbol-years fail.


# Reference
Ran Aroussi, PyPI, 2026, https://pypi.org/project/yfinance/, release 1.3.0.
Ran Aroussi, GitHub, 2026, https://github.com/ranaroussi/yfinance, release 1.3.0.
Ran Aroussi, n.d., yfinance documentation, https://ranaroussi.github.io/yfinance/.
