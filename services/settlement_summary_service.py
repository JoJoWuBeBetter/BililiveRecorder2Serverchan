# services/settlement_summary_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from models.settlement import SettlementRecord


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
    positions: List[PositionSummary]
    position_ratio: Optional[float]


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


def build_account_summary(db: Session) -> AccountSummary:
    records: List[SettlementRecord] = db.query(SettlementRecord).all()
    if not records:
        return AccountSummary(
            total_asset_yuan="0.00",
            cash_balance_yuan="0.00",
            positions=[],
            position_ratio=None,
        )

    # 账户余额：取最新一条记录的资金余额
    latest_record = max(records, key=_record_sort_key)
    cash_balance_cent = latest_record.cash_balance_cent or 0

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

    for symbol, record in latest_by_symbol.items():
        shares = record.share_balance or 0
        if shares <= 0:
            continue
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
    return AccountSummary(
        total_asset_yuan=_cents_to_yuan(total_asset_cent) or "0.00",
        cash_balance_yuan=_cents_to_yuan(cash_balance_cent) or "0.00",
        positions=positions,
        position_ratio=position_ratio,
    )
