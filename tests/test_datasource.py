"""DataSource 与符号映射（离线）。"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from datasource.base import normalize_ohlcv
from datasource.okx_source import resolve_okx_inst_id


class TestResolveOkxInstId:
    def test_btc_usd_spot(self):
        assert resolve_okx_inst_id("BTC-USD", "SPOT") == "BTC-USDT"

    def test_eth_usd_spot(self):
        assert resolve_okx_inst_id("ETH-USD", "SPOT") == "ETH-USDT"

    def test_btc_usd_swap(self):
        assert resolve_okx_inst_id("BTC-USD", "SWAP") == "BTC-USDT-SWAP"

    def test_btc_usdt_swap(self):
        assert resolve_okx_inst_id("BTC-USDT", "SWAP") == "BTC-USDT-SWAP"

    def test_sol_usdt_spot_passthrough(self):
        assert resolve_okx_inst_id("SOL-USDT", "SPOT") == "SOL-USDT"

    def test_already_swap(self):
        assert resolve_okx_inst_id("BTC-USDT-SWAP", "SWAP") == "BTC-USDT-SWAP"

    def test_unverified_usd_raises(self):
        with pytest.raises(ValueError, match="未验证"):
            resolve_okx_inst_id("SOL-USD", "SPOT")

    def test_busd_raises(self):
        with pytest.raises(ValueError, match="不支持"):
            resolve_okx_inst_id("BTC-BUSD", "SPOT")

    def test_invalid_swap_suffix_raises(self):
        with pytest.raises(ValueError, match="须为 BASE-USDT-SWAP"):
            resolve_okx_inst_id("BTC-SWAP", "SPOT")


class TestNormalizeOhlcv:
    def test_sorts_and_dedupes(self):
        idx = pd.to_datetime(
            ["2024-01-03", "2024-01-01", "2024-01-02", "2024-01-01"],
            utc=True,
        )
        df = pd.DataFrame(
            {
                "Open": [1, 2, 3, 99],
                "High": [1, 2, 3, 99],
                "Low": [1, 2, 3, 99],
                "Close": [1, 2, 3, 99],
                "Volume": [10, 20, 30, 999],
            },
            index=idx,
        )
        out = normalize_ohlcv(df)
        assert list(out.index) == sorted(out.index)
        assert len(out) == 3


@pytest.mark.integration
def test_okx_fetch_smoke():
    """可选：需要网络；运行 pytest -m integration"""
    from datasource import fetch_ohlcv

    df = fetch_ohlcv("BTC-USD", "1h", "3d", source="okx", market_type="SPOT")
    assert not df.empty
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
