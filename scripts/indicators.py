#!/usr/bin/env python3
"""Technical indicator calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_rsi(data, period: int = 14):
    delta = data["Close"].diff()
    gain = delta.where(delta > 0, 0.0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_macd(data, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = data["Close"].ewm(span=fast, adjust=False).mean()
    ema_slow = data["Close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def calculate_bollinger_bands(data, period: int = 20, std_dev: float = 2):
    middle = data["Close"].rolling(window=period).mean()
    std = data["Close"].rolling(window=period).std()
    upper = middle + std * std_dev
    lower = middle - std * std_dev
    return upper, middle, lower


def calculate_moving_averages(data, fast: int = 9, slow: int = 21):
    ma_fast = data["Close"].rolling(window=fast).mean()
    ma_slow = data["Close"].rolling(window=slow).mean()
    return ma_fast, ma_slow


def get_latest_indicators(data):
    rsi = calculate_rsi(data)
    macd_line, signal_line, hist = calculate_macd(data)
    upper, middle, lower = calculate_bollinger_bands(data)
    ma_fast, ma_slow = calculate_moving_averages(data)

    idx = -1
    prev_idx = -2 if len(data) >= 2 else -1
    rsi_val = rsi.iloc[idx]
    # 连续上涨等场景下 loss→0 会导致 RSI 为 NaN；与全涨语义一致时视为 100，避免 float 转换与下游信号异常
    rsi_out = 100.0 if pd.isna(rsi_val) else float(rsi_val)

    return {
        "current_price": float(data["Close"].iloc[idx]),
        "rsi": rsi_out,
        "macd": {
            "macd_line": float(macd_line.iloc[idx]),
            "signal_line": float(signal_line.iloc[idx]),
            "histogram": float(hist.iloc[idx]),
        },
        "bollinger": {
            "upper": float(upper.iloc[idx]),
            "middle": float(middle.iloc[idx]),
            "lower": float(lower.iloc[idx]),
        },
        "moving_averages": {
            "ma_fast": float(ma_fast.iloc[idx]),
            "ma_slow": float(ma_slow.iloc[idx]),
            "ma_fast_prev": float(ma_fast.iloc[prev_idx]),
            "ma_slow_prev": float(ma_slow.iloc[prev_idx]),
        },
    }
