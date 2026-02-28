from datetime import date
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
    positions_market_value: Decimal
    total_assets: Decimal
    position_count: int
    positions: List[AssetPositionItem]
