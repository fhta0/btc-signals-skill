#!/usr/bin/env python3
"""CLI：拉取 OHLCV，数据源由 datasource 工厂选择。"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from datasource import fetch_ohlcv


def fetch_price_data(
    symbol: str = "BTC-USD",
    period: str = "30d",
    interval: str = "1h",
    source: str = "okx",
    market_type: str = "SPOT",
):
    """供 signal_generator / backtest 等脚本调用，返回统一 OHLCV DataFrame。"""
    return fetch_ohlcv(
        symbol, interval, period, source=source, market_type=market_type
    )


def save_data(data, symbol: str, output_dir: str = "data") -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filename = f"{symbol.replace('-', '_')}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    out_path = Path(output_dir) / filename
    data.to_csv(out_path)
    return str(out_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--period", default="30d")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--source", default="okx", choices=["yfinance", "okx"])
    parser.add_argument("--market-type", default="SPOT", choices=["SPOT", "SWAP"])
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    data = fetch_price_data(
        args.symbol,
        args.period,
        args.interval,
        source=args.source,
        market_type=args.market_type,
    )
    print(f"获取到 {len(data)} 条数据 (source={args.source})")
    print(f"最新收盘价: ${data['Close'].iloc[-1]:.2f}")

    if args.save:
        path = save_data(data, args.symbol)
        print(f"数据已保存: {path}")


if __name__ == "__main__":
    main()
