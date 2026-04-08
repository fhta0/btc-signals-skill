#!/usr/bin/env python3
"""OKX public market data (no API key)."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

from .base import DataSource, normalize_ohlcv

OKX_API = "https://www.okx.com/api/v5/market/candles"

# yfinance 风格 -> OKX bar
INTERVAL_TO_BAR = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "2h": "2H",
    "4h": "4H",
    "6h": "6H",
    "12h": "12H",
    "1d": "1D",
    "1w": "1W",
}

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 经人工验证的 Yahoo 风格 *-USD 展示符号；其它报价（如 BUSD）须显式使用 OKX 原生 BASE-USDT
_OKX_VERIFIED_USD_DISPLAY = frozenset({"BTC-USD", "ETH-USD"})
_RE_SPOT_USDT = re.compile(r"^[A-Z0-9]+-USDT$")
_RE_SWAP_INST = re.compile(r"^[A-Z0-9]+-USDT-SWAP$")


def resolve_okx_inst_id(symbol: str, market_type: str = "SPOT") -> str:
    """
    将项目统一符号解析为 OKX instId。

    约定（与文档一致）：CLI 使用 BTC-USD；OKX SPOT 映射为 BTC-USDT，
    SWAP 映射为 BTC-USDT-SWAP。未在白名单的 *-USD 或非 USDT 报价会显式报错。
    """
    s = symbol.strip().upper()
    mt = market_type.strip().upper()

    if s.endswith("-SWAP"):
        if not _RE_SWAP_INST.fullmatch(s):
            raise ValueError(
                f"OKX SWAP instId 须为 BASE-USDT-SWAP，收到: {symbol!r}"
            )
        return s

    if _RE_SPOT_USDT.fullmatch(s):
        base_quote = s
    elif s.endswith("-USD") and not s.endswith("-USDT"):
        if s not in _OKX_VERIFIED_USD_DISPLAY:
            raise ValueError(
                f"OKX 未验证的 *-USD 展示符号: {symbol!r}；当前允许: {sorted(_OKX_VERIFIED_USD_DISPLAY)}"
            )
        base_quote = s.replace("-USD", "-USDT", 1)
    else:
        raise ValueError(
            f"OKX 不支持的符号: {symbol!r}；请使用 BTC-USD/ETH-USD 或原生 BASE-USDT"
        )

    if mt == "SWAP":
        if base_quote.endswith("-USDT"):
            return f"{base_quote}-SWAP"
        return f"{base_quote}-USDT-SWAP"
    return base_quote


def _parse_period_days(period: str) -> int:
    m = re.fullmatch(r"(\d+)d", period.strip().lower())
    if not m:
        raise ValueError(
            f"OKX 数据源暂仅支持 period 形如 7d/30d/180d，收到: {period!r}"
        )
    return int(m.group(1))


def _http_get_json(url: str, timeout: float = 30.0) -> dict:
    """公开接口偶发抖动时做有限次重试（指数退避）；最终失败包装为 ValueError。"""
    for attempt in range(3):
        req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if attempt == 2:
                raise ValueError(f"OKX HTTP 错误: {e.code} {e.reason}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == 2:
                raise ValueError(f"OKX 网络错误: {e}") from e
        time.sleep(2**attempt)
    raise RuntimeError("_http_get_json: unreachable")


class OKXSource(DataSource):
    """公开 K 线；向更早历史分页使用 after（毫秒）；单次 limit 最大 300。"""

    def __init__(self, market_type: str = "SPOT"):
        self.market_type = market_type

    def fetch(self, symbol: str, interval: str, period: str) -> pd.DataFrame:
        bar = INTERVAL_TO_BAR.get(interval)
        if not bar:
            raise ValueError(f"不支持的 interval: {interval!r}，可选: {sorted(INTERVAL_TO_BAR)}")

        inst_id = resolve_okx_inst_id(symbol, self.market_type)
        days = _parse_period_days(period)
        now = datetime.now(timezone.utc)
        start_ms = int((now - timedelta(days=days)).timestamp() * 1000)

        # OKX 文档：after = 返回早于该时间戳（毫秒）的 K 线；before = 返回新于该时间戳的 K 线。
        # 响应默认按时间倒序。向更早历史翻页应使用 after=当前批次中最老一根的 ts。
        rows: list[list[str]] = []
        after_ts: str | None = None
        max_pages = 500

        for _ in range(max_pages):
            params: dict[str, str] = {
                "instId": inst_id,
                "bar": bar,
                "limit": "300",
            }
            if after_ts is not None:
                params["after"] = after_ts

            url = f"{OKX_API}?{urllib.parse.urlencode(params)}"
            payload = _http_get_json(url)

            if payload.get("code") != "0":
                raise ValueError(
                    f"OKX 业务错误: code={payload.get('code')} msg={payload.get('msg')}"
                )

            batch = payload.get("data") or []
            if not batch:
                break

            rows.extend(batch)
            ts_ms = [int(r[0]) for r in batch]
            oldest = min(ts_ms)
            # 用 < 而非 <=：最老一根恰等于 start_ms 时仍继续翻页，避免同 ts 重复批次导致提前截断
            if oldest < start_ms:
                break
            after_ts = str(oldest)

        if not rows:
            raise ValueError(
                f"未获取到 OKX 数据: instId={inst_id}, bar={bar}, period={period}"
            )

        seen: set[int] = set()
        filtered: list[list[str]] = []
        for r in rows:
            t = int(r[0])
            if t < start_ms:
                continue
            if t in seen:
                continue
            seen.add(t)
            filtered.append(r)

        if not filtered:
            raise ValueError(
                f"OKX 在选定时间范围内无 K 线: instId={inst_id}, period={period}"
            )

        filtered.sort(key=lambda r: int(r[0]))

        idx = pd.to_datetime([int(r[0]) for r in filtered], unit="ms", utc=True)
        df = pd.DataFrame(
            {
                "Open": [r[1] for r in filtered],
                "High": [r[2] for r in filtered],
                "Low": [r[3] for r in filtered],
                "Close": [r[4] for r in filtered],
                "Volume": [r[5] for r in filtered],
            },
            index=idx,
        )
        return normalize_ohlcv(df)
