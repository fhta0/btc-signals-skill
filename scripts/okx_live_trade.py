#!/usr/bin/env python3
"""OKX 实盘/模拟盘执行器：根据信号下市价单（默认模拟盘）。"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler

SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from datasource.okx_source import resolve_okx_inst_id
from fetch_price import fetch_price_data
from indicators import get_latest_indicators
from signal_generator import SignalGenerator, parse_strategies

ORDER_CSV_PATH = os.path.join("data", "okx_orders.csv")
ORDER_HEADERS = [
    "ts",
    "symbol",
    "inst_id",
    "signal_action",
    "score",
    "side",
    "size",
    "price_snapshot",
    "order_id",
    "state",
    "simulated",
]


def load_dotenv(dotenv_path: str) -> None:
    """轻量 .env 读取器：仅解析 KEY=VALUE，且不覆盖已存在环境变量。"""
    if not os.path.exists(dotenv_path):
        return
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def setup_logger(log_dir: str) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("okx_live_trade")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "okx_live_trade.log"),
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
    parent = os.path.dirname(csv_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(csv_path):
        return
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=ORDER_HEADERS).writeheader()


def append_order_csv(csv_path: str, row: dict) -> None:
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=ORDER_HEADERS).writerow(row)


class OkxClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        simulated: bool = True,
        base_url: str = "https://www.okx.com",
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.simulated = simulated
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._server_time_offset: float = 0.0  # 时间偏移（秒）
        self._last_sync_time: float = 0.0  # 上次同步时间戳
        self._sync_interval: float = 300.0  # 每 5 分钟重新同步
        self._has_synced: bool = False  # 是否已同步过

    def _sync_server_time(self) -> float:
        """同步 OKX 服务器时间，返回偏移量（秒）。失败时返回 0（使用本地时间）。"""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/v5/public/time",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
                # 校验响应格式
                if data.get("code") != "0" or not data.get("data"):
                    logging.warning("OKX 时间接口返回异常: %s", data)
                    return 0.0
                ts_field = data["data"][0].get("ts")
                if not ts_field:
                    logging.warning("OKX 时间接口缺少 ts 字段: %s", data)
                    return 0.0
                server_ts_ms = int(ts_field)
                local_ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                return (server_ts_ms - local_ts_ms) / 1000
        except Exception as e:
            logging.warning("同步 OKX 服务器时间失败，使用本地时间: %s", e)
            return 0.0

    def _get_server_time(self) -> str:
        """获取 OKX 服务器时间，避免本地时间偏差导致签名过期。"""
        now_ts = datetime.now(timezone.utc).timestamp()

        # 首次同步或每 N 分钟重新同步一次
        if not self._has_synced or (now_ts - self._last_sync_time) >= self._sync_interval:
            self._server_time_offset = self._sync_server_time()
            self._last_sync_time = now_ts
            self._has_synced = True

        # 使用偏移后的本地时间
        adjusted_ts = now_ts + self._server_time_offset
        return datetime.fromtimestamp(adjusted_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _sign(self, ts: str, method: str, path: str, body: str) -> str:
        prehash = f"{ts}{method}{path}{body}"
        digest = hmac.new(
            self.api_secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode()

    def _request(
        self, method: str, path: str, params: dict | None = None, payload: dict | None = None
    ) -> dict:
        q = ""
        if params:
            q = "?" + urllib.parse.urlencode(params)
        full_path = f"{path}{q}"
        url = f"{self.base_url}{full_path}"
        body = json.dumps(payload) if payload else ""
        ts = self._get_server_time()
        sign = self._sign(ts, method.upper(), full_path, body)
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        if self.simulated:
            headers["x-simulated-trading"] = "1"

        req = urllib.request.Request(
            url=url,
            data=body.encode("utf-8") if body else None,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 时间戳错误时强制重新同步并重试一次
            if e.code == 401:
                err_body = e.read().decode("utf-8")
                try:
                    err_data = json.loads(err_body)
                    if err_data.get("code") in ("50102", "50103"):  # Timestamp request expired / Invalid timestamp
                        logging.warning("OKX 时间戳错误，强制重新同步: %s", err_data)
                        self._server_time_offset = self._sync_server_time()
                        self._last_sync_time = datetime.now(timezone.utc).timestamp()
                        self._has_synced = True
                        # 重试一次
                        ts2 = self._get_server_time()
                        sign2 = self._sign(ts2, method.upper(), full_path, body)
                        headers["OK-ACCESS-TIMESTAMP"] = ts2
                        headers["OK-ACCESS-SIGN"] = sign2
                        req2 = urllib.request.Request(
                            url=url,
                            data=body.encode("utf-8") if body else None,
                            headers=headers,
                            method=method.upper(),
                        )
                        with urllib.request.urlopen(req2, timeout=self.timeout) as resp2:
                            return json.loads(resp2.read().decode("utf-8"))
                except json.JSONDecodeError:
                    pass
                # 重试失败或非时间戳错误，抛出原始异常
                raise ValueError(f"OKX HTTP 错误: {e.code} {e.reason}") from e
            raise ValueError(f"OKX HTTP 错误: {e.code} {e.reason}") from e

    def account_balance(self) -> dict:
        return self._request("GET", "/api/v5/account/balance")

    def trade_account_balance(self, ccy: str = "USDT") -> float:
        payload = self.account_balance()
        if payload.get("code") != "0":
            raise ValueError(f"查询余额失败: {payload}")
        details = payload.get("data", [{}])[0].get("details", [])
        for d in details:
            if d.get("ccy") == ccy:
                return float(d.get("availBal") or 0.0)
        return 0.0

    def asset_balance(self, ccy: str) -> float:
        payload = self.account_balance()
        if payload.get("code") != "0":
            raise ValueError(f"查询余额失败: {payload}")
        details = payload.get("data", [{}])[0].get("details", [])
        for d in details:
            if d.get("ccy") == ccy:
                return float(d.get("availBal") or 0.0)
        return 0.0

    def place_spot_market_order(self, inst_id: str, side: str, sz: str) -> dict:
        body: dict[str, str] = {
            "instId": inst_id,
            "tdMode": "cash",
            "side": side,
            "ordType": "market",
            "sz": sz,
        }
        if side == "buy":
            body["tgtCcy"] = "quote_ccy"
        return self._request("POST", "/api/v5/trade/order", payload=body)


def base_ccy_from_inst_id(inst_id: str) -> str:
    # BTC-USDT -> BTC
    return inst_id.split("-")[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="根据信号调用 OKX 下单（默认模拟盘）")
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--period", default="7d")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--strategies", default="all")
    parser.add_argument("--sleep", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-rounds", type=int, default=0)
    parser.add_argument("--log-dir", default="logs")
    parser.add_argument("--min-usdt", type=float, default=10.0, help="最小下单 USDT")
    parser.add_argument(
        "--trailing-stop-pct",
        type=float,
        default=0.02,
        help="移动止盈回撤阈值（默认 0.02 = 2%）",
    )
    parser.add_argument("--simulated", action="store_true", help="强制模拟盘")
    parser.add_argument("--live", action="store_true", help="显式开启实盘（默认否）")
    args = parser.parse_args()

    repo_root = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
    load_dotenv(os.path.join(repo_root, ".env"))

    api_key = os.getenv("OKX_API_KEY", "").strip()
    api_secret = os.getenv("OKX_API_SECRET", "").strip()
    passphrase = os.getenv("OKX_API_PASSPHRASE", "").strip()
    if not (api_key and api_secret and passphrase):
        raise SystemExit(
            "缺少 OKX API 环境变量，请设置 OKX_API_KEY / OKX_API_SECRET / OKX_API_PASSPHRASE"
        )

    simulated = True
    if args.live:
        simulated = False
    if args.simulated:
        simulated = True

    logger = setup_logger(args.log_dir)
    ensure_csv(ORDER_CSV_PATH)
    strategies = parse_strategies(args.strategies)
    generator = SignalGenerator(strategies)
    client = OkxClient(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
        simulated=simulated,
    )

    inst_id = resolve_okx_inst_id(args.symbol, market_type="SPOT")
    base_ccy = base_ccy_from_inst_id(inst_id)
    mode_txt = "模拟盘" if simulated else "实盘"
    print(f"OKX 执行器启动 | 模式: {mode_txt} | instId={inst_id} | 策略={args.strategies}")
    print(f"订单CSV: {ORDER_CSV_PATH}")
    logger.info("启动 | mode=%s instId=%s strategies=%s", mode_txt, inst_id, args.strategies)
    logger.info("移动止盈回撤阈值: %.2f%%", args.trailing_stop_pct * 100)

    round_no = 0
    entry_price: float | None = None
    peak_price: float | None = None
    while True:
        round_no += 1
        try:
            df = fetch_price_data(
                symbol=args.symbol,
                period=args.period,
                interval=args.interval,
                source="okx",
                market_type="SPOT",
            )
            indicators = get_latest_indicators(df)
            signal = generator.generate(args.symbol, indicators)
            action = signal["action"]
            price = float(signal["current_price"])
            base_bal = client.asset_balance(base_ccy)

            trailing_forced_sell = False
            if base_bal > 0:
                if entry_price is None:
                    entry_price = price
                    peak_price = price
                else:
                    peak_price = max(peak_price or price, price)
                had_profit = (peak_price or price) > entry_price
                drawdown = (
                    ((peak_price or price) - price) / (peak_price or price)
                    if (peak_price or 0) > 0
                    else 0.0
                )
                if had_profit and drawdown >= args.trailing_stop_pct:
                    action = "SELL"
                    trailing_forced_sell = True
            else:
                entry_price = None
                peak_price = None

            print(
                f"\n[{signal['timestamp']}] 价格={price:.2f} 动作={action} 分数={signal['total_score']:.3f}"
            )

            row = {
                "ts": signal["timestamp"],
                "symbol": args.symbol,
                "inst_id": inst_id,
                "signal_action": action,
                "score": f"{signal['total_score']:.6f}",
                "side": "",
                "size": "",
                "price_snapshot": f"{price:.8f}",
                "order_id": "",
                "state": "NO_TRADE",
                "simulated": "1" if simulated else "0",
            }

            if action == "BUY":
                usdt = client.trade_account_balance("USDT")
                if usdt < args.min_usdt:
                    print(f"跳过 BUY：可用 USDT={usdt:.4f} < 最小下单 {args.min_usdt}")
                    row["state"] = "SKIP_LOW_USDT"
                else:
                    size = f"{usdt:.4f}"
                    resp = client.place_spot_market_order(inst_id, "buy", size)
                    if resp.get("code") != "0":
                        raise ValueError(f"BUY 下单失败: {resp}")
                    order_info = (resp.get("data") or [{}])[0]
                    row.update(
                        {
                            "side": "buy",
                            "size": size,
                            "order_id": order_info.get("ordId", ""),
                            "state": "ORDERED",
                        }
                    )
                    entry_price = price
                    peak_price = price
                    print(f"BUY 已提交：sz={size} ordId={row['order_id']}")
            elif action == "SELL":
                if base_bal <= 0:
                    print(f"跳过 SELL：可用 {base_ccy}=0")
                    row["state"] = "SKIP_NO_BASE"
                else:
                    size = f"{base_bal:.8f}"
                    resp = client.place_spot_market_order(inst_id, "sell", size)
                    if resp.get("code") != "0":
                        raise ValueError(f"SELL 下单失败: {resp}")
                    order_info = (resp.get("data") or [{}])[0]
                    row.update(
                        {
                            "side": "sell",
                            "size": size,
                            "order_id": order_info.get("ordId", ""),
                            "state": "ORDERED_TRAILING_STOP" if trailing_forced_sell else "ORDERED",
                        }
                    )
                    entry_price = None
                    peak_price = None
                    print(f"SELL 已提交：sz={size} ordId={row['order_id']}")

            append_order_csv(ORDER_CSV_PATH, row)
            logger.info("轮次=%s row=%s", round_no, row)
        except Exception as e:
            print(f"[错误] 第 {round_no} 轮执行失败: {e}", file=sys.stderr)
            logger.exception("第 %s 轮执行失败: %s", round_no, e)
            if args.once:
                raise SystemExit(1) from e

        if args.once:
            break
        if args.max_rounds and round_no >= args.max_rounds:
            print(f"已达 --max-rounds={args.max_rounds}，结束。")
            break
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()

