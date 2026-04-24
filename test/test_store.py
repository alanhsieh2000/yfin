from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase

from yfinance_watchlist.models import QuoteSnapshot, WatchlistEntry
from yfinance_watchlist.store import FileStore


class FileStoreTestCase(TestCase):
    def test_write_quotes_creates_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            path = FileStore().write_quotes(
                str(run_dir),
                [
                    QuoteSnapshot(
                        symbol="AAPL",
                        currency="USD",
                        market_price=123.45,
                        market_time=datetime(2026, 4, 24, tzinfo=timezone.utc),
                    )
                ],
                [WatchlistEntry(symbol="AAPL", label="Apple")],
            )

            content = Path(path).read_text(encoding="utf-8")

        self.assertIn("symbol,label,currency,market_price,market_time", content)
        self.assertIn("AAPL,Apple,USD,123.45,2026-04-24T00:00:00+00:00", content)

    def test_write_manifest_creates_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            path = FileStore().write_manifest(str(run_dir), {"status": "ok"})

            payload = json.loads(Path(path).read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], "ok")

