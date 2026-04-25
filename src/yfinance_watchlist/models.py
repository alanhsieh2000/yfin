from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WatchlistEntry:
    symbol: str
    label: str | None = None


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    currency: str
    market_price: float
    market_time: datetime


@dataclass(frozen=True)
class PriceHistoryRow:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    dividend: float
    stock_splits: float
