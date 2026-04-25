from __future__ import annotations

import csv
from pathlib import Path

from .models import WatchlistEntry


def _normalize_symbol(value: str) -> str:
    normalized = value.strip().upper()
    return normalized.rstrip(",").rstrip()


def _normalize_label(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if normalized.startswith(","):
        normalized = normalized[1:].strip()
    return normalized or None


class WatchlistReader:
    def load(self, path: str) -> list[WatchlistEntry]:
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or "symbol" not in reader.fieldnames:
                raise ValueError(f"watchlist file {path} is missing required symbol header")

            entries: list[WatchlistEntry] = []
            seen: set[str] = set()
            for row in reader:
                symbol = _normalize_symbol(row.get("symbol") or "")
                if not symbol:
                    continue
                if symbol in seen:
                    continue
                seen.add(symbol)
                label = _normalize_label(row.get("label"))
                entries.append(WatchlistEntry(symbol=symbol, label=label))

        if not entries:
            raise ValueError(f"watchlist file {path} does not contain any symbols")
        return entries


class WatchlistStore:
    fieldnames = ["symbol", "label"]

    def load_entries(self, path: str) -> list[WatchlistEntry]:
        target = Path(path)
        if not target.exists():
            return []

        with open(target, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or "symbol" not in reader.fieldnames:
                raise ValueError(f"watchlist file {path} is missing required symbol header")

            entries: list[WatchlistEntry] = []
            seen: set[str] = set()
            for row in reader:
                symbol = _normalize_symbol(row.get("symbol") or "")
                if not symbol or symbol in seen:
                    continue
                seen.add(symbol)
                label = _normalize_label(row.get("label"))
                entries.append(WatchlistEntry(symbol=symbol, label=label))
        return entries

    def add_entry(self, path: str, symbol: str, label: str | None = None) -> WatchlistEntry:
        normalized_symbol = _normalize_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("symbol must not be empty")

        normalized_label = _normalize_label(label)
        entries = self.load_entries(path)
        for entry in entries:
            if entry.symbol == normalized_symbol:
                if entry.label:
                    raise ValueError(f"symbol {normalized_symbol} is already in the watchlist with label {entry.label}")
                raise ValueError(f"symbol {normalized_symbol} is already in the watchlist")

        entry = WatchlistEntry(symbol=normalized_symbol, label=normalized_label)
        entries.append(entry)
        self._write_entries(path, entries)
        return entry

    def remove_entry(self, path: str, symbol: str) -> WatchlistEntry:
        normalized_symbol = _normalize_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("symbol must not be empty")

        entries = self.load_entries(path)
        remaining = [entry for entry in entries if entry.symbol != normalized_symbol]
        if len(remaining) == len(entries):
            raise ValueError(f"symbol {normalized_symbol} is not in the watchlist")

        removed = next(entry for entry in entries if entry.symbol == normalized_symbol)
        self._write_entries(path, remaining)
        return removed

    def _write_entries(self, path: str, entries: list[WatchlistEntry]) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            writer.writeheader()
            for entry in entries:
                writer.writerow(
                    {
                        "symbol": entry.symbol,
                        "label": entry.label or "",
                    }
                )
