# -*- coding: utf-8 -*-
"""Offline tests for the US stock skill lab sidecar."""

from __future__ import annotations

import json
import os
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

    def test_resolve_tickers_uses_monitor_list_env(self):
        previous_stock_skill = os.environ.get("STOCK_SKILL_TICKERS")
        previous_stock_list = os.environ.get("STOCK_LIST")
        try:
            os.environ.pop("STOCK_SKILL_TICKERS", None)
            os.environ["STOCK_LIST"] = "AAPL,NVDA SPY;AAPL"
            self.assertEqual(lab.resolve_tickers(None), ["AAPL", "NVDA", "SPY"])
        finally:
            if previous_stock_skill is None:
                os.environ.pop("STOCK_SKILL_TICKERS", None)
            else:
                os.environ["STOCK_SKILL_TICKERS"] = previous_stock_skill
            if previous_stock_list is None:
                os.environ.pop("STOCK_LIST", None)
            else:
                os.environ["STOCK_LIST"] = previous_stock_list

    def test_render_feishu_message_contains_core_metrics(self):
        summary = {
            "tickers": ["MU"],
            "period": "6mo",
            "price_source": "sample",
            "yfinance_profiles": {"MU": {"last_price": 100.0}},
            "finance_toolkit": {"status": "ok"},
            "vectorbt_backtest": {
                "status": "ok",
                "engine": "vectorbt",
                "total_return": {"MU": 0.0345},
                "max_drawdown": {"MU": -0.0123},
                "trades": {"MU": 2},
            },
            "openbb": {"status": "optional_missing"},
        }

        message = lab.render_feishu_message(summary, ticker="MU")

        self.assertIn("MU", message)
        self.assertIn("yfinance + OpenBB", message)
        self.assertIn("FinanceToolkit", message)
        self.assertIn("vectorbt", message)
        self.assertIn("awesome-quant", message)
        self.assertIn("FinanceToolkit: ok", message)
        self.assertIn("vectorbt: ok", message)
        self.assertIn("3.45%", message)


if __name__ == "__main__":
    unittest.main()
