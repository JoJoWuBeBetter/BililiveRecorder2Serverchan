from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models.settlement import SettlementRecord
from services.asset_service import AssetDetailNotFoundError, AssetService
from services.simple_cache import SimpleTTLCache
from services.stock_history_service import StockDailyBar, StockHistoryFetchError, StockHistoryResponse
from services.trade_calendar_service import TradeCalendarFetchError
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


class FakeTradeCalendarService:
    def __init__(self, effective_trade_date=None, error=None):
        self.effective_trade_date = effective_trade_date
        self.error = error
        self.calls = []

    def get_effective_trade_date(self, target_date, now=None, exchange="SSE"):
        self.calls.append(
            {
                "target_date": target_date,
                "now": now,
                "exchange": exchange,
            }
        )
        if self.error:
            raise self.error
        return self.effective_trade_date or target_date


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


def test_asset_service_returns_cash_only_when_no_positions():
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

    service = AssetService(
        stock_history_service=FakeStockHistoryService(),
        trade_calendar_service_instance=FakeTradeCalendarService(effective_trade_date=date(2025, 8, 6)),
        cache=SimpleTTLCache(),
    )

    try:
        result = service.get_asset_detail(db=db, target_date=date(2025, 8, 6))
    finally:
        db.close()

    assert result.cash_balance == Decimal("5000")
    assert result.total_deposit == Decimal("5000")
    assert result.total_withdrawal == Decimal("0")
    assert result.net_deposit == Decimal("5000")
    assert result.positions_market_value == Decimal("0")
    assert result.total_assets == Decimal("5000")
    assert result.positions == []


def test_asset_service_returns_position_detail_for_historical_day():
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
        ),
        trade_calendar_service_instance=FakeTradeCalendarService(effective_trade_date=date(2025, 8, 6)),
        cache=SimpleTTLCache(),
    )

    try:
        result = service.get_asset_detail(db=db, target_date=date(2025, 8, 6))
    finally:
        db.close()

    assert result.cash_balance == Decimal("3777")
    assert result.total_deposit == Decimal("5000")
    assert result.total_withdrawal == Decimal("0")
    assert result.net_deposit == Decimal("5000")
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
        ),
        trade_calendar_service_instance=FakeTradeCalendarService(effective_trade_date=date(2025, 8, 8)),
        cache=SimpleTTLCache(),
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
                    [(date(2025, 8, 6), 5.4), (date(2025, 8, 7), 5.5), (date(2025, 8, 8), 5.8)],
                )
            }
        ),
        trade_calendar_service_instance=FakeTradeCalendarService(effective_trade_date=date(2025, 8, 7)),
        cache=SimpleTTLCache(),
    )

    try:
        result = service.get_asset_detail(db=db, target_date=date(2025, 8, 8))
    finally:
        db.close()

    assert result.positions[0].price_trade_date == date(2025, 8, 7)
    assert result.positions[0].close_price == Decimal("5.5")


def test_asset_service_handles_partial_sell_with_diluted_cost():
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
        ),
        trade_calendar_service_instance=FakeTradeCalendarService(effective_trade_date=date(2025, 8, 7)),
        cache=SimpleTTLCache(),
    )

    try:
        result = service.get_asset_detail(db=db, target_date=date(2025, 8, 7))
    finally:
        db.close()

    assert result.positions[0].quantity == 150
    assert result.positions[0].cost_price.quantize(Decimal("0.001")) == Decimal("4.667")
    assert result.positions[0].cost_amount == Decimal("700")
    assert result.positions[0].market_value == Decimal("1050")
    assert result.positions[0].unrealized_pnl == Decimal("350")


def test_asset_service_raises_when_no_settlement_records():
    db = _create_db()
    service = AssetService(
        stock_history_service=FakeStockHistoryService(),
        trade_calendar_service_instance=FakeTradeCalendarService(effective_trade_date=date(2025, 8, 7)),
        cache=SimpleTTLCache(),
    )

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

    service = AssetService(
        stock_history_service=FakeStockHistoryService(error=StockHistoryFetchError("no price")),
        trade_calendar_service_instance=FakeTradeCalendarService(effective_trade_date=date(2025, 8, 8)),
        cache=SimpleTTLCache(),
    )

    try:
        service.get_asset_detail(db=db, target_date=date(2025, 8, 8))
    except StockHistoryFetchError as exc:
        assert "no price" in str(exc)
    else:
        raise AssertionError("Expected StockHistoryFetchError")
    finally:
        db.close()


def test_asset_service_raises_when_trade_calendar_unavailable():
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
        ),
        trade_calendar_service_instance=FakeTradeCalendarService(error=TradeCalendarFetchError("calendar failed")),
        cache=SimpleTTLCache(),
    )

    try:
        service.get_asset_detail(db=db, target_date=date(2025, 8, 8))
    except TradeCalendarFetchError as exc:
        assert "calendar failed" in str(exc)
    else:
        raise AssertionError("Expected TradeCalendarFetchError")
    finally:
        db.close()


def test_asset_service_calculates_deposit_and_withdrawal_metrics():
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
            _record(
                occur_date=date(2025, 8, 8),
                occur_time="09:00:00",
                trade_type="利息归本",
                amount="0.13",
                cash_balance="4000.13",
            ),
        ]
    )
    db.commit()

    service = AssetService(
        stock_history_service=FakeStockHistoryService(),
        trade_calendar_service_instance=FakeTradeCalendarService(effective_trade_date=date(2025, 8, 8)),
        cache=SimpleTTLCache(),
    )

    try:
        result = service.get_asset_detail(db=db, target_date=date(2025, 8, 8))
    finally:
        db.close()

    assert result.total_deposit == Decimal("5000")
    assert result.total_withdrawal == Decimal("1000")
    assert result.net_deposit == Decimal("4000")
    assert result.cash_balance == Decimal("4000.13")


def test_asset_service_uses_cache_for_same_target_date():
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

    stock_service = FakeStockHistoryService(
        responses={"000597": _history("000597.SZ", [(date(2025, 8, 8), 5.6)])}
    )
    trade_calendar_service = FakeTradeCalendarService(effective_trade_date=date(2025, 8, 8))
    service = AssetService(
        stock_history_service=stock_service,
        trade_calendar_service_instance=trade_calendar_service,
        cache=SimpleTTLCache(),
    )

    try:
        first = service.get_asset_detail(db=db, target_date=date(2025, 8, 8))
        second = service.get_asset_detail(db=db, target_date=date(2025, 8, 8))
    finally:
        db.close()

    assert first == second
    assert len(stock_service.calls) == 1
    assert len(trade_calendar_service.calls) == 1


def test_asset_service_returns_cash_flows_in_desc_order_and_filters_types():
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
                trade_type="利息归本",
                amount="0.13",
                cash_balance="5000.13",
            ),
            _record(
                occur_date=date(2025, 8, 8),
                occur_time="10:00:00",
                trade_type="证券转银行",
                amount="-1000",
                cash_balance="4000.13",
            ),
        ]
    )
    db.commit()

    service = AssetService(cache=SimpleTTLCache())

    try:
        result = service.get_cash_flows(db=db, target_date=date(2025, 8, 8), limit=10)
    finally:
        db.close()

    assert result.count == 2
    assert result.items[0].trade_type == "证券转银行"
    assert result.items[0].amount == Decimal("-1000")
    assert result.items[1].trade_type == "银行转证券"


def test_asset_service_uses_cache_for_cash_flows():
    db = _create_db()
    db.add(
        _record(
            occur_date=date(2025, 8, 8),
            occur_time="09:00:00",
            trade_type="银行转证券",
            amount="5000",
            cash_balance="5000",
        )
    )
    db.commit()

    service = AssetService(cache=SimpleTTLCache())

    try:
        first = service.get_cash_flows(db=db, target_date=date(2025, 8, 8), limit=10)
        db.add(
            _record(
                occur_date=date(2025, 8, 8),
                occur_time="10:00:00",
                trade_type="证券转银行",
                amount="-1000",
                cash_balance="4000",
            )
        )
        db.commit()
        second = service.get_cash_flows(db=db, target_date=date(2025, 8, 8), limit=10)
    finally:
        db.close()

    assert first == second
    assert second.count == 1
