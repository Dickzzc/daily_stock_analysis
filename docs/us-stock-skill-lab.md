# US Stock Skill Lab

`scripts/us_stock_skill_lab.py` is a sidecar smoke lab for the most useful GitHub US stock research tools:

- `yfinance`: US stock price and ticker metadata.
- `FinanceToolkit`: fundamentals and ratio probes.
- `vectorbt`: fast vectorized backtesting.
- `OpenBB`: optional deep-research import probe.
- `awesome-quant`: packaged navigation links in `docs/us_stock_skill_resources.json`.

Run locally with Python 3.11:

```powershell
py -3.11 -m venv .venv-stock-skills
.\.venv-stock-skills\Scripts\python -m pip install -U pip
.\.venv-stock-skills\Scripts\python -m pip install -r requirements-stock-skills.txt
.\.venv-stock-skills\Scripts\python scripts\us_stock_skill_lab.py --tickers AAPL NVDA SPY --period 6mo --out artifacts\us_stock_skill_lab
.\.venv-stock-skills\Scripts\python -m unittest tests.test_us_stock_skill_lab
```

OpenBB is optional and intentionally separated:

```powershell
.\.venv-stock-skills\Scripts\python -m pip install -r requirements-stock-skills-openbb.txt
```

Outputs:

- `prices.csv`: close prices used by the backtest.
- `summary.json`: integration status, metadata, fundamentals probe, backtest metrics, OpenBB availability, and resource links.
- `report.md`: readable smoke report.

This lab is for research and education only. It does not place trades and is not investment advice.
