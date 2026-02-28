from sqlalchemy import Column, Date, DateTime, Integer, JSON, Numeric, String, Time
from sqlalchemy.sql import func

from database import Base


class SettlementRecord(Base):
    __tablename__ = "settlement_records"

    id = Column(Integer, primary_key=True, index=True)
    source_hash = Column(String, nullable=False, unique=True, index=True)

    settlement_date = Column(Date, nullable=False, index=True)
    occur_date = Column(Date, nullable=False, index=True)
    occur_time = Column(Time, nullable=False)

    security_code = Column(String, nullable=True, index=True)
    security_name = Column(String, nullable=True)
    trade_type = Column(String, nullable=False, index=True)

    volume = Column(Integer, nullable=False, default=0)
    price = Column(Numeric(18, 6), nullable=False, default=0)
    turnover = Column(Numeric(18, 6), nullable=False, default=0)
    amount = Column(Numeric(18, 6), nullable=False, default=0)
    commission = Column(Numeric(18, 6), nullable=False, default=0)
    other_fee = Column(Numeric(18, 6), nullable=False, default=0)
    stamp_duty = Column(Numeric(18, 6), nullable=False, default=0)
    transfer_fee = Column(Numeric(18, 6), nullable=False, default=0)
    share_balance = Column(Integer, nullable=False, default=0)
    cash_balance = Column(Numeric(18, 6), nullable=False, default=0)

    trade_no = Column(String, nullable=True)
    shareholder_account = Column(String, nullable=True)
    serial_no = Column(String, nullable=True)
    market = Column(String, nullable=True)
    currency = Column(String, nullable=True)

    raw_row = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
