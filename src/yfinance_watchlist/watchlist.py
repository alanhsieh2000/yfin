from __future__ import annotations

import csv

from .models import WatchlistEntry


class WatchlistReader:
    def load(self, path: str) -> list[WatchlistEntry]:
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or "symbol" not in reader.fieldnames:
                raise ValueError(f"watchlist file {path} is missing required symbol header")

            entries: list[WatchlistEntry] = []
            seen: set[str] = set()
            for row in reader:
                symbol = (row.get("symbol") or "").strip()
                if not symbol:
                    continue
                if symbol in seen:
                    continue
                seen.add(symbol)
                label = (row.get("label") or "").strip() or None
                entries.append(WatchlistEntry(symbol=symbol, label=label))

        if not entries:
            raise ValueError(f"watchlist file {path} does not contain any symbols")
        return entries

