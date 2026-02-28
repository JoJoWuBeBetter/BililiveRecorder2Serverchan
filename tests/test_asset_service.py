from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models.settlement import SettlementRecord
from services.asset_service import AssetDetailNotFoundError, AssetService
from services.stock_history_service import StockDailyBar, StockHistoryFetchError, StockHistoryResponse
from schemas.stock import AdjustmentType, StockHistoryQuery


class FakeStockHistoryService:
    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls = []

    def get_stock_history(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        ts_code = kwargs["ts_code"]
        result = self.responses.get(ts_code)
        if result is None:
            raise StockHistoryFetchError(f"{ts_code} missing")
        return result


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
        turnover=Decimal("0"),
        amount=Decimal(amount),
        commission=Decimal("0"),
        other_fee=Decimal("0"),
        stamp_duty=Decimal("0"),
        transfer_fee=Decimal("0"),
        share_balance=share_balance,
        cash_balance=Decimal(cash_balance),
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


def test_asset_service_returns_cash_only_when_no_positions():
    db = _create_db()
    db.add(_record(occur_date=date(2025, 8, 6), occur_time="09:00:00", cash_balance="5000"))
    db.commit()

    service = AssetService(stock_history_service=FakeStockHistoryService())

    try:
        result = service.get_asset_detail(db=db, target_date=date(2025, 8, 6))
    finally:
        db.close()

    assert result.cash_balance == Decimal("5000")
    assert result.positions_market_value == Decimal("0")
    assert result.total_assets == Decimal("5000")
    assert result.positions == []


def test_asset_service_returns_position_detail_for_historical_day():
    db = _create_db()
    db.add_all(
        [
            _record(occur_date=date(2025, 8, 6), occur_time="09:00:00", cash_balance="5000"),
            _record(
                occur_date=date(2025, 8, 6),
                occur_time="09:30:00",
                security_code="000597",
                security_name="东北制药",
                trade_type="证券买入",
                volume=200,
                amount="-1223",
                share_balance=200,
                cash_balance="3777",
                market="深市A股",
            ),
        ]
    )
    db.commit()

    service = AssetService(
        stock_history_service=FakeStockHistoryService(
            responses={"000597": _history("000597.SZ", [(date(2025, 8, 6), 6.5)])}
        )
    )

    try:
        result = service.get_asset_detail(db=db, target_date=date(2025, 8, 6))
    finally:
        db.close()

    assert result.cash_balance == Decimal("3777")
    assert result.positions_market_value == Decimal("1300.0")
    assert result.total_assets == Decimal("5077.0")
    assert result.position_count == 1
    assert result.positions[0].cost_amount == Decimal("1223")
    assert result.positions[0].unrealized_pnl == Decimal("77.0")


def test_asset_service_rolls_back_to_previous_trade_day_for_weekend():
    db = _create_db()
    db.add(
        _record(
            occur_date=date(2025, 8, 8),
            occur_time="09:30:00",
            security_code="000597",
            security_name="东北制药",
            trade_type="证券买入",
            volume=100,
            amount="-500",
            share_balance=100,
            cash_balance="500",
            market="深市A股",
        )
    )
    db.commit()

    service = AssetService(
        stock_history_service=FakeStockHistoryService(
            responses={"000597": _history("000597.SZ", [(date(2025, 8, 8), 5.6)])}
        )
    )

    try:
        result = service.get_asset_detail(db=db, target_date=date(2025, 8, 9))
    finally:
        db.close()

    assert result.positions[0].price_trade_date == date(2025, 8, 8)


def test_asset_service_uses_previous_close_before_market_close(monkeypatch):
    db = _create_db()
    db.add(
        _record(
            occur_date=date(2025, 8, 8),
            occur_time="09:30:00",
            security_code="000597",
            security_name="东北制药",
            trade_type="证券买入",
            volume=100,
            amount="-500",
            share_balance=100,
            cash_balance="500",
            market="深市A股",
        )
    )
    db.commit()

    service = AssetService(
        stock_history_service=FakeStockHistoryService(
            responses={
                "000597": _history(
                    "000597.SZ",
                    [(date(2025, 8, 7), 5.5), (date(2025, 8, 8), 5.8)],
                )
            }
        )
    )
    monkeypatch.setattr(
        service,
        "_now_shanghai",
        lambda: datetime(2025, 8, 8, 14, 30, 0),
    )

    try:
        result = service.get_asset_detail(db=db, target_date=date(2025, 8, 8))
    finally:
        db.close()

    assert result.positions[0].price_trade_date == date(2025, 8, 7)
    assert result.positions[0].close_price == Decimal("5.5")


def test_asset_service_handles_partial_sell_with_weighted_cost():
    db = _create_db()
    db.add_all(
        [
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

    service = AssetService(
        stock_history_service=FakeStockHistoryService(
            responses={"000597": _history("000597.SZ", [(date(2025, 8, 7), 7.0)])}
        )
    )

    try:
        result = service.get_asset_detail(db=db, target_date=date(2025, 8, 7))
    finally:
        db.close()

    assert result.positions[0].quantity == 150
    assert result.positions[0].cost_price == Decimal("5")
    assert result.positions[0].cost_amount == Decimal("750")
    assert result.positions[0].market_value == Decimal("1050")


def test_asset_service_raises_when_no_settlement_records():
    db = _create_db()
    service = AssetService(stock_history_service=FakeStockHistoryService())

    try:
        service.get_asset_detail(db=db, target_date=date(2025, 8, 7))
    except AssetDetailNotFoundError as exc:
        assert "暂无交割单数据" in str(exc)
    else:
        raise AssertionError("Expected AssetDetailNotFoundError")
    finally:
        db.close()


def test_asset_service_raises_when_price_unavailable():
    db = _create_db()
    db.add(
        _record(
            occur_date=date(2025, 8, 8),
            occur_time="09:30:00",
            security_code="000597",
            security_name="东北制药",
            trade_type="证券买入",
            volume=100,
            amount="-500",
            share_balance=100,
            cash_balance="500",
            market="深市A股",
        )
    )
    db.commit()

    service = AssetService(stock_history_service=FakeStockHistoryService(error=StockHistoryFetchError("no price")))

    try:
        service.get_asset_detail(db=db, target_date=date(2025, 8, 8))
    except StockHistoryFetchError as exc:
        assert "no price" in str(exc)
    else:
        raise AssertionError("Expected StockHistoryFetchError")
    finally:
        db.close()
