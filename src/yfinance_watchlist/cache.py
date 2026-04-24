from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import PriceHistoryRow


class HistoryCache:
    def __init__(self, output_dir: str) -> None:
        self.output_dir = Path(output_dir)
        self.cache_root = self.output_dir / "cache" / "history"
        self.index_path = self.output_dir / "cache" / "history_index.json"

    def has_year(self, symbol: str, year: int) -> bool:
        path = self.year_path(symbol, year)
        entry = self._load_index().get("symbols", {}).get(symbol, {}).get(str(year))
        return path.exists() and entry is not None

    def read_year(self, symbol: str, year: int) -> list[PriceHistoryRow]:
        path = self.year_path(symbol, year)
        rows: list[PriceHistoryRow] = []
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(
                    PriceHistoryRow(
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"]),
                        dividend=float(row["dividend"]),
                    )
                )
        return rows

    def latest_timestamp(self, symbol: str, year: int) -> datetime | None:
        entry = self._load_index().get("symbols", {}).get(symbol, {}).get(str(year))
        if entry is None:
            return None
        timestamp = entry.get("latest_timestamp")
        if not timestamp:
            return None
        return datetime.fromisoformat(timestamp)

    def write_year(self, symbol: str, year: int, rows: list[PriceHistoryRow]) -> str:
        path = self.year_path(symbol, year)
        self._write_rows(path, rows)
        self._update_index(symbol, year, path, rows)
        return str(path)

    def merge_year(self, symbol: str, year: int, rows: list[PriceHistoryRow]) -> str:
        existing = self.read_year(symbol, year) if self.has_year(symbol, year) else []
        merged = {row.timestamp: row for row in existing}
        for row in rows:
            merged[row.timestamp] = row
        merged_rows = [merged[key] for key in sorted(merged)]
        return self.write_year(symbol, year, merged_rows)

    def year_path(self, symbol: str, year: int) -> Path:
        return self.cache_root / symbol / f"{year}.csv"

    def _write_rows(self, path: Path, rows: list[PriceHistoryRow]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".csv.tmp")
        with open(temp_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["timestamp", "open", "high", "low", "close", "volume", "dividend"],
            )
            writer.writeheader()
            for row in sorted(rows, key=lambda item: item.timestamp):
                payload = asdict(row)
                payload["timestamp"] = row.timestamp.isoformat()
                writer.writerow(payload)
        temp_path.replace(path)

    def _load_index(self) -> dict:
        if not self.index_path.exists():
            return {"symbols": {}}
        with open(self.index_path, encoding="utf-8") as handle:
            return json.load(handle)

    def _update_index(self, symbol: str, year: int, path: Path, rows: list[PriceHistoryRow]) -> None:
        index = self._load_index()
        index.setdefault("symbols", {}).setdefault(symbol, {})
        latest = max((row.timestamp for row in rows), default=None)
        index["symbols"][symbol][str(year)] = {
            "path": str(path.relative_to(self.output_dir)),
            "latest_timestamp": latest.isoformat() if latest else None,
            "row_count": len(rows),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as handle:
            json.dump(index, handle, indent=2, sort_keys=True)
