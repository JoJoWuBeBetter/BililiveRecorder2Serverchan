import asyncio
from datetime import date
from decimal import Decimal

from fastapi import HTTPException

from api.routers import asset_api
from schemas.asset import (
    AssetCashFlowItem,
    AssetCashFlowResponse,
    AssetDetailResponse,
    AssetSnapshotRebuildResponse,
)
from services.asset_service import AssetDetailNotFoundError
from services.stock_history_service import (
    StockHistoryConfigError,
    StockHistoryFetchError,
    StockHistoryPermissionError,
)
from services.trade_calendar_service import (
    TradeCalendarConfigError,
    TradeCalendarFetchError,
    TradeCalendarPermissionError,
)


def _response() -> AssetDetailResponse:
    return AssetDetailResponse(
        target_date=date(2025, 8, 8),
        pricing_trade_date=date(2025, 8, 8),
        cash_balance=Decimal("100"),
        total_deposit=Decimal("1000"),
        total_withdrawal=Decimal("200"),
        net_deposit=Decimal("800"),
        positions_market_value=Decimal("200"),
        total_assets=Decimal("300"),
        position_count=0,
        positions=[],
    )


def _cash_flow_response() -> AssetCashFlowResponse:
    return AssetCashFlowResponse(
        target_date=date(2025, 8, 8),
        count=1,
        items=[
            AssetCashFlowItem(
                occur_date=date(2025, 8, 8),
                occur_time="09:00:00",
                trade_type="银行转证券",
                amount=Decimal("1000"),
                cash_balance=Decimal("1000"),
            )
        ],
    )


def _rebuild_response() -> AssetSnapshotRebuildResponse:
    return AssetSnapshotRebuildResponse(
        mode="incremental",
        from_date=date(2025, 8, 8),
        to_date=date(2025, 8, 8),
        trade_day_count=1,
        security_count=1,
        snapshot_count=1,
        position_count=1,
        include_pricing=True,
    )
def _raise_snapshot_miss(**kwargs):
    raise AssetDetailNotFoundError("snapshot missing")


def _patch_normalize(monkeypatch, normalized=None):
    value = normalized or date(2025, 8, 8)
    monkeypatch.setattr(
        asset_api.trade_calendar_service,
        "normalize_to_trade_date",
        lambda *args, **kwargs: value,
    )


def test_asset_api_returns_service_result(monkeypatch):
    _patch_normalize(monkeypatch)
    monkeypatch.setattr(asset_api.account_snapshot_service, "get_snapshot_detail", _raise_snapshot_miss)
    monkeypatch.setattr(asset_api.asset_service, "get_asset_detail", lambda **kwargs: _response())

    result = asyncio.run(asset_api.get_asset_detail(target_date=date(2025, 8, 8), db=None))

    assert result.total_assets == Decimal("300")
    assert result.net_deposit == Decimal("800")


def test_asset_api_maps_not_found(monkeypatch):
    _patch_normalize(monkeypatch)
    monkeypatch.setattr(asset_api.account_snapshot_service, "get_snapshot_detail", _raise_snapshot_miss)
    def raise_not_found(**kwargs):
        raise AssetDetailNotFoundError("missing")

    monkeypatch.setattr(asset_api.asset_service, "get_asset_detail", raise_not_found)

    try:
        asyncio.run(asset_api.get_asset_detail(target_date=date(2025, 8, 8), db=None))
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Expected HTTPException")


def test_asset_api_maps_config_error(monkeypatch):
    _patch_normalize(monkeypatch)
    monkeypatch.setattr(asset_api.account_snapshot_service, "get_snapshot_detail", _raise_snapshot_miss)
    def raise_error(**kwargs):
        raise StockHistoryConfigError("token missing")

    monkeypatch.setattr(asset_api.asset_service, "get_asset_detail", raise_error)

    try:
        asyncio.run(asset_api.get_asset_detail(target_date=date(2025, 8, 8), db=None))
    except HTTPException as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("Expected HTTPException")


def test_asset_api_maps_permission_error(monkeypatch):
    _patch_normalize(monkeypatch)
    monkeypatch.setattr(asset_api.account_snapshot_service, "get_snapshot_detail", _raise_snapshot_miss)
    def raise_error(**kwargs):
        raise StockHistoryPermissionError("forbidden")

    monkeypatch.setattr(asset_api.asset_service, "get_asset_detail", raise_error)

    try:
        asyncio.run(asset_api.get_asset_detail(target_date=date(2025, 8, 8), db=None))
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException")


def test_asset_api_maps_fetch_error(monkeypatch):
    _patch_normalize(monkeypatch)
    monkeypatch.setattr(asset_api.account_snapshot_service, "get_snapshot_detail", _raise_snapshot_miss)
    def raise_error(**kwargs):
        raise StockHistoryFetchError("failed")

    monkeypatch.setattr(asset_api.asset_service, "get_asset_detail", raise_error)

    try:
        asyncio.run(asset_api.get_asset_detail(target_date=date(2025, 8, 8), db=None))
    except HTTPException as exc:
        assert exc.status_code == 502
    else:
        raise AssertionError("Expected HTTPException")


def test_asset_api_maps_trade_calendar_config_error(monkeypatch):
    _patch_normalize(monkeypatch)
    monkeypatch.setattr(asset_api.account_snapshot_service, "get_snapshot_detail", _raise_snapshot_miss)
    def raise_error(**kwargs):
        raise TradeCalendarConfigError("token missing")

    monkeypatch.setattr(asset_api.asset_service, "get_asset_detail", raise_error)

    try:
        asyncio.run(asset_api.get_asset_detail(target_date=date(2025, 8, 8), db=None))
    except HTTPException as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("Expected HTTPException")


def test_asset_api_maps_trade_calendar_permission_error(monkeypatch):
    _patch_normalize(monkeypatch)
    monkeypatch.setattr(asset_api.account_snapshot_service, "get_snapshot_detail", _raise_snapshot_miss)
    def raise_error(**kwargs):
        raise TradeCalendarPermissionError("forbidden")

    monkeypatch.setattr(asset_api.asset_service, "get_asset_detail", raise_error)

    try:
        asyncio.run(asset_api.get_asset_detail(target_date=date(2025, 8, 8), db=None))
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException")


def test_asset_api_maps_trade_calendar_fetch_error(monkeypatch):
    _patch_normalize(monkeypatch)
    monkeypatch.setattr(asset_api.account_snapshot_service, "get_snapshot_detail", _raise_snapshot_miss)
    def raise_error(**kwargs):
        raise TradeCalendarFetchError("failed")

    monkeypatch.setattr(asset_api.asset_service, "get_asset_detail", raise_error)

    try:
        asyncio.run(asset_api.get_asset_detail(target_date=date(2025, 8, 8), db=None))
    except HTTPException as exc:
        assert exc.status_code == 502
    else:
        raise AssertionError("Expected HTTPException")


def test_asset_api_returns_cash_flow_result(monkeypatch):
    _patch_normalize(monkeypatch)
    monkeypatch.setattr(asset_api.asset_service, "get_cash_flows", lambda **kwargs: _cash_flow_response())

    result = asyncio.run(asset_api.get_asset_cash_flows(target_date=date(2025, 8, 8), limit=10, db=None))

    assert result.count == 1
    assert result.items[0].trade_type == "银行转证券"


def test_asset_api_cash_flows_maps_not_found(monkeypatch):
    _patch_normalize(monkeypatch)
    def raise_not_found(**kwargs):
        raise AssetDetailNotFoundError("missing")

    monkeypatch.setattr(asset_api.asset_service, "get_cash_flows", raise_not_found)

    try:
        asyncio.run(asset_api.get_asset_cash_flows(target_date=date(2025, 8, 8), limit=10, db=None))
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Expected HTTPException")


def test_asset_api_rebuild_snapshots_returns_service_result(monkeypatch):
    _patch_normalize(monkeypatch)
    monkeypatch.setattr(asset_api.account_snapshot_service, "rebuild_snapshots", lambda **kwargs: _rebuild_response())

    result = asyncio.run(
        asset_api.rebuild_asset_snapshots(mode="incremental", from_date=date(2025, 8, 8), include_pricing=True, db=None)
    )

    assert result.snapshot_count == 1
    assert result.include_pricing is True


def test_asset_api_get_snapshot_detail_returns_service_result(monkeypatch):
    _patch_normalize(monkeypatch)
    monkeypatch.setattr(asset_api.account_snapshot_service, "get_snapshot_detail", lambda **kwargs: _response())

    result = asyncio.run(asset_api.get_asset_snapshot_detail(snapshot_date=date(2025, 8, 8), db=None))

    assert result.total_assets == Decimal("300")
