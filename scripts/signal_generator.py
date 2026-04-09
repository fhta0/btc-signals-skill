#!/usr/bin/env python3
"""Generate multi-strategy BTC trading signals."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from fetch_price import fetch_price_data
from indicators import get_latest_indicators


class SignalGenerator:
    DEFAULT_CONFIG = {
        "rsi": {"oversold": 30, "overbought": 70, "weight": 0.25},
        "macd": {"weight": 0.25},
        "bollinger": {"weight": 0.25},
        "ma_crossover": {"weight": 0.25},
    }

    def __init__(self, enabled_strategies=None):
        self.config = self.DEFAULT_CONFIG
        self.enabled = enabled_strategies or list(self.config.keys())
        self.enabled = [s for s in self.enabled if s in self.config]
        if not self.enabled:
            raise ValueError("strategies 参数无效，至少启用一个策略")

    def rsi_signal(self, rsi_value: float):
        if rsi_value < self.config["rsi"]["oversold"]:
            return 1, f"RSI={rsi_value:.2f}，超卖偏多"
        if rsi_value > self.config["rsi"]["overbought"]:
            return -1, f"RSI={rsi_value:.2f}，超买偏空"
        return 0, f"RSI={rsi_value:.2f}，中性"

    @staticmethod
    def macd_signal(histogram: float):
        if histogram > 0:
            return 1, "MACD 金叉偏多"
        if histogram < 0:
            return -1, "MACD 死叉偏空"
        return 0, "MACD 中性"

    @staticmethod
    def bollinger_signal(price: float, upper: float, lower: float):
        if price <= lower:
            return 1, f"触及下轨({lower:.2f})，偏多"
        if price >= upper:
            return -1, f"触及上轨({upper:.2f})，偏空"
        return 0, "布林带中性"

    @staticmethod
    def ma_crossover_signal(
        ma_fast: float, ma_slow: float, ma_fast_prev: float, ma_slow_prev: float
    ):
        crossed_up = ma_fast_prev <= ma_slow_prev and ma_fast > ma_slow
        crossed_down = ma_fast_prev >= ma_slow_prev and ma_fast < ma_slow
        if crossed_up:
            return 1, "均线金叉确认，偏多"
        if crossed_down:
            return -1, "均线死叉确认，偏空"
        return 0, "均线未发生新交叉，中性"

    @staticmethod
    def _risk_notes(total_score: float):
        notes = [
            "请结合仓位管理与止损策略，不要单指标重仓。",
            "极端行情下技术指标可能失真。"
        ]
        if abs(total_score) < 0.2:
            notes.append("当前综合信号较弱，建议降低交易频率。")
        return notes

    def generate(self, symbol: str, indicators: dict):
        weighted_sum = 0.0
        total_weight = sum(self.config[s]["weight"] for s in self.enabled)
        signals = []

        if "rsi" in self.enabled:
            score, msg = self.rsi_signal(indicators["rsi"])
            weighted_sum += score * self.config["rsi"]["weight"]
            signals.append({"strategy": "RSI", "score": score, "message": msg})

        if "macd" in self.enabled:
            m = indicators["macd"]
            score, msg = self.macd_signal(m["histogram"])
            weighted_sum += score * self.config["macd"]["weight"]
            signals.append({"strategy": "MACD", "score": score, "message": msg})

        if "bollinger" in self.enabled:
            b = indicators["bollinger"]
            score, msg = self.bollinger_signal(indicators["current_price"], b["upper"], b["lower"])
            weighted_sum += score * self.config["bollinger"]["weight"]
            signals.append({"strategy": "BOLLINGER", "score": score, "message": msg})

        if "ma_crossover" in self.enabled:
            ma = indicators["moving_averages"]
            score, msg = self.ma_crossover_signal(
                ma["ma_fast"],
                ma["ma_slow"],
                ma["ma_fast_prev"],
                ma["ma_slow_prev"],
            )
            weighted_sum += score * self.config["ma_crossover"]["weight"]
            signals.append({"strategy": "MA_CROSSOVER", "score": score, "message": msg})

        total_score = weighted_sum / total_weight
        if total_score > 0.3:
            action, direction = "BUY", "做多"
        elif total_score < -0.3:
            action, direction = "SELL", "做空"
        else:
            action, direction = "HOLD", "观望"

        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "symbol": symbol,
            "current_price": indicators["current_price"],
            "total_score": total_score,
            "action": action,
            "direction": direction,
            "signals": signals,
            "risk_notes": self._risk_notes(total_score),
        }


def parse_strategies(raw: str):
    if raw.lower() == "all":
        return ["rsi", "macd", "bollinger", "ma_crossover"]
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--period", default="7d")
    parser.add_argument("--interval", default="1h")
    parser.add_argument(
        "--strategies",
        default="all",
        help="all 或逗号分隔: rsi,macd,bollinger,ma_crossover",
    )
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
    indicators = get_latest_indicators(data)
    generator = SignalGenerator(parse_strategies(args.strategies))
    result = generator.generate(args.symbol, indicators)

    print("\n=== BTC 量化分析报告 ===")
    print(f"时间: {result['timestamp']}")
    print(f"标的: {result['symbol']}")
    print(f"价格: ${result['current_price']:.2f}")
    print(f"综合评分: {result['total_score']:.2f}")
    print(f"建议: {result['action']} ({result['direction']})")
    print("--- 策略明细 ---")
    for s in result["signals"]:
        tag = "🟢" if s["score"] > 0 else ("🔴" if s["score"] < 0 else "⚪")
        print(f"{tag} {s['strategy']}: {s['message']}")
    print("--- 风险提示 ---")
    for note in result["risk_notes"]:
        print(f"- {note}")


if __name__ == "__main__":
    main()
