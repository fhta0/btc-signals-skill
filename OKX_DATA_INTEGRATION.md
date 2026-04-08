# OKX 数据接入说明

本文档描述 **数据源抽象层**、**符号约定**、**OKX 分页与限频**、**测试分层** 与 **推荐开发顺序**。实现代码位于 `scripts/datasource/`。

---

## 1. 目标

- 指标与回测 **不感知** 数据来自 Yahoo 还是 OKX
- 优先使用 **公开行情**（无需 API Key）
- 输出统一：`Open/High/Low/Close/Volume` + UTC `DatetimeIndex`

---

## 2. 架构：DataSource 抽象层（已定）

```
scripts/
  datasource/
    __init__.py          # get_data_source / fetch_ohlcv 工厂与统一入口
    base.py              # DataSource 抽象 + normalize_ohlcv（内部使用）
    yfinance_source.py
    okx_source.py
  fetch_price.py         # 仅 CLI，内部调用 fetch_ohlcv
```

- `indicators.py` / `signal_generator.py` / `backtest.py` 继续通过 `fetch_price.fetch_price_data(...)` 取数；可选参数 `source` / `market_type` 传入工厂。
- **禁止** 在业务脚本里写 `if source == "okx"`，新数据源应新增 `*_source.py` 并注册到 `datasource/__init__.py` 的 `_REGISTRY`。

---

## 3. 是否需要 API Key

| 场景 | 是否需要 Key |
|------|----------------|
| 公开 K 线、Ticker | 否 |
| 下单、账户、私有账单 | 是（`API_KEY` / `SECRET` / `PASSPHRASE`） |

Key 仅放 `.env`，勿写入仓库文档或代码。

---

## 4. 符号约定（已定死，避免反复横跳）

**CLI 与 `fetch_price_data` 统一使用「展示符号」`BTC-USD` 风格（与 Yahoo 一致、对用户友好）。**

各数据源在 **各自 Source 内** 映射为原生 `instId`：

| 展示符号 | yfinance | OKX SPOT | OKX SWAP |
|----------|----------|----------|----------|
| `BTC-USD` | `BTC-USD` | `BTC-USDT` | `BTC-USDT-SWAP` |
| `ETH-USD` | `ETH-USD` | `ETH-USDT` | `ETH-USDT-SWAP` |
| `BTC-USDT` | （无对应，Yahoo 可能失败） | `BTC-USDT` | `BTC-USDT-SWAP` |

规则（与 `okx_source.resolve_okx_inst_id` 一致）：

- **已验证的 `*-USD` 展示符**（当前白名单）：`BTC-USD`、`ETH-USD`。其它 `FOO-USD` 会 **显式报错**，避免误映射到错误 `instId`。
- **OKX 原生现货**：`BASE-USDT`（字母数字 + `-USDT`）直接接受，例如 `SOL-USDT`。
- **`market_type=SWAP`**：在现货 `instId` 基础上追加 `-SWAP`，或直接使用完整 `BASE-USDT-SWAP`。
- 若符号已带 `-SWAP`，须匹配 `^[A-Z0-9]+-USDT-SWAP$`，否则报错。
- **不支持** 如 `BTC-BUSD` 等未约定报价：应改用 OKX 上真实存在的 `instId` 格式。

---

## 5. 时间粒度映射

项目 `interval` → OKX `bar`（见 `okx_source.INTERVAL_TO_BAR`），例如：`1h` → `1H`，`1d` → `1D`。

---

## 6. OKX K 线分页与 HTTP

参考 OKX v5 `GET /api/v5/market/candles`：

| 项 | 说明 |
|----|------|
| **单次 `limit` 上限** | **300** 条 |
| **`after`** | **毫秒**时间戳；返回 **早于** 该时间戳的 K 线（用于向 **更旧** 历史翻页） |
| **`before`** | **毫秒**时间戳；返回 **新于** 该时间戳的 K 线（用于向 **更新** 方向翻页） |

默认返回顺序为 **时间倒序**（最新在前）。向过去补全历史时：取当前批次中 **最老** 一根 K 线的 `ts`，将 `after=str(ts)` 作为下一页游标。

**终止翻页**：当批次内 **最老** `ts` **严格小于** `start_ms` 时再停止（使用 `oldest < start_ms`，而非 `<=`），避免最老一根恰等于窗口起点时提前结束、遗漏更早数据或重复批次边界问题。窗口外数据由后续 `t < start_ms` 过滤丢弃。

**易错点**：参数单位为 **毫秒**，勿用秒级时间戳。

**HTTP**：部分环境对无 `User-Agent` 的请求返回 403，实现中已带浏览器 UA。

**重试**：`_http_get_json` 对网络/HTTP 失败做 **最多 3 次** 请求，间隔 `2**attempt` 秒（指数退避）；连续失败后仍抛出异常。

---

## 7. 数据字段与 `normalize_ohlcv`

`normalize_ohlcv` 为 **模块内部** 函数（不列入 `datasource` 包公共 `__all__`）。各 Source 在返回前调用它：

- 仅保留 `Open, High, Low, Close, Volume`
- 数值化、去 NaN、索引转 UTC、去重、按时间升序

---

## 8. 测试策略（CI 稳定）

| 类型 | 内容 | 运行方式 |
|------|------|----------|
| 单元测试 | `resolve_okx_inst_id`、`normalize_ohlcv`、工厂注册 | 默认 `pytest`，**无网络** |
| 集成测试 | 真实请求 OKX / Yahoo | `@pytest.mark.integration`，**按需** `pytest -m integration` |

勿让默认 CI 依赖外网；网络用例单独标记。

---

## 9. 推荐开发顺序（已调整）

1. **`base.py` + `yfinance_source.py`**：把原 `yfinance` 逻辑迁入并实现 `normalize_ohlcv`，验证抽象是否合理。  
2. **`okx_source.py`**：分页、`instId`、UA、错误处理。  
3. **`fetch_price.py` CLI**：`--source` / `--market-type`，仅调工厂。  
4. **回归**：`signal_generator` / `backtest` 在默认 `yfinance` 下行为与迁移前一致；再手动或集成测试 `okx`。

当前仓库已完成上述 1–3 步；第 4 步可通过本地运行与 `pytest` / `pytest -m integration` 验证。

---

## 10. 版本与维护

- 若 OKX 调整分页语义或限额，优先改 `okx_source.py` 与本文档第 6 节，保持业务层不变。
- 扩展新的 **已验证 `*-USD` 展示符** 时，同步修改 `okx_source._OKX_VERIFIED_USD_DISPLAY` 与本节表格。
