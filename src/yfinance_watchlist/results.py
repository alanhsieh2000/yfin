from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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

    def to_manifest_dict(self) -> dict:
        payload = {
            "symbol": self.symbol,
            "label": self.label,
            "year": self.year,
            "status": self.status,
            "source": self.source,
            "path": self.path,
            "row_count": self.row_count,
            "last_timestamp": self.last_timestamp.isoformat() if self.last_timestamp else None,
            "error": self.error,
        }
        return payload


@dataclass
class FetchRunSummary:
    run_dir: str
    requested_years: int = 0
    cached_years: int = 0
    refreshed_years: int = 0
    fetched_years: int = 0
    failed_years: int = 0
    results: list[SymbolYearResult] = field(default_factory=list)
    stopped_early: bool = False

    def add_result(self, result: SymbolYearResult) -> None:
        self.requested_years += 1
        self.results.append(result)
        if result.source == "cache_hit":
            self.cached_years += 1
        elif result.source == "cache_refresh":
            self.refreshed_years += 1
        elif result.source == "fetched":
            self.fetched_years += 1
        elif result.source == "failed":
            self.failed_years += 1

    @property
    def satisfied_years(self) -> int:
        return self.cached_years + self.refreshed_years + self.fetched_years

    @property
    def status(self) -> str:
        if self.satisfied_years == 0:
            return "failed"
        if self.failed_years:
            return "partial_success"
        return "success"

    def to_manifest_dict(self) -> dict:
        return {
            "status": self.status,
            "requested_years": self.requested_years,
            "cached_years": self.cached_years,
            "refreshed_years": self.refreshed_years,
            "fetched_years": self.fetched_years,
            "failed_years": self.failed_years,
            "stopped_early": self.stopped_early,
            "years": [result.to_manifest_dict() for result in self.results],
        }

