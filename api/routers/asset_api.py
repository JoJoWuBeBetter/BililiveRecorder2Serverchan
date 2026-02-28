from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import SessionLocal
from schemas.asset import (
    AssetCashFlowResponse,
    AssetDetailResponse,
    AssetSnapshotRebuildResponse,
)
from services.account_snapshot_service import account_snapshot_service
from services.asset_service import AssetDetailNotFoundError, asset_service
from services.stock_history_service import (
    StockHistoryConfigError,
    StockHistoryFetchError,
    StockHistoryPermissionError,
)
from services.trade_calendar_service import (
    TradeCalendarConfigError,
    TradeCalendarFetchError,
    TradeCalendarPermissionError,
    trade_calendar_service,
)

router = APIRouter(
    prefix="/assets",
    tags=["Asset Detail"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/detail", response_model=AssetDetailResponse)
async def get_asset_detail(
    target_date: Annotated[Optional[date], Query(description="目标日期，格式 YYYY-MM-DD")] = None,
    db: Session = Depends(get_db),
):
    try:
        requested_date = target_date or date.today()
        normalized_date = trade_calendar_service.normalize_to_trade_date(requested_date, db=db)
        if normalized_date is not None:
            try:
                return account_snapshot_service.get_snapshot_detail(db=db, snapshot_date=normalized_date)
            except AssetDetailNotFoundError:
                pass
        return asset_service.get_asset_detail(db=db, target_date=normalized_date)
    except AssetDetailNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except StockHistoryConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except TradeCalendarConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except StockHistoryPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except TradeCalendarPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except StockHistoryFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except TradeCalendarFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get("/cash-flows", response_model=AssetCashFlowResponse)
async def get_asset_cash_flows(
    target_date: Annotated[Optional[date], Query(description="目标日期，格式 YYYY-MM-DD")] = None,
    limit: Annotated[int, Query(ge=1, le=50, description="返回数量，范围 1-50")] = 10,
    db: Session = Depends(get_db),
):
    try:
        requested_date = target_date or date.today()
        normalized_date = trade_calendar_service.normalize_to_trade_date(requested_date, db=db)
        return asset_service.get_cash_flows(db=db, target_date=normalized_date, limit=limit)
    except AssetDetailNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except TradeCalendarConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except TradeCalendarPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TradeCalendarFetchError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/snapshots/rebuild", response_model=AssetSnapshotRebuildResponse)
async def rebuild_asset_snapshots(
    mode: Annotated[str, Query(pattern="^(full|incremental)$")] = "incremental",
    from_date: Annotated[Optional[date], Query(description="重建起始日期，格式 YYYY-MM-DD")] = None,
    include_pricing: Annotated[bool, Query(description="是否同步行情并回填估值")] = True,
    db: Session = Depends(get_db),
):
    try:
        normalized_from_date = (
            trade_calendar_service.normalize_to_trade_date(from_date, db=db)
            if from_date is not None
            else None
        )
        return account_snapshot_service.rebuild_snapshots(
            db=db,
            mode=mode,
            from_date=normalized_from_date,
            include_pricing=include_pricing,
        )
    except AssetDetailNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except StockHistoryConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except TradeCalendarConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except StockHistoryPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except TradeCalendarPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except StockHistoryFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except TradeCalendarFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get("/snapshots/{snapshot_date}", response_model=AssetDetailResponse)
async def get_asset_snapshot_detail(
    snapshot_date: date,
    db: Session = Depends(get_db),
):
    try:
        normalized_date = trade_calendar_service.normalize_to_trade_date(snapshot_date, db=db)
        return account_snapshot_service.get_snapshot_detail(db=db, snapshot_date=normalized_date)
    except AssetDetailNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except TradeCalendarConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except TradeCalendarPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TradeCalendarFetchError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
