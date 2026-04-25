from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, time, timedelta, timezone
from io import StringIO

import pandas as pd
import yfinance as yf

from .models import PriceHistoryRow, QuoteSnapshot


class YahooFinanceClient:
    """Thin adapter around yfinance with repository-owned normalization."""

    def _today(self) -> date:
        return date.today()

    def fetch_quote(self, symbol: str) -> QuoteSnapshot:
        ticker = yf.Ticker(symbol)
        info = self._read_ticker_info(ticker) or {}
        fast_info = self._read_ticker_fast_info(ticker) or {}
        history_metadata = self._read_ticker_history_metadata(ticker) or {}
        latest_history_timestamp = self._read_latest_history_timestamp(ticker)

        currency = self._first_present(
            info.get("currency"),
            info.get("financialCurrency"),
            fast_info.get("currency"),
            history_metadata.get("currency"),
        )
        market_price = self._first_present(
            info.get("regularMarketPrice"),
            info.get("currentPrice"),
            fast_info.get("regularMarketPrice"),
            fast_info.get("lastPrice"),
            history_metadata.get("regularMarketPrice"),
        )
        market_time_raw = self._first_present(
            info.get("regularMarketTime"),
            history_metadata.get("regularMarketTime"),
            self._history_metadata_trading_start(history_metadata),
            latest_history_timestamp,
        )

        if currency in (None, "") and market_price is None and latest_history_timestamp is None:
            raise ValueError(f"quote data for {symbol} is unavailable")
        if currency in (None, ""):
            raise ValueError(f"quote data for {symbol} is missing currency")
        if market_price is None:
            raise ValueError(f"quote data for {symbol} is missing regular market price")
        if market_time_raw is None:
            raise ValueError(f"quote data for {symbol} is missing regular market time")

        market_time = self._normalize_quote_timestamp(market_time_raw)
        return QuoteSnapshot(
            symbol=symbol,
            currency=str(currency),
            market_price=float(market_price),
            market_time=market_time,
        )

    def fetch_history(self, symbol: str, start_year: int, end_year: int) -> list[PriceHistoryRow]:
        if start_year > end_year:
            raise ValueError("start_year must be less than or equal to end_year")

        rows: list[PriceHistoryRow] = []
        for year in range(start_year, end_year + 1):
            start_date, end_date = self._year_bounds(year)
            rows.extend(self.fetch_history_year(symbol, year, start_date=start_date, end_date=end_date))
        return rows

    def fetch_history_year(
        self,
        symbol: str,
        year: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PriceHistoryRow]:
        if start_date is None or end_date is None:
            start_date, end_date = self._year_bounds(year)
        if start_date >= end_date:
            return []

        ticker = yf.Ticker(symbol)
        history = self._read_ticker_history(
            ticker,
            symbol=symbol,
            year=year,
            start_date=start_date,
            end_date=end_date,
        )
        return self._normalize_history(symbol, history)

    def _year_bounds(self, year: int) -> tuple[date, date]:
        today = self._today()
        start = date(year, 1, 1)
        if year < today.year:
            return start, date(year + 1, 1, 1)
        if year == today.year:
            return start, today + timedelta(days=1)
        raise ValueError(f"cannot fetch history for future year {year}")

    def _normalize_history(self, symbol: str, history: pd.DataFrame) -> list[PriceHistoryRow]:
        required = ["Open", "High", "Low", "Close", "Volume"]
        missing = [column for column in required if column not in history.columns]
        if missing:
            raise ValueError(
                f"history data for {symbol} is missing required fields: {', '.join(missing)}"
            )

        rows: list[PriceHistoryRow] = []
        for timestamp, row in history.iterrows():
            normalized_timestamp = self._normalize_timestamp(timestamp)
            dividend = row.get("Dividends", 0)
            if pd.isna(dividend):
                dividend = 0
            volume = row["Volume"]
            if pd.isna(volume):
                volume = 0
            rows.append(
                PriceHistoryRow(
                    timestamp=normalized_timestamp,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(volume),
                    dividend=float(dividend),
                )
            )
        return rows

    @staticmethod
    def _normalize_timestamp(value: object) -> datetime:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(timezone.utc)
        else:
            timestamp = timestamp.tz_convert(timezone.utc)
        if timestamp.hour == 0 and timestamp.minute == 0 and timestamp.second == 0:
            return datetime.combine(timestamp.date(), time.min, tzinfo=timezone.utc)
        return timestamp.to_pydatetime()

    @classmethod
    def _normalize_quote_timestamp(cls, value: object) -> datetime:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        return cls._normalize_timestamp(value)

    @staticmethod
    def _first_present(*values: object) -> object | None:
        for value in values:
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _history_metadata_trading_start(history_metadata: dict) -> object | None:
        current_period = history_metadata.get("currentTradingPeriod")
        if not isinstance(current_period, dict):
            return None

        regular_period = current_period.get("regular")
        if not isinstance(regular_period, dict):
            return None

        return regular_period.get("start")

    @staticmethod
    def _read_ticker_info(ticker: yf.Ticker) -> dict:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            try:
                return ticker.info
            except Exception:
                return {}

    @staticmethod
    def _read_ticker_fast_info(ticker: yf.Ticker) -> dict:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            try:
                fast_info = ticker.fast_info
                if hasattr(fast_info, "items"):
                    return dict(fast_info.items())
                return dict(fast_info)
            except Exception:
                return {}

    @staticmethod
    def _read_ticker_history_metadata(ticker: yf.Ticker) -> dict:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            try:
                return ticker.get_history_metadata()
            except Exception:
                return {}

    @classmethod
    def _read_latest_history_timestamp(cls, ticker: yf.Ticker) -> datetime | None:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            try:
                history = ticker.history(period="5d", interval="1d", actions=False, auto_adjust=False)
            except Exception:
                return None

        if history.empty:
            return None
        return cls._normalize_timestamp(history.index[-1])

    @staticmethod
    def _read_ticker_history(
        ticker: yf.Ticker,
        *,
        symbol: str,
        year: int,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            try:
                return ticker.history(
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                    interval="1d",
                    actions=True,
                    auto_adjust=False,
                )
            except Exception as exc:
                raise ValueError(
                    f"history data for {symbol} in {year} could not be retrieved: {exc}"
                ) from exc
