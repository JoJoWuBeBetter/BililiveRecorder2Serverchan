from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from database import Base


class TradeCalendarDayRecord(Base):
    __tablename__ = "trade_calendar_days"
    __table_args__ = (
        UniqueConstraint("exchange", "cal_date", name="uq_trade_calendar_exchange_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String, nullable=False, default="SSE", index=True)
    cal_date = Column(Date, nullable=False, index=True)
    is_open = Column(Boolean, nullable=False, default=False)
    pretrade_date = Column(Date, nullable=True)
    source = Column(String, nullable=False, default="tushare")
    synced_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
