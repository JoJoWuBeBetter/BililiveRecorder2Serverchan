import asyncio
from datetime import date
from decimal import Decimal

from fastapi import HTTPException

from api.routers import asset_api
from schemas.asset import AssetDetailResponse
from services.asset_service import AssetDetailNotFoundError
from services.stock_history_service import (
    StockHistoryConfigError,
    StockHistoryFetchError,
    StockHistoryPermissionError,
)


def _response() -> AssetDetailResponse:
    return AssetDetailResponse(
        target_date=date(2025, 8, 8),
        pricing_trade_date=date(2025, 8, 8),
        cash_balance=Decimal("100"),
        positions_market_value=Decimal("200"),
        total_assets=Decimal("300"),
        position_count=0,
        positions=[],
    )


def test_asset_api_returns_service_result(monkeypatch):
    monkeypatch.setattr(asset_api.asset_service, "get_asset_detail", lambda **kwargs: _response())

    result = asyncio.run(asset_api.get_asset_detail(target_date=date(2025, 8, 8), db=None))

    assert result.total_assets == Decimal("300")


def test_asset_api_maps_not_found(monkeypatch):
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
    def raise_error(**kwargs):
        raise StockHistoryFetchError("failed")

    monkeypatch.setattr(asset_api.asset_service, "get_asset_detail", raise_error)

    try:
        asyncio.run(asset_api.get_asset_detail(target_date=date(2025, 8, 8), db=None))
    except HTTPException as exc:
        assert exc.status_code == 502
    else:
        raise AssertionError("Expected HTTPException")
