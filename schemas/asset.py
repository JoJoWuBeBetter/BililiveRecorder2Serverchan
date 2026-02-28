from datetime import date, time
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class AssetPositionItem(BaseModel):
    security_code: str
    security_name: Optional[str] = None
    market: Optional[str] = None
    quantity: int
    cost_price: Decimal
    cost_amount: Decimal
    close_price: Decimal
    price_trade_date: date
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Optional[Decimal] = None


class AssetDetailResponse(BaseModel):
    target_date: date
    pricing_trade_date: date
    cash_balance: Decimal
    total_deposit: Decimal
    total_withdrawal: Decimal
    net_deposit: Decimal
    positions_market_value: Decimal
    total_assets: Decimal
    position_count: int
    positions: List[AssetPositionItem]


class AssetCashFlowItem(BaseModel):
    occur_date: date
    occur_time: time
    trade_type: str
    amount: Decimal
    cash_balance: Decimal


class AssetCashFlowResponse(BaseModel):
    target_date: date
    count: int
    items: List[AssetCashFlowItem]


class AssetSnapshotRebuildResponse(BaseModel):
    mode: str
    from_date: date
    to_date: date
    trade_day_count: int
    security_count: int
    snapshot_count: int
    position_count: int
    include_pricing: bool
