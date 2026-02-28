from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, status

from schemas.stock import AdjustmentType, StockHistoryResponse
from services.stock_history_service import (
    StockHistoryConfigError,
    StockHistoryFetchError,
    StockHistoryPermissionError,
    StockHistoryService,
)

router = APIRouter(
    prefix="/stocks",
    tags=["Stock Data"],
)

stock_history_service = StockHistoryService()


@router.get("/{ts_code}/history", response_model=StockHistoryResponse)
async def get_stock_history(
    ts_code: str,
    start_date: Annotated[Optional[date], Query(description="起始日期，格式 YYYY-MM-DD")] = None,
    end_date: Annotated[Optional[date], Query(description="结束日期，格式 YYYY-MM-DD")] = None,
    trade_date: Annotated[Optional[date], Query(description="单日日期，格式 YYYY-MM-DD")] = None,
    adjust: Annotated[AdjustmentType, Query(description="复权方式")] = AdjustmentType.NONE,
):
    if trade_date and (start_date or end_date):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="trade_date 与 start_date/end_date 不能同时传入",
        )

    if not any((start_date, end_date, trade_date)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="必须至少提供 start_date、end_date 或 trade_date 之一",
        )

    try:
        return stock_history_service.get_stock_history(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            trade_date=trade_date,
            adjust=adjust,
        )
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
