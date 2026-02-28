import asyncio
from datetime import date

from fastapi import HTTPException

from api.routers import stock_api
from schemas.stock import AdjustmentType, StockDailyBar, StockHistoryQuery, StockHistoryResponse
from services.simple_cache import SimpleTTLCache
from services.stock_history_service import (
    StockHistoryConfigError,
    StockHistoryFetchError,
    StockHistoryPermissionError,
    StockHistoryService,
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


class FakeTushareModule:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []
        self.token = None

    def set_token(self, token):
        self.token = token

    def pro_bar(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        if isinstance(self.result, dict):
            return self.result.get(kwargs.get("asset"))
        return self.result


def test_stock_history_service_none_adjust_returns_sorted_items(monkeypatch):
    service = StockHistoryService(cache=SimpleTTLCache())
    fake_ts = FakeTushareModule(
        result=FakeDataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240103",
                    "open": 11,
                    "high": 12,
                    "low": 10,
                    "close": 11.5,
                    "pre_close": 10.5,
                    "change": 1,
                    "pct_chg": 9.5238,
                    "vol": 1000,
                    "amount": 2000,
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240102",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10.5,
                    "pre_close": 10,
                    "change": 0.5,
                    "pct_chg": 5,
                    "vol": 900,
                    "amount": 1800,
                },
            ]
        )
    )

    monkeypatch.setattr("services.stock_history_service.get_tushare_token", lambda: "token")
    monkeypatch.setattr(service, "_get_tushare_module", lambda: fake_ts)

    result = service.get_stock_history(
        ts_code="000001.SZ",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
        adjust=AdjustmentType.NONE,
    )

    assert result.count == 2
    assert [item.trade_date for item in result.items] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert fake_ts.token == "token"
    assert fake_ts.calls == [
        {
            "ts_code": "000001.SZ",
            "start_date": "20240102",
            "end_date": "20240103",
            "adj": None,
            "asset": "E",
            "freq": "D",
        }
    ]


def test_stock_history_service_trade_date_maps_to_single_day(monkeypatch):
    service = StockHistoryService(cache=SimpleTTLCache())
    fake_ts = FakeTushareModule(result=FakeDataFrame([]))

    monkeypatch.setattr("services.stock_history_service.get_tushare_token", lambda: "token")
    monkeypatch.setattr(service, "_get_tushare_module", lambda: fake_ts)

    result = service.get_stock_history(
        ts_code="000001.SZ",
        trade_date=date(2024, 1, 5),
        adjust=AdjustmentType.QFQ,
    )

    assert result.count == 0
    assert fake_ts.calls[0]["start_date"] == "20240105"
    assert fake_ts.calls[0]["end_date"] == "20240105"
    assert fake_ts.calls[0]["adj"] == "qfq"


def test_stock_history_service_auto_appends_exchange_suffix(monkeypatch):
    service = StockHistoryService(cache=SimpleTTLCache())
    fake_ts = FakeTushareModule(result=FakeDataFrame([]))

    monkeypatch.setattr("services.stock_history_service.get_tushare_token", lambda: "token")
    monkeypatch.setattr(service, "_get_tushare_module", lambda: fake_ts)

    result = service.get_stock_history(
        ts_code="603599",
        trade_date=date(2024, 1, 5),
    )

    assert result.ts_code == "603599.SH"
    assert fake_ts.calls[0]["ts_code"] == "603599.SH"


def test_stock_history_service_falls_back_to_fund_asset(monkeypatch):
    service = StockHistoryService(cache=SimpleTTLCache())
    fake_ts = FakeTushareModule(
        result={
            "FD": FakeDataFrame(
                [
                    {
                        "ts_code": "563230.SH",
                        "trade_date": "20260227",
                        "open": 1.5,
                        "high": 1.6,
                        "low": 1.4,
                        "close": 1.55,
                        "pre_close": 1.5,
                        "change": 0.05,
                        "pct_chg": 3.33,
                        "vol": 1000,
                        "amount": 1550,
                    }
                ]
            ),
            "E": FakeDataFrame([]),
        }
    )

    monkeypatch.setattr("services.stock_history_service.get_tushare_token", lambda: "token")
    monkeypatch.setattr(service, "_get_tushare_module", lambda: fake_ts)

    result = service.get_stock_history(
        ts_code="563230",
        trade_date=date(2026, 2, 27),
    )

    assert result.count == 1
    assert result.items[0].close == 1.55
    assert fake_ts.calls[0]["asset"] == "FD"


def test_stock_history_service_raises_config_error_without_token(monkeypatch):
    service = StockHistoryService(cache=SimpleTTLCache())
    monkeypatch.setattr("services.stock_history_service.get_tushare_token", lambda: None)

    try:
        service.get_stock_history(ts_code="000001.SZ", trade_date=date(2024, 1, 5))
    except StockHistoryConfigError as exc:
        assert "TUSHARE_TOKEN" in str(exc)
    else:
        raise AssertionError("Expected StockHistoryConfigError")


def test_stock_history_service_maps_permission_error(monkeypatch):
    service = StockHistoryService(cache=SimpleTTLCache())
    fake_ts = FakeTushareModule(error=Exception("权限不足"))

    monkeypatch.setattr("services.stock_history_service.get_tushare_token", lambda: "token")
    monkeypatch.setattr(service, "_get_tushare_module", lambda: fake_ts)

    try:
        service.get_stock_history(ts_code="000001.SZ", trade_date=date(2024, 1, 5))
    except StockHistoryPermissionError:
        pass
    else:
        raise AssertionError("Expected StockHistoryPermissionError")


def test_stock_history_service_maps_fetch_error(monkeypatch):
    service = StockHistoryService(cache=SimpleTTLCache())
    fake_ts = FakeTushareModule(error=Exception("network failed"))

    monkeypatch.setattr("services.stock_history_service.get_tushare_token", lambda: "token")
    monkeypatch.setattr(service, "_get_tushare_module", lambda: fake_ts)

    try:
        service.get_stock_history(ts_code="000001.SZ", trade_date=date(2024, 1, 5))
    except StockHistoryFetchError as exc:
        assert "network failed" in str(exc)
    else:
        raise AssertionError("Expected StockHistoryFetchError")


def test_stock_api_rejects_conflicting_dates():
    try:
        asyncio.run(
            stock_api.get_stock_history(
                ts_code="000001.SZ",
                start_date=date(2024, 1, 1),
                trade_date=date(2024, 1, 2),
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("Expected HTTPException")


def test_stock_api_rejects_missing_dates():
    try:
        asyncio.run(stock_api.get_stock_history(ts_code="000001.SZ"))
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("Expected HTTPException")


def test_stock_api_maps_service_errors(monkeypatch):
    def raise_permission(*args, **kwargs):
        raise StockHistoryPermissionError("权限不足")

    monkeypatch.setattr(stock_api.stock_history_service, "get_stock_history", raise_permission)

    try:
        asyncio.run(
            stock_api.get_stock_history(
                ts_code="000001.SZ",
                trade_date=date(2024, 1, 2),
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException")


def test_stock_api_returns_service_result(monkeypatch):
    expected = StockHistoryResponse(
        ts_code="000001.SZ",
        adjust=AdjustmentType.HFQ,
        query=StockHistoryQuery(trade_date=date(2024, 1, 2)),
        count=1,
        items=[
            StockDailyBar(
                ts_code="000001.SZ",
                trade_date=date(2024, 1, 2),
                open=10.0,
                high=11.0,
                low=9.0,
                close=10.5,
                pre_close=10.0,
                change=0.5,
                pct_chg=5.0,
                vol=100.0,
                amount=200.0,
            )
        ],
    )

    def fake_get_stock_history(**kwargs):
        assert kwargs["adjust"] == AdjustmentType.HFQ
        return expected

    monkeypatch.setattr(stock_api.stock_history_service, "get_stock_history", fake_get_stock_history)

    result = asyncio.run(
        stock_api.get_stock_history(
            ts_code="000001.SZ",
            trade_date=date(2024, 1, 2),
            adjust=AdjustmentType.HFQ,
        )
    )

    assert result == expected


def test_stock_history_service_uses_cache_for_same_query(monkeypatch):
    service = StockHistoryService(cache=SimpleTTLCache())
    fake_ts = FakeTushareModule(
        result=FakeDataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240105",
                    "open": 10,
                    "high": 10,
                    "low": 10,
                    "close": 10,
                    "pre_close": 10,
                    "change": 0,
                    "pct_chg": 0,
                    "vol": 1,
                    "amount": 1,
                }
            ]
        )
    )

    monkeypatch.setattr("services.stock_history_service.get_tushare_token", lambda: "token")
    monkeypatch.setattr(service, "_get_tushare_module", lambda: fake_ts)

    first = service.get_stock_history(ts_code="000001.SZ", trade_date=date(2024, 1, 5))
    second = service.get_stock_history(ts_code="000001.SZ", trade_date=date(2024, 1, 5))

    assert first == second
    assert len(fake_ts.calls) == 1
