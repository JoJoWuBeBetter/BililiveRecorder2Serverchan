from datetime import date, datetime, time
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class SettlementImportResponse(BaseModel):
    filename: str
    total_count: int
    inserted_count: int
    skipped_count: int


class SettlementRecordItem(BaseModel):
    id: int
    settlement_date: date
    occur_date: date
    occur_time: time
    security_code: Optional[str] = None
    security_name: Optional[str] = None
    trade_type: str
    volume: int
    price: Decimal
    turnover: Decimal
    amount: Decimal
    commission: Decimal
    other_fee: Decimal
    stamp_duty: Decimal
    transfer_fee: Decimal
    share_balance: int
    cash_balance: Decimal
    trade_no: Optional[str] = None
    shareholder_account: Optional[str] = None
    serial_no: Optional[str] = None
    market: Optional[str] = None
    currency: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SettlementListResponse(BaseModel):
    total_count: int
    items: List[SettlementRecordItem]
