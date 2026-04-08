"""Tests for scripts/indicators.py"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from indicators import (
    calculate_bollinger_bands,
    calculate_macd,
    calculate_moving_averages,
    calculate_rsi,
    get_latest_indicators,
)


def make_df(prices: list) -> pd.DataFrame:
    return pd.DataFrame({"Close": prices})


# ── RSI ──────────────────────────────────────────────────────────────────────

class TestRSI:
    def test_all_gains_approaches_100(self):
        # 价格持续上涨，RSI 应趋近 100（loss=0 时结果为 NaN，数学上等价于 100）
        prices = [100 + i for i in range(60)]
        rsi = calculate_rsi(make_df(prices))
        assert pd.isna(rsi.iloc[-1]) or rsi.iloc[-1] > 95

    def test_all_losses_approaches_0(self):
        # 价格持续下跌，RSI 应趋近 0
        prices = [100 - i for i in range(60)]
        rsi = calculate_rsi(make_df(prices))
        assert rsi.iloc[-1] < 5

    def test_flat_market_is_nan_or_50(self):
        # 价格不变，gain=loss=0，RSI 应为 NaN（除零）
        prices = [100.0] * 30
        rsi = calculate_rsi(make_df(prices))
        assert np.isnan(rsi.iloc[-1]) or 45 <= rsi.iloc[-1] <= 55

    def test_output_range_0_to_100(self):
        rng = np.random.default_rng(42)
        prices = 100 + rng.normal(0, 5, 100).cumsum()
        rsi = calculate_rsi(make_df(prices.tolist()))
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_insufficient_data_returns_nan(self):
        # 数据不足 period，应返回 NaN
        rsi = calculate_rsi(make_df([100.0] * 5), period=14)
        assert rsi.dropna().empty


# ── MACD ─────────────────────────────────────────────────────────────────────

class TestMACD:
    def setup_method(self):
        rng = np.random.default_rng(0)
        prices = 100 + rng.normal(0, 2, 100).cumsum()
        self.df = make_df(prices.tolist())

    def test_output_length_matches_input(self):
        macd_line, signal_line, hist = calculate_macd(self.df)
        assert len(macd_line) == len(self.df)
        assert len(signal_line) == len(self.df)
        assert len(hist) == len(self.df)

    def test_histogram_equals_macd_minus_signal(self):
        macd_line, signal_line, hist = calculate_macd(self.df)
        diff = (macd_line - signal_line - hist).dropna().abs()
        assert (diff < 1e-10).all()

    def test_last_value_is_not_nan(self):
        macd_line, signal_line, hist = calculate_macd(self.df)
        assert not np.isnan(macd_line.iloc[-1])
        assert not np.isnan(signal_line.iloc[-1])
        assert not np.isnan(hist.iloc[-1])


# ── Bollinger Bands ───────────────────────────────────────────────────────────

class TestBollingerBands:
    def setup_method(self):
        rng = np.random.default_rng(1)
        prices = 100 + rng.normal(0, 1, 60).cumsum()
        self.df = make_df(prices.tolist())

    def test_upper_gt_middle_gt_lower(self):
        upper, middle, lower = calculate_bollinger_bands(self.df)
        valid = upper.dropna().index
        assert (upper[valid] > middle[valid]).all()
        assert (middle[valid] > lower[valid]).all()

    def test_output_length_matches_input(self):
        upper, middle, lower = calculate_bollinger_bands(self.df)
        assert len(upper) == len(self.df)

    def test_middle_is_rolling_mean(self):
        upper, middle, lower = calculate_bollinger_bands(self.df, period=20)
        expected = self.df["Close"].rolling(20).mean()
        diff = (middle - expected).dropna().abs()
        assert (diff < 1e-10).all()


# ── Moving Averages ───────────────────────────────────────────────────────────

class TestMovingAverages:
    def test_fast_reacts_faster_than_slow(self):
        # 价格大幅拉升后，快线应高于慢线
        # 用 15 根 K 线：fast(9) 已完全收敛到 200，slow(21) 仍有历史权重拖累
        prices = [100.0] * 30 + [200.0] * 15
        ma_fast, ma_slow = calculate_moving_averages(make_df(prices), fast=9, slow=21)
        assert ma_fast.iloc[-1] > ma_slow.iloc[-1]

    def test_output_length_matches_input(self):
        prices = list(range(1, 51))
        ma_fast, ma_slow = calculate_moving_averages(make_df(prices))
        assert len(ma_fast) == 50
        assert len(ma_slow) == 50


# ── get_latest_indicators ─────────────────────────────────────────────────────

class TestGetLatestIndicators:
    def setup_method(self):
        rng = np.random.default_rng(7)
        prices = 100 + rng.normal(0, 2, 100).cumsum()
        self.df = make_df(prices.tolist())

    def test_required_keys_present(self):
        result = get_latest_indicators(self.df)
        assert "current_price" in result
        assert "rsi" in result
        assert "macd" in result
        assert "bollinger" in result
        assert "moving_averages" in result

    def test_all_values_are_floats(self):
        result = get_latest_indicators(self.df)
        assert isinstance(result["current_price"], float)
        assert isinstance(result["rsi"], float)
        for v in result["macd"].values():
            assert isinstance(v, float)
        for v in result["bollinger"].values():
            assert isinstance(v, float)
        for v in result["moving_averages"].values():
            assert isinstance(v, float)

    def test_rsi_nan_latest_maps_to_100(self):
        # 若末端 RSI 为 NaN（如连续上涨 loss→0），应映射为 100；否则保持数值
        prices = [100 + i for i in range(60)]
        df = make_df(prices)
        raw = calculate_rsi(df).iloc[-1]
        out = get_latest_indicators(df)["rsi"]
        if pd.isna(raw):
            assert out == 100.0
        else:
            assert out == float(raw)

    def test_rsi_flat_when_nan_is_100(self):
        df = make_df([100.0] * 50)
        raw = calculate_rsi(df).iloc[-1]
        if pd.isna(raw):
            assert get_latest_indicators(df)["rsi"] == 100.0
