#!/usr/bin/env python3
"""Abstract data source for OHLCV."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class DataSource(ABC):
    """统一行情入口：各实现返回相同结构的 DataFrame。"""

    @abstractmethod
    def fetch(self, symbol: str, interval: str, period: str) -> pd.DataFrame:
        """
        拉取 OHLCV。

        Parameters
        ----------
        symbol : str
            项目统一符号（见 OKX_DATA_INTEGRATION.md 第 3.3 节）。
        interval : str
            如 1m, 5m, 15m, 1h, 4h, 1d。
        period : str
            如 7d, 30d, 180d（与 yfinance 风格一致；OKX 实现暂要求 *d 形式）。
        """
        raise NotImplementedError


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """统一列名、索引、排序、去重。"""
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"OHLCV 缺少列: {missing}")

    out = df[required].copy()
    for c in required:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(how="any")
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, utc=True)
    else:
        if out.index.tz is None:
            out.index = out.index.tz_localize("UTC")
        else:
            out.index = out.index.tz_convert("UTC")
    out = out[~out.index.duplicated(keep="last")]
    out = out.sort_index()
    return out
