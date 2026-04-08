# Py BTC Signals

**English:** Open-source **Python** toolkit for **Bitcoin** market data (**Yahoo Finance** + **OKX** public API), **technical indicators** (RSI, MACD, Bollinger Bands, moving averages), **multi-strategy trading signals**, and simple **backtesting**. Educational / research only — not investment advice.

开源比特币行情与技术分析工具：**yfinance / OKX** 双数据源、多策略信号、基础回测；与代码实现一致。仅供学习研究，不构成投资建议。

> **GitHub 仓库：** [fhta0/btc-signals-skill](https://github.com/fhta0/btc-signals-skill)（公开技能与脚本一体化；本地目录名可任意）。

## OpenClaw Skill

本仓库包含符合 [AgentSkills](https://agentskills.io/) / [OpenClaw](https://docs.openclaw.ai/skills/) 的技能定义：

- 路径：`skills/py_btc_signals/SKILL.md`
- Skill `name`：`py_btc_signals`（`snake_case`）

**使用方式（任选其一）**

1. **整仓作为工作区**：用 OpenClaw 打开本仓库根目录，技能会随项目被识别（若配置扫描 `skills/` 或 `.agents/skills/`，以你的 `openclaw.json` 为准）。
2. **复制到全局技能目录**：将 `skills/py_btc_signals` 复制到 `~/.openclaw/skills/` 或当前工作区的 `skills/`，并确保执行命令时的工作目录仍是**本仓库根**（脚本依赖 `scripts/`）。
3. **CLI 验证**：`openclaw skills list`；新建会话或 `openclaw gateway restart` 后生效。详见 [Creating Skills](https://docs.openclaw.ai/tools/creating-skills)。

`SKILL.md` 内使用 `{baseDir}` 表示技能目录；仓库根目录为 `{baseDir}/../..`。

## 环境要求

- Python 3.10+
- 可访问外网（`yfinance` / OKX 数据源）

## 安装

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 目录结构

```text
py-btc-signals/   # 或你本地的 btc-quant-trader/
├── readme.md
├── requirements.txt
├── pytest.ini
├── skills/
│   └── py_btc_signals/
│       └── SKILL.md      # OpenClaw / AgentSkills 技能定义
└── scripts/
    ├── datasource/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── yfinance_source.py
    │   └── okx_source.py
    ├── fetch_price.py
    ├── indicators.py
    ├── signal_generator.py
    └── backtest.py
```

## 依赖（与 `requirements.txt` 一致）

- yfinance>=0.2.28
- pandas>=2.0.0
- numpy>=1.24.0
- pytest>=8.0.0
- matplotlib>=3.7.0

## 行情脚本

```bash
python scripts/fetch_price.py --symbol BTC-USD --period 30d --interval 1h --save
python scripts/fetch_price.py --symbol BTC-USD --period 30d --interval 1h --source okx --market-type SPOT
```

- 支持 `--symbol` / `--period` / `--interval`
- `--source`：`yfinance`（默认）或 `okx`
- `--market-type`：仅 OKX 有效，`SPOT` 或 `SWAP`
- CLI 统一使用 `BTC-USD` 风格；OKX 侧对 **已验证** 的 `BTC-USD` / `ETH-USD` 映射为 `*-USDT`，其它 `*-USD` 会报错；原生 `BASE-USDT` 可直接使用（逻辑见 `scripts/datasource/okx_source.py`）
- OKX 数据源下 `period` 暂要求 `Nd` 形式（如 `30d`）
- `--save` 会将 CSV 落盘到 `data/`

## 信号脚本

```bash
python scripts/signal_generator.py --symbol BTC-USD --period 7d --interval 1h --strategies all
python scripts/signal_generator.py --symbol BTC-USD --period 7d --interval 1h --strategies rsi,macd --source okx
```

### 支持策略

- `rsi`
- `macd`
- `bollinger`
- `ma_crossover`

### 输出字段（与 `generate()` 返回一致）

- `timestamp`
- `symbol`
- `current_price`
- `total_score`
- `action`（BUY / SELL / HOLD）
- `direction`（做多 / 做空 / 观望）
- `signals`（数组）
- `risk_notes`（数组）

## 回测脚本

```bash
python scripts/backtest.py --symbol BTC-USD --period 180d --interval 1d --strategy ma_crossover --capital 10000
python scripts/backtest.py --symbol BTC-USD --period 30d --interval 1h --strategy rsi --capital 10000 --source okx
```

### 回测结果字段（与 `_calculate_returns()` 返回一致）

- `total_return`
- `buy_hold_return`
- `excess_return`
- `final_capital`
- `sharpe_ratio`
- `max_drawdown`
- `total_trades`

### 年化系数规则（与 `annualization_factor()` 一致）

- 分钟级（如 `1m/5m/15m`，排除 `mo`）：`sqrt(365*24*60/minutes)`
- 小时级（如 `1h/4h`）：`sqrt(365*24/hours)`
- 日级（如 `1d`）：`sqrt(365/days)`
- 其他：`sqrt(365)`

## 指标计算说明

- RSI 使用 Wilder 平滑（`ewm(com=period-1, adjust=False)`），便于与主流平台对齐。
- MACD 信号判断使用 histogram 正负。

## 测试

```bash
pytest -q
pytest -q -m integration
```

默认测试不依赖外网；`-m integration` 会请求 OKX 等（见 `pytest.ini`）。

## GitHub 开源与发现性（SEO）

1. **仓库名**：推荐 `py-btc-signals`；避免过长或与现有大热仓库完全重名。
2. **About 描述**（英文，便于全球检索，可粘贴到 GitHub 仓库简介）：
   `Python Bitcoin toolkit: OHLCV from Yahoo Finance & OKX, RSI/MACD/Bollinger/MA signals, multi-strategy scoring, simple backtest. Educational only.`
3. **Topics 标签**（在仓库页面 Add topics）：  
   `bitcoin` `python` `quantitative-trading` `backtesting` `yfinance` `okx` `technical-analysis` `trading-signals` `cryptocurrency` `pandas` `numpy`
4. **README**：首段已含英文关键词；保持标题层级清晰（H1 一个、其余用 H2）。
5. **LICENSE**：仓库根目录已提供 `LICENSE`（MIT），开源页会显示 license 徽章，利于信任与筛选。

## 免责声明

本项目仅用于学习研究，不构成投资建议。
