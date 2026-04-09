#!/usr/bin/env python3
"""模拟实盘：按信号全仓买卖，每次成交后打印盈亏与权益（非真实下单）。"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from fetch_price import fetch_price_data
from indicators import get_latest_indicators
from signal_generator import SignalGenerator, parse_strategies

CSV_HEADERS = [
    "seq",
    "timestamp",
    "symbol",
    "signal_action",
    "trade_side",
    "trade_reason",
    "price",
    "qty",
    "fee",
    "realized_trade",
    "realized_total",
    "cash_after",
    "position_qty_after",
    "equity_after",
    "unrealized_after",
    "source",
    "market_type",
    "strategies",
]
TRADES_CSV_PATH = os.path.join("data", "paper_trades.csv")


def setup_logger(log_dir: str) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("paper_trade")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    log_path = os.path.join(log_dir, "paper_trade.log")
    handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    logger.addHandler(handler)
    return logger


def ensure_csv(csv_path: str) -> None:
    csv_dir = os.path.dirname(csv_path)
    if csv_dir:
        os.makedirs(csv_dir, exist_ok=True)
    if os.path.exists(csv_path):
        return
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()


def append_trade_csv(
    csv_path: str,
    signal: dict,
    trade: dict,
    portfolio: "PaperPortfolio",
    source: str,
    market_type: str,
    strategies: str,
) -> None:
    price = float(signal["current_price"])
    row = {
        "seq": trade["seq"],
        "timestamp": signal["timestamp"],
        "symbol": signal["symbol"],
        "signal_action": signal["action"],
        "trade_side": trade["side"],
        "trade_reason": trade.get("reason", ""),
        "price": f"{trade['price']:.8f}",
        "qty": f"{trade['qty']:.8f}",
        "fee": f"{trade['fee']:.8f}",
        "realized_trade": f"{trade['realized_trade']:.8f}",
        "realized_total": f"{portfolio.realized_pnl:.8f}",
        "cash_after": f"{portfolio.cash:.8f}",
        "position_qty_after": f"{portfolio.qty:.8f}",
        "equity_after": f"{portfolio.equity(price):.8f}",
        "unrealized_after": f"{portfolio.unrealized_pnl(price):.8f}",
        "source": source,
        "market_type": market_type,
        "strategies": strategies,
    }
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writerow(row)


@dataclass
class PaperPortfolio:
    """现货、全进全出；手续费按成交额比例从现金/卖出所得中扣除。"""

    cash: float
    qty: float = 0.0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0
    commission: float = 0.001
    trade_seq: int = 0
    peak_price: float = 0.0
    history: list[dict] = field(default_factory=list)

    def equity(self, price: float) -> float:
        return self.cash + self.qty * price

    def unrealized_pnl(self, price: float) -> float:
        if self.qty <= 0:
            return 0.0
        return self.qty * price - self.qty * self.avg_cost

    def buy_all(self, price: float, ts: str, reason: str = "signal_buy") -> dict | None:
        if self.cash <= 0 or self.qty > 0:
            return None
        fee = self.cash * self.commission
        invest = self.cash - fee
        if invest <= 0:
            return None
        bought = invest / price
        self.trade_seq += 1
        rec = {
            "seq": self.trade_seq,
            "ts": ts,
            "side": "BUY",
            "reason": reason,
            "price": price,
            "qty": bought,
            "fee": fee,
            "realized_trade": 0.0,
        }
        self.qty = bought
        self.avg_cost = invest / bought
        self.peak_price = price
        self.cash = 0.0
        self.history.append(rec)
        return rec

    def sell_all(self, price: float, ts: str, reason: str = "signal_sell") -> dict | None:
        if self.qty <= 0:
            return None
        gross = self.qty * price
        fee = gross * self.commission
        proceeds = gross - fee
        cost = self.qty * self.avg_cost
        pnl = proceeds - cost
        self.realized_pnl += pnl
        self.trade_seq += 1
        rec = {
            "seq": self.trade_seq,
            "ts": ts,
            "side": "SELL",
            "reason": reason,
            "price": price,
            "qty": self.qty,
            "fee": fee,
            "realized_trade": pnl,
        }
        self.cash = proceeds
        self.qty = 0.0
        self.avg_cost = 0.0
        self.peak_price = 0.0
        self.history.append(rec)
        return rec


def run_tick(
    portfolio: PaperPortfolio,
    symbol: str,
    period: str,
    interval: str,
    source: str,
    market_type: str,
    strategies: list[str],
    trailing_stop_pct: float = 0.02,
) -> tuple[dict, dict | None]:
    data = fetch_price_data(
        symbol, period, interval, source=source, market_type=market_type
    )
    indicators = get_latest_indicators(data)
    gen = SignalGenerator(strategies)
    signal = gen.generate(symbol, indicators)
    price = float(signal["current_price"])
    action = signal["action"]
    ts = signal["timestamp"]

    trade: dict | None = None
    if portfolio.qty > 0:
        portfolio.peak_price = max(portfolio.peak_price, price)
        had_profit = portfolio.peak_price > portfolio.avg_cost
        drawdown_from_peak = (
            (portfolio.peak_price - price) / portfolio.peak_price
            if portfolio.peak_price > 0
            else 0.0
        )
        if had_profit and drawdown_from_peak >= trailing_stop_pct:
            trade = portfolio.sell_all(price, ts, reason="trailing_stop")
            return signal, trade

    if action == "BUY" and portfolio.qty <= 0 and portfolio.cash > 0:
        trade = portfolio.buy_all(price, ts, reason="signal_buy")
    elif action == "SELL" and portfolio.qty > 0:
        trade = portfolio.sell_all(price, ts, reason="signal_sell")

    return signal, trade


def print_after_tick(
    portfolio: PaperPortfolio,
    signal: dict,
    trade: dict | None,
    quote: str,
    logger: logging.Logger | None = None,
) -> None:
    def emit(msg: str) -> None:
        print(msg)
        if logger:
            logger.info(msg)

    price = signal["current_price"]
    eq = portfolio.equity(price)
    ur = portfolio.unrealized_pnl(price)

    emit(f"\n{'='*50}")
    emit(f"时间: {signal['timestamp']}  标的: {signal['symbol']}  价: {quote}{price:,.2f}")
    emit(f"信号: {signal['action']} ({signal['direction']})  综合分: {signal['total_score']:.3f}")

    if trade:
        side = trade["side"]
        emit(f"\n>>> 模拟成交 #{trade['seq']}: {side} ({trade.get('reason', '-')})")
        emit(f"    数量: {trade['qty']:.8f}  手续费: {quote}{trade['fee']:,.2f}")
        if side == "SELL":
            emit(f"    本笔已实现盈亏: {quote}{trade['realized_trade']:+,.2f}")
        emit(f"    累计已实现盈亏: {quote}{portfolio.realized_pnl:+,.2f}")
    elif signal["action"] in ("BUY", "SELL"):
        why = (
            "已有持仓，忽略重复买入"
            if signal["action"] == "BUY" and portfolio.qty > 0
            else "空仓，忽略卖出"
            if signal["action"] == "SELL" and portfolio.qty <= 0
            else "无可用资金"
        )
        emit(f"\n>>> 未成交: {why}")

    emit(f"\n--- 账户快照 ---")
    emit(f"现金: {quote}{portfolio.cash:,.2f}  持仓: {portfolio.qty:.8f}")
    emit(f"总权益: {quote}{eq:,.2f}  浮动盈亏: {quote}{ur:+,.2f}")
    emit(f"累计已实现: {quote}{portfolio.realized_pnl:+,.2f}")
    emit(f"交易次数: {portfolio.trade_seq}（每笔买入或卖出各计 1 次）")


def main():
    parser = argparse.ArgumentParser(
        description="按 signal_generator 规则模拟买卖；每次操作后打印盈亏。"
    )
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--period", default="7d")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--strategies", default="all")
    parser.add_argument("--source", default="okx", choices=["yfinance", "okx"])
    parser.add_argument("--market-type", default="SPOT", choices=["SPOT", "SWAP"])
    parser.add_argument("--capital", type=float, default=10_000.0, help="初始现金（名义 USDT/USD）")
    parser.add_argument("--commission", type=float, default=0.001, help="手续费率，如 0.001=0.1%%")
    parser.add_argument(
        "--trailing-stop-pct",
        type=float,
        default=0.02,
        help="移动止盈回撤阈值（默认 0.02 = 2%）",
    )
    parser.add_argument("--once", action="store_true", help="只跑一轮（拉一次行情 + 判断一次）")
    parser.add_argument(
        "--sleep",
        type=int,
        default=300,
        metavar="SEC",
        help="循环模式下每轮间隔秒数（默认 300）",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=0,
        help="最多跑几轮，0 表示不限制（需 Ctrl+C 退出）",
    )
    parser.add_argument(
        "--log-dir",
        default="logs",
        help="日志目录（按天轮转，保留 7 天）",
    )
    args = parser.parse_args()
    strategies = parse_strategies(args.strategies)
    logger = setup_logger(args.log_dir)
    ensure_csv(TRADES_CSV_PATH)

    quote = "$"
    portfolio = PaperPortfolio(
        cash=float(args.capital), commission=float(args.commission)
    )

    start_msg = (
        f"模拟盘启动 | 本金 {quote}{args.capital:,.2f} | 手续费 {args.commission*100:.3f}% | "
        f"数据源 {args.source} | 策略 {args.strategies} | 移动止盈回撤 {args.trailing_stop_pct*100:.2f}%"
    )
    print(start_msg)
    print("说明: BUY 且空仓时用全部现金买入；SELL 且持仓时全部卖出。HOLD 不交易。")
    print(f"日志文件: {os.path.join(args.log_dir, 'paper_trade.log')}（按天轮转，保留 7 天）")
    print(f"成交 CSV: {TRADES_CSV_PATH}")
    logger.info(start_msg)
    logger.info("说明: BUY 且空仓时用全部现金买入；SELL 且持仓时全部卖出。HOLD 不交易。")
    logger.info("成交 CSV: %s", TRADES_CSV_PATH)

    round_no = 0
    while True:
        round_no += 1
        try:
            signal, trade = run_tick(
                portfolio,
                args.symbol,
                args.period,
                args.interval,
                args.source,
                args.market_type,
                strategies,
                trailing_stop_pct=float(args.trailing_stop_pct),
            )
        except Exception as e:
            print(f"\n[错误] 拉取或计算失败: {e}", file=sys.stderr)
            logger.exception("拉取或计算失败: %s", e)
            if args.once:
                sys.exit(1)
            time.sleep(min(args.sleep, 60))
            continue

        print_after_tick(portfolio, signal, trade, quote, logger=logger)
        if trade:
            append_trade_csv(
                TRADES_CSV_PATH,
                signal,
                trade,
                portfolio,
                source=args.source,
                market_type=args.market_type,
                strategies=args.strategies,
            )
            logger.info("已写入成交 CSV: seq=%s side=%s", trade["seq"], trade["side"])

        if args.once:
            break
        if args.max_rounds and round_no >= args.max_rounds:
            print(f"\n已达 --max-rounds={args.max_rounds}，结束。")
            logger.info("已达 --max-rounds=%s，结束。", args.max_rounds)
            break
        print(f"\n{args.sleep}s 后进行下一轮 (第 {round_no + 1} 轮)...")
        logger.info("%ss 后进行下一轮 (第 %s 轮)...", args.sleep, round_no + 1)
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
