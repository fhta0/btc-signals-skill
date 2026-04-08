#!/usr/bin/env python3
"""行情数据源工厂。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import DataSource

_REGISTRY_KEYS = frozenset({"yfinance", "okx"})


def get_data_source(name: str, **kwargs: Any) -> DataSource:
    key = name.lower().strip()
    if key not in _REGISTRY_KEYS:
        raise ValueError(f"未知数据源: {name!r}，可选: {sorted(_REGISTRY_KEYS)}")
    if key == "yfinance":
        from .yfinance_source import YFinanceSource

        return YFinanceSource()
    from .okx_source import OKXSource

    return OKXSource(market_type=str(kwargs.get("market_type", "SPOT")))


def fetch_ohlcv(
    symbol: str,
    interval: str,
    period: str,
    source: str = "yfinance",
    **kwargs: Any,
) -> pd.DataFrame:
    """统一入口：indicators / signal / backtest 只依赖此函数即可切换数据源。"""
    ds = get_data_source(source, **kwargs)
    return ds.fetch(symbol, interval, period)


__all__ = [
    "DataSource",
    "get_data_source",
    "fetch_ohlcv",
]
