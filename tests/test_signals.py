"""Tests for scripts/signal_generator.py"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from signal_generator import SignalGenerator, parse_strategies


# ── parse_strategies ──────────────────────────────────────────────────────────

class TestParseStrategies:
    ALL = ["rsi", "macd", "bollinger", "ma_crossover"]

    def test_all_returns_all_four(self):
        assert parse_strategies("all") == self.ALL

    def test_all_case_insensitive(self):
        assert parse_strategies("ALL") == self.ALL
        assert parse_strategies("All") == self.ALL

    def test_comma_separated(self):
        assert parse_strategies("rsi,macd") == ["rsi", "macd"]

    def test_strips_whitespace(self):
        assert parse_strategies("rsi, macd , bollinger") == ["rsi", "macd", "bollinger"]

    def test_lowercases_input(self):
        assert parse_strategies("RSI,MACD") == ["rsi", "macd"]

    def test_empty_tokens_ignored(self):
        assert parse_strategies("rsi,,macd") == ["rsi", "macd"]


# ── SignalGenerator 初始化 ────────────────────────────────────────────────────

class TestSignalGeneratorInit:
    def test_invalid_strategies_raises(self):
        with pytest.raises(ValueError):
            SignalGenerator(["invalid_strategy"])

    def test_mixed_valid_invalid_keeps_valid(self):
        sg = SignalGenerator(["rsi", "nonexistent"])
        assert sg.enabled == ["rsi"]

    def test_none_defaults_to_all(self):
        sg = SignalGenerator(None)
        assert set(sg.enabled) == {"rsi", "macd", "bollinger", "ma_crossover"}


# ── 各策略信号只返回 {-1, 0, 1} ──────────────────────────────────────────────

class TestIndividualSignalScores:
    sg = SignalGenerator()

    def test_rsi_buy_signal(self):
        score, _ = self.sg.rsi_signal(25.0)
        assert score == 1

    def test_rsi_sell_signal(self):
        score, _ = self.sg.rsi_signal(75.0)
        assert score == -1

    def test_rsi_neutral_signal(self):
        score, _ = self.sg.rsi_signal(50.0)
        assert score == 0

    def test_macd_buy_signal(self):
        score, _ = SignalGenerator.macd_signal(0.5)
        assert score == 1

    def test_macd_sell_signal(self):
        score, _ = SignalGenerator.macd_signal(-0.5)
        assert score == -1

    def test_macd_neutral_signal(self):
        score, _ = SignalGenerator.macd_signal(0.0)
        assert score == 0

    def test_bollinger_buy_signal(self):
        score, _ = SignalGenerator.bollinger_signal(99.0, 110.0, 100.0)
        assert score == 1

    def test_bollinger_sell_signal(self):
        score, _ = SignalGenerator.bollinger_signal(111.0, 110.0, 100.0)
        assert score == -1

    def test_bollinger_neutral_signal(self):
        score, _ = SignalGenerator.bollinger_signal(105.0, 110.0, 100.0)
        assert score == 0

    def test_ma_crossover_buy_signal(self):
        score, _ = SignalGenerator.ma_crossover_signal(10.0, 9.0)
        assert score == 1

    def test_ma_crossover_sell_signal(self):
        score, _ = SignalGenerator.ma_crossover_signal(9.0, 10.0)
        assert score == -1

    def test_ma_crossover_neutral_signal(self):
        score, _ = SignalGenerator.ma_crossover_signal(10.0, 10.0)
        assert score == 0


# ── generate() 综合输出 ───────────────────────────────────────────────────────

def make_indicators(rsi=50.0, macd_hist=0.0, price=100.0, upper=110.0, lower=90.0,
                    ma_fast=10.0, ma_slow=10.0):
    return {
        "current_price": price,
        "rsi": rsi,
        "macd": {"macd_line": 0.0, "signal_line": 0.0, "histogram": macd_hist},
        "bollinger": {"upper": upper, "middle": 100.0, "lower": lower},
        "moving_averages": {"ma_fast": ma_fast, "ma_slow": ma_slow},
    }


class TestGenerate:
    def test_total_score_in_range(self):
        sg = SignalGenerator()
        for _ in range(20):
            rng = np.random.default_rng()
            ind = make_indicators(
                rsi=float(rng.uniform(0, 100)),
                macd_hist=float(rng.uniform(-1, 1)),
                ma_fast=float(rng.uniform(9, 11)),
                ma_slow=10.0,
            )
            result = sg.generate("BTC-USD", ind)
            assert -1.0 <= result["total_score"] <= 1.0

    def test_action_buy_when_all_bullish(self):
        sg = SignalGenerator()
        ind = make_indicators(rsi=20.0, macd_hist=1.0, price=89.0, upper=110.0, lower=90.0,
                              ma_fast=11.0, ma_slow=10.0)
        result = sg.generate("BTC-USD", ind)
        assert result["action"] == "BUY"
        assert result["direction"] == "做多"

    def test_action_sell_when_all_bearish(self):
        sg = SignalGenerator()
        ind = make_indicators(rsi=80.0, macd_hist=-1.0, price=111.0, upper=110.0, lower=90.0,
                              ma_fast=9.0, ma_slow=10.0)
        result = sg.generate("BTC-USD", ind)
        assert result["action"] == "SELL"
        assert result["direction"] == "做空"

    def test_action_hold_when_neutral(self):
        sg = SignalGenerator()
        ind = make_indicators()  # 全部中性
        result = sg.generate("BTC-USD", ind)
        assert result["action"] == "HOLD"

    def test_output_fields_complete(self):
        sg = SignalGenerator()
        result = sg.generate("BTC-USD", make_indicators())
        for field in ("timestamp", "symbol", "current_price", "total_score",
                      "action", "direction", "signals", "risk_notes"):
            assert field in result

    def test_signals_count_matches_enabled(self):
        sg = SignalGenerator(["rsi", "macd"])
        result = sg.generate("BTC-USD", make_indicators())
        assert len(result["signals"]) == 2

    def test_symbol_passed_through(self):
        sg = SignalGenerator()
        result = sg.generate("ETH-USD", make_indicators())
        assert result["symbol"] == "ETH-USD"

    def test_risk_notes_is_list(self):
        sg = SignalGenerator()
        result = sg.generate("BTC-USD", make_indicators())
        assert isinstance(result["risk_notes"], list)
        assert len(result["risk_notes"]) >= 1
