# services/tushare_service.py
from __future__ import annotations

from datetime import date
from typing import Dict, Optional

import tushare as ts

from config import logger


def _market_to_suffix(market: Optional[str], symbol: str) -> str:
    if market:
        if "深" in market:
            return "SZ"
        if "沪" in market:
            return "SH"
    if symbol.startswith("6"):
        return "SH"
    return "SZ"


def build_ts_code(symbol: str, market: Optional[str]) -> str:
    suffix = _market_to_suffix(market, symbol)
    return f"{symbol}.{suffix}"


def _date_to_trade_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def fetch_daily_close(
    token: str,
    ts_code: str,
    trade_date: date,
) -> Optional[int]:
    """返回收盘价（分）。"""
    if not token:
        return None

    try:
        pro = ts.pro_api(token)
        df = pro.daily(
            ts_code=ts_code,
            trade_date=_date_to_trade_date(trade_date),
            fields=["ts_code", "trade_date", "close"],
        )
        if df is None or df.empty:
            return None
        close_value = df.iloc[0]["close"]
        if close_value is None:
            return None
        return int(round(float(close_value) * 100))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Tushare 行情获取失败: {ts_code} {trade_date} {exc}")
        return None


def fetch_daily_close_batch(
    token: str,
    symbol_market: Dict[str, Optional[str]],
    trade_date: date,
) -> Dict[str, int]:
    """批量获取收盘价（分）。返回 {symbol: close_cent}。"""
    if not token or not symbol_market:
        return {}

    ts_codes = []
    ts_code_to_symbol: Dict[str, str] = {}
    for symbol, market in symbol_market.items():
        ts_code = build_ts_code(symbol, market)
        ts_codes.append(ts_code)
        ts_code_to_symbol[ts_code] = symbol

    try:
        pro = ts.pro_api(token)
        df = pro.daily(
            ts_code=",".join(ts_codes),
            trade_date=_date_to_trade_date(trade_date),
            fields=["ts_code", "trade_date", "close"],
        )
        if df is None or df.empty:
            return {}

        results: Dict[str, int] = {}
        for _, row in df.iterrows():
            ts_code = row.get("ts_code")
            close_value = row.get("close")
            if not ts_code or close_value is None:
                continue
            symbol = ts_code_to_symbol.get(ts_code)
            if not symbol:
                continue
            results[symbol] = int(round(float(close_value) * 100))
        return results
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Tushare 批量行情获取失败: {exc}")
        return {}
