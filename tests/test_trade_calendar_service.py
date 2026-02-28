from datetime import date, datetime

from services.simple_cache import SimpleTTLCache
from services.trade_calendar_service import (
    TradeCalendarConfigError,
    TradeCalendarDay,
    TradeCalendarFetchError,
    TradeCalendarPermissionError,
    TradeCalendarService,
)


class FakeDataFrame:
    def __init__(self, records):
        self._records = records

    @property
    def empty(self):
        return len(self._records) == 0

    def to_dict(self, orient):
        assert orient == "records"
        return list(self._records)


class FakeProClient:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def trade_cal(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeTushareModule:
    def __init__(self, pro_client):
        self.pro_client = pro_client
        self.tokens = []

    def pro_api(self, token):
        self.tokens.append(token)
        return self.pro_client


def test_trade_calendar_service_returns_calendar_day(monkeypatch):
    service = TradeCalendarService(cache=SimpleTTLCache())
    monkeypatch.setattr(
        service,
        "_get_calendar_day_with_db",
        lambda db, trade_date, exchange: TradeCalendarDay(
            exchange=exchange,
            cal_date=trade_date,
            is_open=True,
            pretrade_date=date(2025, 8, 7),
        ),
    )

    result = service.get_calendar_day(date(2025, 8, 8))

    assert result.exchange == "SSE"
    assert result.is_open is True
    assert result.pretrade_date == date(2025, 8, 7)


def test_trade_calendar_service_returns_previous_trade_day_for_holiday(monkeypatch):
    service = TradeCalendarService(cache=SimpleTTLCache())
    monkeypatch.setattr(
        service,
        "get_calendar_day",
        lambda trade_date, exchange="SSE", db=None: type(
            "FakeCalendarDay",
            (),
            {
                "exchange": exchange,
                "cal_date": trade_date,
                "is_open": False,
                "pretrade_date": date(2025, 10, 8),
            },
        )(),
    )

    result = service.get_effective_trade_date(date(2025, 10, 9), now=datetime(2025, 10, 9, 16, 0, 0))

    assert result == date(2025, 10, 8)


def test_trade_calendar_service_uses_previous_trade_day_before_close(monkeypatch):
    service = TradeCalendarService(cache=SimpleTTLCache())
    monkeypatch.setattr(
        service,
        "get_calendar_day",
        lambda trade_date, exchange="SSE", db=None: type(
            "FakeCalendarDay",
            (),
            {
                "exchange": exchange,
                "cal_date": trade_date,
                "is_open": True,
                "pretrade_date": date(2025, 8, 7),
            },
        )(),
    )

    result = service.get_effective_trade_date(date(2025, 8, 8), now=datetime(2025, 8, 8, 14, 30, 0))

    assert result == date(2025, 8, 7)


def test_trade_calendar_service_uses_same_day_after_close(monkeypatch):
    service = TradeCalendarService(cache=SimpleTTLCache())
    monkeypatch.setattr(
        service,
        "get_calendar_day",
        lambda trade_date, exchange="SSE", db=None: type(
            "FakeCalendarDay",
            (),
            {
                "exchange": exchange,
                "cal_date": trade_date,
                "is_open": True,
                "pretrade_date": date(2025, 8, 7),
            },
        )(),
    )

    result = service.get_effective_trade_date(date(2025, 8, 8), now=datetime(2025, 8, 8, 15, 1, 0))

    assert result == date(2025, 8, 8)


def test_trade_calendar_service_raises_config_error_without_token(monkeypatch):
    service = TradeCalendarService(cache=SimpleTTLCache())
    monkeypatch.setattr(
        service,
        "_get_calendar_day_with_db",
        lambda db, trade_date, exchange: (_ for _ in ()).throw(TradeCalendarConfigError("TUSHARE_TOKEN 未配置")),
    )

    try:
        service.get_calendar_day(date(2025, 8, 8))
    except TradeCalendarConfigError as exc:
        assert "TUSHARE_TOKEN" in str(exc)
    else:
        raise AssertionError("Expected TradeCalendarConfigError")


def test_trade_calendar_service_maps_permission_error(monkeypatch):
    service = TradeCalendarService(cache=SimpleTTLCache())
    monkeypatch.setattr(
        service,
        "_get_calendar_day_with_db",
        lambda db, trade_date, exchange: (_ for _ in ()).throw(TradeCalendarPermissionError("权限不足")),
    )

    try:
        service.get_calendar_day(date(2025, 8, 8))
    except TradeCalendarPermissionError:
        pass
    else:
        raise AssertionError("Expected TradeCalendarPermissionError")


def test_trade_calendar_service_raises_fetch_error_for_empty_rows(monkeypatch):
    service = TradeCalendarService(cache=SimpleTTLCache())
    monkeypatch.setattr(
        service,
        "_get_calendar_day_with_db",
        lambda db, trade_date, exchange: (_ for _ in ()).throw(
            TradeCalendarFetchError(f"{exchange} 在 {trade_date} 没有交易日历数据")
        ),
    )

    try:
        service.get_calendar_day(date(2025, 8, 8))
    except TradeCalendarFetchError as exc:
        assert "没有交易日历数据" in str(exc)
    else:
        raise AssertionError("Expected TradeCalendarFetchError")


def test_trade_calendar_service_uses_cache_for_same_day(monkeypatch):
    service = TradeCalendarService(cache=SimpleTTLCache())
    state = {"count": 0}

    def fake_get_calendar_day_with_db(db, trade_date, exchange):
        state["count"] += 1
        return TradeCalendarDay(
            exchange=exchange,
            cal_date=trade_date,
            is_open=True,
            pretrade_date=date(2025, 8, 7),
        )

    monkeypatch.setattr(service, "_get_calendar_day_with_db", fake_get_calendar_day_with_db)

    first = service.get_calendar_day(date(2025, 8, 8))
    second = service.get_calendar_day(date(2025, 8, 8))

    assert first == second
    assert state["count"] == 1


def test_trade_calendar_service_prewarms_recent_trade_days(monkeypatch):
    service = TradeCalendarService(cache=SimpleTTLCache())
    captured = {}

    monkeypatch.setattr(
        service,
        "_now_shanghai",
        lambda: datetime(2025, 8, 8, 16, 0, 0),
    )

    def fake_get_trade_days(start_date, end_date, exchange="SSE", db=None):
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        captured["exchange"] = exchange
        return [date(2025, 8, 7), date(2025, 8, 8)]

    monkeypatch.setattr(service, "get_trade_days", fake_get_trade_days)

    result = service.prewarm_recent_trade_days(days=30)

    assert result == 2
    assert captured["start_date"] == date(2025, 7, 9)
    assert captured["end_date"] == date(2025, 8, 8)
    assert captured["exchange"] == "SSE"


def test_trade_calendar_service_prewarm_can_fail_silently(monkeypatch):
    service = TradeCalendarService(cache=SimpleTTLCache())

    monkeypatch.setattr(
        service,
        "get_trade_days",
        lambda *args, **kwargs: (_ for _ in ()).throw(TradeCalendarFetchError("failed")),
    )

    result = service.prewarm_recent_trade_days(silent=True)

    assert result == 0
