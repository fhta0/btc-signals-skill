#!/usr/bin/env python3
"""Simple BTC strategy backtest engine."""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np

SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from fetch_price import fetch_price_data
from indicators import calculate_rsi


def annualization_factor(interval: str) -> float:
    interval = interval.lower().strip()
    if interval.endswith("m") and not interval.endswith("mo"):
        minutes = int(interval[:-1]) if interval[:-1].isdigit() else 1
        periods_per_year = (365 * 24 * 60) / max(minutes, 1)
        return np.sqrt(periods_per_year)
    if interval.endswith("h"):
        hours = int(interval[:-1]) if interval[:-1].isdigit() else 1
        periods_per_year = (365 * 24) / max(hours, 1)
        return np.sqrt(periods_per_year)
    if interval.endswith("d"):
        days = int(interval[:-1]) if interval[:-1].isdigit() else 1
        periods_per_year = 365 / max(days, 1)
        return np.sqrt(periods_per_year)
    return np.sqrt(365)


class BacktestEngine:
    def __init__(self, initial_capital=10000, commission=0.001):
        self.initial_capital = initial_capital
        self.commission = commission

    def run_ma_crossover_backtest(self, data, interval="1d", fast=9, slow=21):
        df = data.copy()
        df["MA_Fast"] = df["Close"].rolling(fast).mean()
        df["MA_Slow"] = df["Close"].rolling(slow).mean()
        df["Signal"] = 0
        df.loc[df["MA_Fast"] > df["MA_Slow"], "Signal"] = 1
        df.loc[df["MA_Fast"] < df["MA_Slow"], "Signal"] = -1
        df["Position"] = df["Signal"].shift(1).fillna(0)
        return self._calculate_returns(df, annualization_factor(interval))

    def run_rsi_backtest(self, data, interval="1d", period=14, oversold=30, overbought=70):
        df = data.copy()
        df["RSI"] = calculate_rsi(df, period)
        df["Signal"] = 0
        df.loc[df["RSI"] < oversold, "Signal"] = 1
        df.loc[df["RSI"] > overbought, "Signal"] = -1
        df["Position"] = df["Signal"].shift(1).fillna(0)
        return self._calculate_returns(df, annualization_factor(interval))

    def _calculate_returns(self, df, ann_factor):
        df["Returns"] = df["Close"].pct_change().fillna(0)
        df["Trade"] = df["Position"].diff().abs().fillna(0)
        df["Strategy_Returns"] = df["Position"] * df["Returns"] - df["Trade"] * self.commission

        df["Cumulative_Returns"] = (1 + df["Strategy_Returns"]).cumprod()
        df["Buy_Hold"] = (1 + df["Returns"]).cumprod()

        total_return = (df["Cumulative_Returns"].iloc[-1] - 1) * 100
        buy_hold_return = (df["Buy_Hold"].iloc[-1] - 1) * 100

        std = df["Strategy_Returns"].std()
        # 简化夏普：均值/标准差年化，未减无风险利率；加密回测中 Rf 影响通常较小，勿与学术定义混为一谈
        sharpe = df["Strategy_Returns"].mean() / std * ann_factor if std > 0 else 0

        running_max = df["Cumulative_Returns"].cummax()
        drawdown = (df["Cumulative_Returns"] - running_max) / running_max
        max_drawdown = drawdown.min() * 100

        return {
            "total_return": float(total_return),
            "buy_hold_return": float(buy_hold_return),
            "excess_return": float(total_return - buy_hold_return),
            "final_capital": round(self.initial_capital * (1 + total_return / 100), 2),
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(max_drawdown),
            "total_trades": int(df["Trade"].sum() / 2),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--period", default="180d")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--strategy", default="ma_crossover", choices=["ma_crossover", "rsi"])
    parser.add_argument("--capital", type=int, default=10000)
    parser.add_argument("--source", default="okx", choices=["yfinance", "okx"])
    parser.add_argument("--market-type", default="SPOT", choices=["SPOT", "SWAP"])
    args = parser.parse_args()

    data = fetch_price_data(
        args.symbol,
        args.period,
        args.interval,
        source=args.source,
        market_type=args.market_type,
    )
    engine = BacktestEngine(initial_capital=args.capital)

    if args.strategy == "ma_crossover":
        result = engine.run_ma_crossover_backtest(data, interval=args.interval)
    else:
        result = engine.run_rsi_backtest(data, interval=args.interval)

    print("\n=== 回测结果 ===")
    print(f"总收益率: {result['total_return']:.2f}%")
    print(f"买入持有: {result['buy_hold_return']:.2f}%")
    print(f"超额收益: {result['excess_return']:.2f}%")
    print(f"期末资金: ${result['final_capital']:.2f}")
    print(f"夏普比率: {result['sharpe_ratio']:.2f}")
    print(f"最大回撤: {result['max_drawdown']:.2f}%")
    print(f"交易次数: {result['total_trades']}")


if __name__ == "__main__":
    main()
