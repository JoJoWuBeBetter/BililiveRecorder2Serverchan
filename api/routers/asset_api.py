from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import SessionLocal
from schemas.asset import AssetDetailResponse
from services.asset_service import AssetDetailNotFoundError, asset_service
from services.stock_history_service import (
    StockHistoryConfigError,
    StockHistoryFetchError,
    StockHistoryPermissionError,
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
        return asset_service.get_asset_detail(db=db, target_date=target_date)
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
    except StockHistoryPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except StockHistoryFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
