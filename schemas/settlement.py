# schemas/settlement.py
import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class SettlementImportBatch(BaseModel):
    id: uuid.UUID
    filename: str
    file_hash: str
    row_count: int
    imported_count: int
    skipped_count: int
    error_count: int
    encoding: str
    created_at: datetime

    class Config:
        from_attributes = True


class SettlementRecord(BaseModel):
    id: uuid.UUID
    batch_id: uuid.UUID

    settlement_date: Optional[date] = None
    trade_date: Optional[date] = None
    trade_time: Optional[str] = None
    symbol: Optional[str] = None
    symbol_name: Optional[str] = None
    trade_type: Optional[str] = None

    volume: Optional[int] = None
    price_cent: Optional[int] = None
    amount_cent: Optional[int] = None
    occur_amount_cent: Optional[int] = None
    commission_cent: Optional[int] = None
    other_fee_cent: Optional[int] = None
    stamp_tax_cent: Optional[int] = None
    transfer_fee_cent: Optional[int] = None

    share_balance: Optional[int] = None
    cash_balance_cent: Optional[int] = None

    deal_no: Optional[str] = None
    shareholder_account: Optional[str] = None
    serial_no: Optional[str] = None
    market: Optional[str] = None
    currency: Optional[str] = None

    raw_row_hash: str
    created_at: datetime

    class Config:
        from_attributes = True


class SettlementImportResult(BaseModel):
    batch: SettlementImportBatch


class PositionSummary(BaseModel):
    symbol: str
    symbol_name: Optional[str] = None
    shares: int
    last_price_yuan: Optional[str] = None
    market_value_yuan: Optional[str] = None


class AccountSummary(BaseModel):
    total_asset_yuan: str
    cash_balance_yuan: str
    positions: list[PositionSummary]
    position_ratio: Optional[float] = None
