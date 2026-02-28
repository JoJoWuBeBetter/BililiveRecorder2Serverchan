import enum
from decimal import Decimal

from sqlalchemy import Column, Date, DateTime, Integer, JSON, Numeric, String, Time
from sqlalchemy.sql import func

from database import Base


class SettlementTradeType(str, enum.Enum):
    SECURITY_BUY = "证券买入"
    SECURITY_SELL = "证券卖出"
    BANK_TO_SECURITY = "银行转证券"
    SECURITY_TO_BANK = "证券转银行"
    INTEREST_REINVEST = "利息归本"
    DIVIDEND_TAX = "股息红利差异扣税"
    DESIGNATED_TRADING = "指定交易"
    DIVIDEND_CREDIT = "红利入账"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(item.value for item in cls)

    @classmethod
    def trading_values(cls) -> tuple[str, ...]:
        return (
            cls.SECURITY_BUY.value,
            cls.SECURITY_SELL.value,
        )


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
    turnover_milli = Column(Integer, nullable=False, default=0)
    amount_milli = Column(Integer, nullable=False, default=0)
    commission_milli = Column(Integer, nullable=False, default=0)
    other_fee_milli = Column(Integer, nullable=False, default=0)
    stamp_duty_milli = Column(Integer, nullable=False, default=0)
    transfer_fee_milli = Column(Integer, nullable=False, default=0)
    share_balance = Column(Integer, nullable=False, default=0)
    cash_balance_milli = Column(Integer, nullable=False, default=0)

    trade_no = Column(String, nullable=True)
    shareholder_account = Column(String, nullable=True)
    serial_no = Column(String, nullable=True)
    market = Column(String, nullable=True)
    currency = Column(String, nullable=True)

    raw_row = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @staticmethod
    def _milli_to_decimal(value: int) -> Decimal:
        return Decimal(value) / Decimal("1000")

    @property
    def turnover(self) -> Decimal:
        return self._milli_to_decimal(self.turnover_milli)

    @property
    def amount(self) -> Decimal:
        return self._milli_to_decimal(self.amount_milli)

    @property
    def commission(self) -> Decimal:
        return self._milli_to_decimal(self.commission_milli)

    @property
    def other_fee(self) -> Decimal:
        return self._milli_to_decimal(self.other_fee_milli)

    @property
    def stamp_duty(self) -> Decimal:
        return self._milli_to_decimal(self.stamp_duty_milli)

    @property
    def transfer_fee(self) -> Decimal:
        return self._milli_to_decimal(self.transfer_fee_milli)

    @property
    def cash_balance(self) -> Decimal:
        return self._milli_to_decimal(self.cash_balance_milli)
