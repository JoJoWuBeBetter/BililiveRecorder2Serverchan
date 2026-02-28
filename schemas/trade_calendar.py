from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class TradeCalendarDayItem(BaseModel):
    cal_date: date
    is_open: bool
    pretrade_date: Optional[date] = None


class TradeCalendarMonthResponse(BaseModel):
    year: int
    month: int
    exchange: str
    items: List[TradeCalendarDayItem]


class TradeCalendarNormalizeResponse(BaseModel):
    requested_date: date
    effective_date: date
    is_trade_day: bool


class TradeCalendarAdjacentResponse(BaseModel):
    requested_date: date
    effective_date: date
    direction: str
