---
name: py_btc_signals
description: >
  获取 BTC 实时行情、计算 RSI/MACD/布林带/均线等技术指标、生成多策略交易信号、执行策略回测。
  当用户问"BTC 现在该买还是卖"、"帮我看看行情"、"做个回测"、"技术指标怎么样"、
  "信号怎么样"、"比特币涨还是跌"等时，主动使用本 Skill 调用 Python CLI。
  数据源支持 Yahoo Finance 与 OKX 公开接口（无需 API Key），仅供学习研究。
metadata: {"openclaw": {"emoji": "₿", "requires": {"bins": ["python"]}}}
---

# Py BTC Signals（OpenClaw Skill）

当用户询问 **比特币行情、技术指标、交易信号、回测、RSI、MACD、布林带、均线、OKX / Yahoo 数据** 时，使用本 Skill：在**包含 `scripts/` 的仓库根目录**下用 `python` 执行 CLI（勿把用户输入直接拼进 shell 元字符；`symbol` 等参数用引号包裹）。

## 定位仓库根目录（重要）

执行前先找到同时包含 `scripts/` 和 `requirements.txt` 的目录，记为 **`REPO`**。

- 通常就是用户启动 Claude Code 时的工作目录
- 不确定时运行：`find . -name "signal_generator.py" -not -path "*/.venv/*"` 确认

执行命令前先 `cd "$REPO"`，或使用绝对路径。**不要**依赖相对层级推算路径。

## 环境与依赖

- Python **3.10+**，已安装依赖：`pip install -r REPO/requirements.txt`
- 需要外网拉取行情（Yahoo / OKX 公开接口）
- 免责声明：**仅供学习研究，不构成投资建议**

## 常用命令（在 `REPO` 下）

**拉取行情**

```bash
python scripts/fetch_price.py --symbol BTC-USD --period 30d --interval 1h
python scripts/fetch_price.py --symbol BTC-USD --period 30d --interval 1h --source okx --market-type SPOT
# 保存到 data/ 目录（供后续离线分析）
python scripts/fetch_price.py --symbol BTC-USD --period 30d --interval 1h --save
```

**生成多策略信号**

```bash
python scripts/signal_generator.py --symbol BTC-USD --period 7d --interval 1h --strategies all
python scripts/signal_generator.py --symbol BTC-USD --period 7d --interval 1h --strategies rsi,macd --source okx
```

**回测**

```bash
python scripts/backtest.py --symbol BTC-USD --period 180d --interval 1d --strategy ma_crossover --capital 10000
python scripts/backtest.py --symbol BTC-USD --period 30d --interval 1h --strategy rsi --source okx
```

**测试（可选）**

```bash
pytest -q
```

## 数据源说明

- 默认 `--source yfinance`；OKX 用 `--source okx`，可选 `--market-type SPOT|SWAP`。
- OKX 展示符号白名单与分页细节见仓库内 `OKX_DATA_INTEGRATION.md`。
- 指标：RSI（Wilder 平滑）、MACD、布林带、均线；信号输出含 `symbol`、`risk_notes` 等字段。

## 输出与合规

- 向用户展示脚本打印结果即可；避免夸大收益承诺。
- 说明数据来源为第三方聚合 / 交易所公开 API，**非实盘撮合保证**。

## 相关文档

- 数据源集成细节：仓库内 `OKX_DATA_INTEGRATION.md`
- 项目说明：仓库内 `readme.md`
