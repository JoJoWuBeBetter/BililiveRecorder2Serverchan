# services/settlement_summary_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from config import TUSHARE_TOKEN
from crud.settlement_crud import get_daily_summary, upsert_daily_summary
from models.settlement import AccountDailySummary, SettlementRecord
from services.tushare_service import fetch_daily_close_batch


@dataclass
class PositionSummary:
    symbol: str
    symbol_name: Optional[str]
    shares: int
    last_price_yuan: Optional[str]
    market_value_yuan: Optional[str]


@dataclass
class AccountSummary:
    total_asset_yuan: str
    cash_balance_yuan: str
    total_market_value_yuan: str
    positions: List[PositionSummary]
    position_ratio: Optional[float]
    net_inflow_yuan: Optional[str]


_NET_INFLOW_TYPES = {"银行转证券", "证券转银行", "利息归本"}


def _parse_time(value: Optional[str]) -> time:
    if not value:
        return time(0, 0, 0)
    try:
        return datetime.strptime(value, "%H:%M:%S").time()
    except ValueError:
        try:
            return datetime.strptime(value, "%H:%M").time()
        except ValueError:
            return time(0, 0, 0)


def _record_sort_key(record: SettlementRecord) -> Tuple[datetime, str]:
    date = record.trade_date or record.settlement_date
    if date:
        dt = datetime.combine(date, _parse_time(record.trade_time))
    else:
        dt = datetime.min
    return dt, str(record.id)


def _cents_to_yuan(value: Optional[int]) -> Optional[str]:
    if value is None:
        return None
    yuan = (Decimal(value) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(yuan, "f")


def build_account_summary(db: Session, price_date: Optional[datetime.date] = None) -> AccountSummary:
    records: List[SettlementRecord] = db.query(SettlementRecord).all()
    if not records:
        return AccountSummary(
            total_asset_yuan="0.00",
            cash_balance_yuan="0.00",
            total_market_value_yuan="0.00",
            positions=[],
            position_ratio=None,
        )

    # 账户余额：只取证券买入/卖出中的最新一条记录
    trade_records = [r for r in records if r.trade_type in {"证券买入", "证券卖出"}]
    if trade_records:
        latest_record = max(trade_records, key=_record_sort_key)
        cash_balance_cent = latest_record.cash_balance_cent or 0
    else:
        latest_record = max(records, key=_record_sort_key)
        cash_balance_cent = 0

    # 估值日期：默认取最新记录的交易日期
    if price_date is None:
        price_date = latest_record.trade_date or latest_record.settlement_date

    # 按证券代码聚合持仓，取每个代码的最新余额与成交均价
    latest_by_symbol: Dict[str, SettlementRecord] = {}
    latest_price_by_symbol: Dict[str, Tuple[int, Tuple[datetime, str]]] = {}

    for record in records:
        symbol = record.symbol
        if not symbol:
            continue
        current = latest_by_symbol.get(symbol)
        if current is None or _record_sort_key(record) > _record_sort_key(current):
            latest_by_symbol[symbol] = record

        if record.price_cent is not None and record.price_cent > 0:
            key = _record_sort_key(record)
            current_price = latest_price_by_symbol.get(symbol)
            if current_price is None or key > current_price[1]:
                latest_price_by_symbol[symbol] = (record.price_cent, key)

    positions: List[PositionSummary] = []
    total_market_value = 0

    # 尝试使用 Tushare 获取收盘价（收盘后）
    price_by_symbol: Dict[str, int] = {}
    if price_date and TUSHARE_TOKEN:
        symbol_market = {
            symbol: record.market
            for symbol, record in latest_by_symbol.items()
            if record.share_balance and record.share_balance > 0
        }
        price_by_symbol = fetch_daily_close_batch(TUSHARE_TOKEN, symbol_market, price_date)

    for symbol, record in latest_by_symbol.items():
        shares = record.share_balance or 0
        if shares <= 0:
            continue
        last_price = price_by_symbol.get(symbol)
        if last_price is None:
            price_entry = latest_price_by_symbol.get(symbol)
            last_price = price_entry[0] if price_entry else None
        market_value = None
        if last_price is not None:
            market_value = shares * last_price
            total_market_value += market_value
        positions.append(
            PositionSummary(
                symbol=symbol,
                symbol_name=record.symbol_name,
                shares=shares,
                last_price_yuan=_cents_to_yuan(last_price),
                market_value_yuan=_cents_to_yuan(market_value),
            )
        )

    total_asset_cent = cash_balance_cent + total_market_value
    position_ratio = None
    if total_asset_cent > 0:
        position_ratio = total_market_value / total_asset_cent

    positions.sort(key=lambda item: item.symbol)
    summary = AccountSummary(
        total_asset_yuan=_cents_to_yuan(total_asset_cent) or "0.00",
        cash_balance_yuan=_cents_to_yuan(cash_balance_cent) or "0.00",
        total_market_value_yuan=_cents_to_yuan(total_market_value) or "0.00",
        positions=positions,
        position_ratio=position_ratio,
        net_inflow_yuan=None,
    )

    if price_date:
        stored = get_daily_summary(db, price_date)
        if stored is None:
            stored = AccountDailySummary(
                summary_date=price_date,
                total_asset_cent=total_asset_cent,
                cash_balance_cent=cash_balance_cent,
                total_market_value_cent=total_market_value,
                position_ratio=str(position_ratio) if position_ratio is not None else None,
            )
        else:
            stored.total_asset_cent = total_asset_cent
            stored.cash_balance_cent = cash_balance_cent
            stored.total_market_value_cent = total_market_value
            stored.position_ratio = str(position_ratio) if position_ratio is not None else None
        upsert_daily_summary(db, stored)

    net_inflow_cent = 0
    for record in records:
        if record.trade_type in _NET_INFLOW_TYPES:
            net_inflow_cent += record.occur_amount_cent or 0
    summary.net_inflow_yuan = _cents_to_yuan(net_inflow_cent) or "0.00"

    return summary
