from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from database import Base


class AccountDailySnapshot(Base):
    __tablename__ = "account_daily_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, unique=True, index=True)
    is_trade_day = Column(Boolean, nullable=False, default=True)
    pricing_trade_date = Column(Date, nullable=True)

    cash_balance_milli = Column(Integer, nullable=False, default=0)
    total_deposit_milli = Column(Integer, nullable=False, default=0)
    total_withdrawal_milli = Column(Integer, nullable=False, default=0)
    net_deposit_milli = Column(Integer, nullable=False, default=0)
    positions_cost_milli = Column(Integer, nullable=False, default=0)
    positions_market_value_milli = Column(Integer, nullable=True)
    total_assets_milli = Column(Integer, nullable=True)
    net_profit_milli = Column(Integer, nullable=True)
    return_rate_bp = Column(Integer, nullable=True)
    position_count = Column(Integer, nullable=False, default=0)
    rebuild_version = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @staticmethod
    def milli_to_decimal(value: Optional[int]) -> Optional[Decimal]:
        if value is None:
            return None
        return Decimal(value) / Decimal("1000")


class AccountDailyPosition(Base):
    __tablename__ = "account_daily_positions"
    __table_args__ = (
        UniqueConstraint("snapshot_date", "security_code", name="uq_account_daily_position_date_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    security_code = Column(String, nullable=False, index=True)
    security_name = Column(String, nullable=True)
    market = Column(String, nullable=True)

    quantity = Column(Integer, nullable=False, default=0)
    cost_price_milli = Column(Integer, nullable=False, default=0)
    cost_amount_milli = Column(Integer, nullable=False, default=0)
    close_price_milli = Column(Integer, nullable=True)
    market_value_milli = Column(Integer, nullable=True)
    unrealized_pnl_milli = Column(Integer, nullable=True)
    unrealized_pnl_pct_bp = Column(Integer, nullable=True)
    price_trade_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SecurityDailyPrice(Base):
    __tablename__ = "security_daily_prices"
    __table_args__ = (
        UniqueConstraint("security_code", "trade_date", name="uq_security_daily_price_code_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    security_code = Column(String, nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    ts_code = Column(String, nullable=False)
    asset_type = Column(String, nullable=True)
    close_milli = Column(Integer, nullable=False)
    open_milli = Column(Integer, nullable=True)
    high_milli = Column(Integer, nullable=True)
    low_milli = Column(Integer, nullable=True)
    source = Column(String, nullable=False, default="tushare")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
