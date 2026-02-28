from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models.settlement import SettlementRecord
from schemas.stock import AdjustmentType, StockHistoryQuery
from services.account_snapshot_service import AccountSnapshotService
from services.stock_history_service import StockDailyBar, StockHistoryResponse


class FakeStockHistoryService:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def get_stock_history(self, **kwargs):
        self.calls.append(kwargs)
        ts_code = kwargs["ts_code"]
        return self.responses[ts_code]


class FakeTradeCalendarService:
    def __init__(self, trade_days):
        self.trade_days = trade_days
        self.calls = []

    def get_trade_days(self, start_date, end_date, exchange="SSE"):
        self.calls.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "exchange": exchange,
            }
        )
        return [day for day in self.trade_days if start_date <= day <= end_date]


def _create_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session_local()


def _record(
    *,
    occur_date: date,
    occur_time: str,
    security_code=None,
    security_name=None,
    trade_type="银行转证券",
    volume=0,
    amount="0",
    share_balance=0,
    cash_balance="0",
    market=None,
):
    amount_decimal = Decimal(amount)
    cash_balance_decimal = Decimal(cash_balance)
    return SettlementRecord(
        source_hash=f"{occur_date.isoformat()}-{occur_time}-{security_code}-{trade_type}-{volume}-{amount}-{share_balance}-{cash_balance}",
        settlement_date=occur_date,
        occur_date=occur_date,
        occur_time=datetime.strptime(occur_time, "%H:%M:%S").time(),
        security_code=security_code,
        security_name=security_name,
        trade_type=trade_type,
        volume=volume,
        price=Decimal("0"),
        turnover_milli=0,
        amount_milli=int(amount_decimal * Decimal("1000")),
        commission_milli=0,
        other_fee_milli=0,
        stamp_duty_milli=0,
        transfer_fee_milli=0,
        share_balance=share_balance,
        cash_balance_milli=int(cash_balance_decimal * Decimal("1000")),
        trade_no=None,
        shareholder_account=None,
        serial_no=None,
        market=market,
        currency="人民币",
        raw_row={},
    )


def _history(ts_code: str, bars: list[tuple[date, float]]) -> StockHistoryResponse:
    return StockHistoryResponse(
        ts_code=ts_code,
        adjust=AdjustmentType.NONE,
        query=StockHistoryQuery(start_date=bars[0][0], end_date=bars[-1][0]),
        count=len(bars),
        items=[
            StockDailyBar(
                ts_code=ts_code,
                trade_date=trade_date,
                open=close_price,
                high=close_price,
                low=close_price,
                close=close_price,
                pre_close=close_price,
                change=0.0,
                pct_chg=0.0,
                vol=0.0,
                amount=0.0,
            )
            for trade_date, close_price in bars
        ],
    )


def test_account_snapshot_service_rebuilds_and_persists_trade_day_snapshots():
    db = _create_db()
    db.add_all(
        [
            _record(
                occur_date=date(2025, 8, 6),
                occur_time="09:00:00",
                trade_type="银行转证券",
                amount="5000",
                cash_balance="5000",
            ),
            _record(
                occur_date=date(2025, 8, 6),
                occur_time="09:30:00",
                security_code="000597",
                security_name="东北制药",
                trade_type="证券买入",
                volume=200,
                amount="-1000",
                share_balance=200,
                cash_balance="4000",
                market="深市A股",
            ),
            _record(
                occur_date=date(2025, 8, 7),
                occur_time="10:00:00",
                security_code="000597",
                security_name="东北制药",
                trade_type="证券卖出",
                volume=50,
                amount="300",
                share_balance=150,
                cash_balance="4300",
                market="深市A股",
            ),
        ]
    )
    db.commit()

    stock_service = FakeStockHistoryService(
        responses={
            "000597": _history("000597.SZ", [(date(2025, 8, 6), 5.8), (date(2025, 8, 7), 6.1)])
        }
    )
    trade_calendar_service = FakeTradeCalendarService(
        trade_days=[date(2025, 8, 6), date(2025, 8, 7)]
    )
    service = AccountSnapshotService(
        stock_history_service=stock_service,
        trade_calendar_service_instance=trade_calendar_service,
    )

    try:
        rebuild_result = service.rebuild_snapshots(db=db, mode="full", include_pricing=True)
        snapshot_detail = service.get_snapshot_detail(db=db, snapshot_date=date(2025, 8, 7))
    finally:
        db.close()

    assert rebuild_result.trade_day_count == 2
    assert rebuild_result.security_count == 1
    assert len(stock_service.calls) == 1
    assert snapshot_detail.cash_balance == Decimal("4300")
    assert snapshot_detail.positions_market_value == Decimal("915")
    assert snapshot_detail.total_assets == Decimal("5215")
    assert snapshot_detail.positions[0].quantity == 150
    assert snapshot_detail.positions[0].cost_amount == Decimal("700")
    assert snapshot_detail.positions[0].cost_price.quantize(Decimal("0.001")) == Decimal("4.666")
    assert snapshot_detail.positions[0].unrealized_pnl == Decimal("215")


def test_account_snapshot_service_can_rebuild_without_pricing():
    db = _create_db()
    db.add(
        _record(
            occur_date=date(2025, 8, 6),
            occur_time="09:00:00",
            trade_type="银行转证券",
            amount="5000",
            cash_balance="5000",
        )
    )
    db.commit()

    stock_service = FakeStockHistoryService(responses={})
    trade_calendar_service = FakeTradeCalendarService(trade_days=[date(2025, 8, 6)])
    service = AccountSnapshotService(
        stock_history_service=stock_service,
        trade_calendar_service_instance=trade_calendar_service,
    )

    try:
        rebuild_result = service.rebuild_snapshots(db=db, mode="full", include_pricing=False)
        snapshot_detail = service.get_snapshot_detail(db=db, snapshot_date=date(2025, 8, 6))
    finally:
        db.close()

    assert rebuild_result.include_pricing is False
    assert len(stock_service.calls) == 0
    assert snapshot_detail.total_assets == Decimal("5000")
    assert snapshot_detail.positions == []


def test_account_snapshot_service_sorts_trade_days_before_building_snapshots():
    db = _create_db()
    db.add_all(
        [
            _record(
                occur_date=date(2025, 8, 6),
                occur_time="09:00:00",
                trade_type="银行转证券",
                amount="5000",
                cash_balance="5000",
            ),
            _record(
                occur_date=date(2025, 8, 7),
                occur_time="09:00:00",
                trade_type="证券转银行",
                amount="-1000",
                cash_balance="4000",
            ),
        ]
    )
    db.commit()

    trade_calendar_service = FakeTradeCalendarService(
        trade_days=[date(2025, 8, 7), date(2025, 8, 6)]
    )
    service = AccountSnapshotService(
        stock_history_service=FakeStockHistoryService(responses={}),
        trade_calendar_service_instance=trade_calendar_service,
    )

    try:
        service.rebuild_snapshots(db=db, mode="full", include_pricing=False)
        first_day = service.get_snapshot_detail(db=db, snapshot_date=date(2025, 8, 6))
        second_day = service.get_snapshot_detail(db=db, snapshot_date=date(2025, 8, 7))
    finally:
        db.close()

    assert first_day.cash_balance == Decimal("5000")
    assert first_day.net_deposit == Decimal("5000")
    assert second_day.cash_balance == Decimal("4000")
    assert second_day.net_deposit == Decimal("4000")
