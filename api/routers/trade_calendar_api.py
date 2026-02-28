from calendar import monthrange
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from crud.trade_calendar_crud import get_trade_calendar_days_in_range
from database import SessionLocal
from schemas.trade_calendar import (
    TradeCalendarAdjacentResponse,
    TradeCalendarDayItem,
    TradeCalendarMonthResponse,
    TradeCalendarNormalizeResponse,
)
from services.trade_calendar_service import (
    TradeCalendarConfigError,
    TradeCalendarFetchError,
    TradeCalendarPermissionError,
    trade_calendar_service,
)

router = APIRouter(
    prefix="/trade-calendar",
    tags=["Trade Calendar"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/month", response_model=TradeCalendarMonthResponse)
async def get_trade_calendar_month(
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
    exchange: str = Query(default="SSE"),
    db: Session = Depends(get_db),
):
    try:
        start_date = date(year, month, 1)
        end_date = date(year, month, monthrange(year, month)[1])
        trade_calendar_service.get_trade_days(start_date=start_date, end_date=end_date, exchange=exchange, db=db)
        rows = get_trade_calendar_days_in_range(db=db, exchange=exchange, start_date=start_date, end_date=end_date)
        return TradeCalendarMonthResponse(
            year=year,
            month=month,
            exchange=exchange,
            items=[
                TradeCalendarDayItem(
                    cal_date=row.cal_date,
                    is_open=bool(row.is_open),
                    pretrade_date=row.pretrade_date,
                )
                for row in rows
            ],
        )
    except TradeCalendarConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except TradeCalendarPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TradeCalendarFetchError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/normalize", response_model=TradeCalendarNormalizeResponse)
async def normalize_trade_calendar_date(
    target_date: Annotated[date, Query(alias="date")],
    exchange: str = Query(default="SSE"),
    db: Session = Depends(get_db),
):
    try:
        calendar_day = trade_calendar_service.get_calendar_day(target_date, exchange=exchange, db=db)
        effective_date = trade_calendar_service.normalize_to_trade_date(target_date, exchange=exchange, db=db)
        return TradeCalendarNormalizeResponse(
            requested_date=target_date,
            effective_date=effective_date,
            is_trade_day=calendar_day.is_open,
        )
    except TradeCalendarConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except TradeCalendarPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TradeCalendarFetchError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/adjacent", response_model=TradeCalendarAdjacentResponse)
async def get_adjacent_trade_calendar_date(
    target_date: Annotated[date, Query(alias="date")],
    direction: Annotated[str, Query(pattern="^(prev|next)$")],
    exchange: str = Query(default="SSE"),
    db: Session = Depends(get_db),
):
    try:
        effective_date = trade_calendar_service.get_adjacent_trade_day(
            base_date=target_date,
            direction=direction,
            exchange=exchange,
            db=db,
        )
        return TradeCalendarAdjacentResponse(
            requested_date=target_date,
            effective_date=effective_date,
            direction=direction,
        )
    except TradeCalendarConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except TradeCalendarPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TradeCalendarFetchError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
