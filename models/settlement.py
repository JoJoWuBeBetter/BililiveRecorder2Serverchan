# models/settlement.py
import uuid

from sqlalchemy import Column, Date, DateTime, Integer, String, UniqueConstraint, Index
from sqlalchemy import UUID
from sqlalchemy.sql import func

from database import Base


class SettlementImportBatch(Base):
    __tablename__ = "settlement_import_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False)
    file_hash = Column(String, nullable=False, index=True)
    row_count = Column(Integer, nullable=False, default=0)
    imported_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    encoding = Column(String, nullable=False, default="GB18030")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SettlementRecord(Base):
    __tablename__ = "settlement_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    settlement_date = Column(Date, nullable=True)
    trade_date = Column(Date, nullable=True)
    trade_time = Column(String, nullable=True)
    symbol = Column(String, nullable=True)
    symbol_name = Column(String, nullable=True)
    trade_type = Column(String, nullable=True)

    volume = Column(Integer, nullable=True)
    price_cent = Column(Integer, nullable=True)
    amount_cent = Column(Integer, nullable=True)
    occur_amount_cent = Column(Integer, nullable=True)
    commission_cent = Column(Integer, nullable=True)
    other_fee_cent = Column(Integer, nullable=True)
    stamp_tax_cent = Column(Integer, nullable=True)
    transfer_fee_cent = Column(Integer, nullable=True)

    share_balance = Column(Integer, nullable=True)
    cash_balance_cent = Column(Integer, nullable=True)

    deal_no = Column(String, nullable=True)
    shareholder_account = Column(String, nullable=True)
    serial_no = Column(String, nullable=True)
    market = Column(String, nullable=True)
    currency = Column(String, nullable=True)

    raw_row_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("serial_no", name="uq_settlement_records_serial_no"),
        UniqueConstraint("raw_row_hash", name="uq_settlement_records_raw_row_hash"),
        Index("ix_settlement_records_batch_id", "batch_id"),
    )


class AccountDailySummary(Base):
    __tablename__ = "account_daily_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    summary_date = Column(Date, nullable=False, unique=True, index=True)
    total_asset_cent = Column(Integer, nullable=False, default=0)
    cash_balance_cent = Column(Integer, nullable=False, default=0)
    total_market_value_cent = Column(Integer, nullable=False, default=0)
    position_ratio = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
