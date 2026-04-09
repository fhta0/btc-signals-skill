# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Bitcoin quantitative trading analysis toolkit implemented as a Claude Skill (`btc-quant-trader`). Provides BTC price fetching, technical indicator calculation, multi-strategy signal generation, and backtesting. For educational/research use only — not investment advice.

**Python 3.10+ required.** Market data is loaded through a **`DataSource` abstraction** (`scripts/datasource/`). Supported backends:

- **`okx`** — OKX public REST candles (default for market data; no API key)
- **`yfinance`** — Yahoo Finance (optional)

OKX: symbol mapping and pagination live in `scripts/datasource/okx_source.py` (verified `BTC-USD`/`ETH-USD` → `*-USDT`, `after` in ms, limit 300 per page, browser-like `User-Agent`). Use `pytest -m integration` for live smoke tests.

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

Dependencies: `yfinance>=0.2.28`, `pandas>=2.0.0`, `numpy>=1.24.0`, `matplotlib>=3.7.0`, `pytest>=8.0.0`

## Common Commands

```bash
# Fetch OHLCV (default OKX; optional Yahoo)
python scripts/fetch_price.py --symbol BTC-USD --period 30d --interval 1h --save
python scripts/fetch_price.py --symbol BTC-USD --period 30d --interval 1h --source okx --market-type SPOT --save

# Signals (optional --source / --market-type)
python scripts/signal_generator.py --symbol BTC-USD --period 7d --interval 1h --strategies all
python scripts/signal_generator.py --symbol BTC-USD --period 7d --strategies rsi,macd --source okx

# Backtest (optional --source / --market-type)
python scripts/backtest.py --symbol BTC-USD --period 180d --interval 1d --strategy ma_crossover --capital 10000

# Tests (offline by default)
pytest -q

# Network integration tests (OKX, etc.) — optional
pytest -q -m integration

# Single test file
pytest tests/test_indicators.py -q
```

**Note:** OKX source currently expects `period` in the form `Nd` (e.g. `30d`, `180d`).

## Architecture

### Data layer (`scripts/datasource/`)

Do **not** branch on `source` inside `indicators.py` / `signal_generator.py` / `backtest.py`. All OHLCV goes through:

- **`fetch_ohlcv(symbol, interval, period, source=..., market_type=...)`** in `datasource/__init__.py`
- **`fetch_price.fetch_price_data(...)`** — thin wrapper used by scripts; same kwargs as above

Implementations:

- `base.py` — `DataSource` ABC + internal `normalize_ohlcv` (UTC index, OHLCV columns; not re-exported from `datasource` package)
- `yfinance_source.py` — Yahoo (lazy-import `yfinance` so tests can run without it when only testing OKX/offline helpers)
- `okx_source.py` — public `/api/v5/market/candles`, pagination via `after` (ms), browser-like `User-Agent`

**Symbol convention:** CLI uses **`BTC-USD`-style** symbols. OKX maps verified `BTC-USD` / `ETH-USD` → `*-USDT`; other `*-USD` inputs raise. Native `BASE-USDT` / `BASE-USDT-SWAP` are accepted. See `okx_source.resolve_okx_inst_id`.

### Scripts (`scripts/`)

1. **`fetch_price.py`** — CLI only. Args: `--symbol`, `--period`, `--interval`, `--source` (`yfinance`|`okx`), `--market-type` (`SPOT`|`SWAP`), `--save`.

2. **`indicators.py`** — Indicators on a DataFrame:
   - `calculate_rsi` — Wilder-style smoothing (`ewm(com=period-1, adjust=False)`)
   - `calculate_macd` — (macd, signal, histogram); histogram = macd − signal
   - `calculate_bollinger_bands`, `calculate_moving_averages`
   - `get_latest_indicators` — dict for signal generator

3. **`signal_generator.py`** — `SignalGenerator`; four strategies, equal weight 0.25; thresholds ±0.3. MACD branch uses **histogram sign** only. Output includes `symbol`, `risk_notes`, etc. CLI: `--strategies`, `--source`, `--market-type`.

4. **`backtest.py`** — `BacktestEngine`; commission on position changes; Sharpe uses **`annualization_factor(interval)`** (minute/hour/day aware) and is a **simplified** ratio (mean/std, no risk-free rate subtracted—fine for rough crypto research); result includes **`final_capital`**. CLI: `--source`, `--market-type`.

### Signal output shape

```
timestamp, symbol, current_price, total_score (-1.0 to 1.0),
action (BUY/SELL/HOLD), direction (做多/做空/观望),
signals[] (per-strategy scores + messages), risk_notes[]
```

### Skill definitions

- **OpenClaw / AgentSkills:** `skills/py_btc_signals/SKILL.md` — YAML front matter (`name: py_btc_signals`, `description`, optional `metadata` for `openclaw.requires.bins`). See [OpenClaw Skills](https://docs.openclaw.ai/skills/).
- **Claude Code (optional):** a separate `SKILL.md` may also live under `.claude/skills/...` if you mirror instructions for that product.

### Testing

- Default **`pytest -q`** — no network (`pytest.ini` registers `integration` marker).
- **`pytest -m integration`** — live OKX/Yahoo smoke tests when needed.

### Known limitations

- Backtesting is simplified: no slippage, no realistic market impact modeling
- Signals are purely technical — no on-chain data, macro data, or order book
- Warm-up bars needed before indicators are valid (avoid NaN edge cases)
- **`yfinance`** depends on Yahoo Finance availability; **OKX** depends on OKX REST and network (403 without a reasonable `User-Agent`)
