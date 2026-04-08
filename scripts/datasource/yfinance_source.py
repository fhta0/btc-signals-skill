#!/usr/bin/env python3
"""Yahoo Finance data source."""

from __future__ import annotations

from datetime import datetime, timedelta

import yfinance as yf

from .base import DataSource, normalize_ohlcv


class YFinanceSource(DataSource):
    def fetch(self, symbol: str, interval: str, period: str):
        ticker = yf.Ticker(symbol)
        if period.endswith("d"):
            days = int(period[:-1])
            start = datetime.now() - timedelta(days=days)
            data = ticker.history(start=start, interval=interval)
        else:
            data = ticker.history(period=period, interval=interval)

        if data.empty:
            raise ValueError(
                f"未获取到数据: symbol={symbol}, period={period}, interval={interval}"
            )

        df = data.copy()
        if "Volume" not in df.columns and "Vol" in df.columns:
            df = df.rename(columns={"Vol": "Volume"})
        cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        if len(cols) != 5:
            raise ValueError(f"yfinance 返回列不完整: {list(df.columns)}")
        df = df[cols]
        return normalize_ohlcv(df)
