from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import QuoteSnapshot, WatchlistEntry


class FileStore:
    def write_quotes(self, run_dir: str, quotes: list[QuoteSnapshot], entries: list[WatchlistEntry]) -> str:
        path = Path(run_dir) / "quotes.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        labels = {entry.symbol: entry.label for entry in entries}
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["symbol", "label", "currency", "market_price", "market_time"],
            )
            writer.writeheader()
            for quote in quotes:
                writer.writerow(
                    {
                        "symbol": quote.symbol,
                        "label": labels.get(quote.symbol) or "",
                        "currency": quote.currency,
                        "market_price": quote.market_price,
                        "market_time": quote.market_time.isoformat(),
                    }
                )
        return str(path)

    def write_manifest(self, run_dir: str, manifest: dict) -> str:
        path = Path(run_dir) / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
        return str(path)

