from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class AdjustmentType(str, Enum):
    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


class StockHistoryQuery(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    trade_date: Optional[date] = None


class StockDailyBar(BaseModel):
    ts_code: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    pre_close: float
    change: float
    pct_chg: float
    vol: float
    amount: float


class StockHistoryResponse(BaseModel):
    ts_code: str
    adjust: AdjustmentType
    query: StockHistoryQuery
    count: int
    items: List[StockDailyBar]
