#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US stock research skill lab.

This script integrates popular open-source US stock research tools without
making them mandatory for the daily production analysis path.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


DEFAULT_TICKERS = ["AAPL", "NVDA", "SPY"]
REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCE_FILE = REPO_ROOT / "docs" / "us_stock_skill_resources.json"


@dataclass(frozen=True)
class PriceResult:
    prices: pd.DataFrame
    source: str
    warning: str | None = None


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run US stock skill integration smoke checks.")
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS, help="US tickers to inspect.")
    parser.add_argument("--period", default="6mo", help="yfinance period, for example 3mo, 6mo, 1y.")
    parser.add_argument("--out", default="artifacts/us_stock_skill_lab", help="Output directory.")
    return parser.parse_args(list(argv) if argv is not None else None)


def sample_prices(tickers: list[str], rows: int = 126) -> pd.DataFrame:
    index = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=rows)
    data: dict[str, np.ndarray] = {}
    for offset, ticker in enumerate(tickers):
        base = 100.0 + offset * 30
        drift = np.linspace(0, 16 + offset * 3, rows)
        cycle = np.sin(np.linspace(0, 7, rows) + offset) * (2.0 + offset)
        data[ticker] = base + drift + cycle
    return pd.DataFrame(data, index=index)


def load_prices(tickers: list[str], period: str) -> PriceResult:
    try:
        import yfinance as yf

        data = yf.download(
            tickers=tickers,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        prices = extract_close_prices(data, tickers)
        if prices.empty:
            raise RuntimeError("yfinance returned no close prices")
        return PriceResult(prices=prices, source="yfinance")
    except Exception as exc:
        return PriceResult(
            prices=sample_prices(tickers),
            source="sample",
            warning=f"yfinance unavailable, used deterministic sample prices: {exc}",
        )


def extract_close_prices(data: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.get_level_values(0):
            close = data["Close"]
        elif "Close" in data.columns.get_level_values(-1):
            close = data.xs("Close", axis=1, level=-1)
        else:
            return pd.DataFrame()
    else:
        if "Close" not in data:
            return pd.DataFrame()
        close = data[["Close"]].copy()
        if len(tickers) == 1:
            close.columns = [tickers[0]]
    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])
    available = [col for col in close.columns if str(col).upper() in tickers]
    return close.loc[:, available].dropna(how="all")


def fetch_yfinance_profiles(tickers: list[str]) -> dict[str, dict[str, Any]]:
    try:
        import yfinance as yf
    except Exception as exc:
        return {ticker: {"status": "unavailable", "reason": str(exc)} for ticker in tickers}

    profiles: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        try:
            fast_info = yf.Ticker(ticker).fast_info
            profiles[ticker] = {
                "status": "ok",
                "last_price": json_safe(getattr(fast_info, "last_price", None)),
                "market_cap": json_safe(getattr(fast_info, "market_cap", None)),
                "currency": json_safe(getattr(fast_info, "currency", None)),
            }
        except Exception as exc:
            profiles[ticker] = {"status": "degraded", "reason": str(exc)}
    return profiles


def run_finance_toolkit_probe(tickers: list[str]) -> dict[str, Any]:
    try:
        from financetoolkit import Toolkit

        toolkit = Toolkit(tickers, start_date="2023-01-01")
        ratios = toolkit.ratios.collect_profitability_ratios()
        shape = getattr(ratios, "shape", (0, 0))
        return {"status": "ok", "rows": int(shape[0]), "columns": int(shape[1])}
    except Exception as exc:
        return {"status": "degraded", "reason": f"FinanceToolkit probe failed or skipped: {exc}"}


def run_vectorbt_backtest(prices: pd.DataFrame) -> dict[str, Any]:
    clean = prices.dropna(how="all").ffill().dropna(how="all")
    if clean.empty:
        return {"status": "degraded", "engine": "none", "reason": "no price data"}
    try:
        import vectorbt as vbt

        fast = vbt.MA.run(clean, window=10)
        slow = vbt.MA.run(clean, window=30)
        entries = fast.ma_crossed_above(slow)
        exits = fast.ma_crossed_below(slow)
        portfolio = vbt.Portfolio.from_signals(clean, entries, exits, init_cash=10_000, freq="1D")
        return {
            "status": "ok",
            "engine": "vectorbt",
            "total_return": series_to_dict(portfolio.total_return()),
            "max_drawdown": series_to_dict(portfolio.max_drawdown()),
            "trades": series_to_dict(portfolio.trades.count()),
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "engine": "pandas-fallback",
            "reason": str(exc),
            "total_return": series_to_dict(clean.iloc[-1] / clean.iloc[0] - 1),
            "max_drawdown": series_to_dict((clean / clean.cummax() - 1).min()),
            "trades": {str(col): 0 for col in clean.columns},
        }


def check_openbb() -> dict[str, str]:
    try:
        from openbb import obb  # noqa: F401

        return {"status": "ok", "detail": "OpenBB import succeeded."}
    except Exception as exc:
        return {"status": "optional_missing", "detail": str(exc)}


def load_resource_links() -> list[dict[str, Any]]:
    return json.loads(RESOURCE_FILE.read_text(encoding="utf-8"))


def build_summary(tickers: list[str], period: str, price_result: PriceResult) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tickers": tickers,
        "period": period,
        "price_source": price_result.source,
        "price_warning": price_result.warning,
        "yfinance_profiles": fetch_yfinance_profiles(tickers),
        "finance_toolkit": run_finance_toolkit_probe(tickers),
        "vectorbt_backtest": run_vectorbt_backtest(price_result.prices),
        "openbb": check_openbb(),
        "resources": load_resource_links(),
    }


def write_outputs(out_dir: Path, prices: pd.DataFrame, summary: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    prices.to_csv(out_dir / "prices.csv", index_label="date")
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(render_report(summary), encoding="utf-8")


def render_report(summary: dict[str, Any]) -> str:
    backtest = summary["vectorbt_backtest"]
    lines = [
        "# US Stock Skill Lab Smoke Report",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Tickers: {', '.join(summary['tickers'])}",
        f"- Price source: {summary['price_source']}",
        f"- FinanceToolkit: {summary['finance_toolkit']['status']}",
        f"- vectorbt: {backtest['status']} ({backtest['engine']})",
        f"- OpenBB: {summary['openbb']['status']}",
        "",
        "## Backtest total return",
        "",
    ]
    for ticker, value in backtest.get("total_return", {}).items():
        lines.append(f"- {ticker}: {float(value):.2%}")
    lines.extend(["", "## Resource map", ""])
    for item in summary["resources"]:
        lines.append(f"- [{item['name']}]({item['url']}): {item['role']}")
    lines.extend(["", "Research output only. This is not investment advice."])
    return "\n".join(lines) + "\n"


def series_to_dict(value: Any) -> dict[str, float | int | None]:
    if isinstance(value, pd.Series):
        return {label_for_key(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, pd.DataFrame):
        row = value.iloc[0] if len(value.index) else pd.Series(dtype=float)
        return {label_for_key(k): json_safe(v) for k, v in row.items()}
    return {"portfolio": json_safe(value)}


def label_for_key(key: Any) -> str:
    if isinstance(key, tuple) and key:
        return str(key[-1])
    return str(key)


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    return value


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    tickers = [ticker.strip().upper() for ticker in args.tickers if ticker.strip()]
    price_result = load_prices(tickers, args.period)
    summary = build_summary(tickers, args.period, price_result)
    write_outputs(Path(args.out), price_result.prices, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
