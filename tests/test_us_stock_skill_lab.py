# -*- coding: utf-8 -*-
"""Offline tests for the US stock skill lab sidecar."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import us_stock_skill_lab as lab


class UsStockSkillLabTest(unittest.TestCase):
    def test_sample_prices_has_requested_tickers(self):
        prices = lab.sample_prices(["AAPL", "NVDA"], rows=20)

        self.assertEqual(list(prices.columns), ["AAPL", "NVDA"])
        self.assertEqual(len(prices), 20)
        self.assertTrue(prices.notna().all().all())

    def test_vectorbt_backtest_shape(self):
        prices = lab.sample_prices(["AAPL", "SPY"], rows=80)

        result = lab.run_vectorbt_backtest(prices)

        self.assertIn(result["status"], {"ok", "degraded"})
        self.assertIn("total_return", result)
        self.assertEqual(set(result["total_return"]), {"AAPL", "SPY"})

    def test_resource_links_include_five_projects(self):
        names = {item["name"] for item in lab.load_resource_links()}

        self.assertGreaterEqual(names, {"yfinance", "OpenBB", "FinanceToolkit", "vectorbt", "awesome-quant"})

    def test_write_outputs(self):
        prices = lab.sample_prices(["NVDA"], rows=30)
        summary = {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "tickers": ["NVDA"],
            "price_source": "sample",
            "finance_toolkit": {"status": "degraded"},
            "vectorbt_backtest": {
                "status": "ok",
                "engine": "vectorbt",
                "total_return": {"NVDA": 0.12},
            },
            "openbb": {"status": "optional_missing"},
            "resources": lab.load_resource_links(),
        }
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            lab.write_outputs(out_dir, prices, summary)

            self.assertTrue((out_dir / "prices.csv").exists())
            self.assertTrue((out_dir / "report.md").read_text(encoding="utf-8").startswith("# US Stock Skill Lab"))
            parsed = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(parsed["tickers"], ["NVDA"])


if __name__ == "__main__":
    unittest.main()
