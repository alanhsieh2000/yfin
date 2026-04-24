from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import yfinance as yf

from .models import PriceHistoryRow, QuoteSnapshot


class YahooFinanceClient:
    """Thin adapter around yfinance with repository-owned normalization."""

    def _today(self) -> date:
        return date.today()

    def fetch_quote(self, symbol: str) -> QuoteSnapshot:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        currency = info.get("currency")
        market_price = info.get("regularMarketPrice")
        market_time_raw = info.get("regularMarketTime")

        if currency in (None, ""):
            raise ValueError(f"quote data for {symbol} is missing currency")
        if market_price is None:
            raise ValueError(f"quote data for {symbol} is missing regular market price")
        if market_time_raw is None:
            raise ValueError(f"quote data for {symbol} is missing regular market time")

        market_time = datetime.fromtimestamp(market_time_raw, tz=timezone.utc)
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
        history = ticker.history(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            interval="1d",
            actions=True,
            auto_adjust=False,
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
