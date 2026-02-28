from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from models.trade_calendar import TradeCalendarDayRecord


def get_trade_calendar_day(
    db: Session,
    exchange: str,
    cal_date: date,
) -> Optional[TradeCalendarDayRecord]:
    return (
        db.query(TradeCalendarDayRecord)
        .filter(
            TradeCalendarDayRecord.exchange == exchange,
            TradeCalendarDayRecord.cal_date == cal_date,
        )
        .first()
    )


def get_trade_calendar_days_in_range(
    db: Session,
    exchange: str,
    start_date: date,
    end_date: date,
) -> list[TradeCalendarDayRecord]:
    return (
        db.query(TradeCalendarDayRecord)
        .filter(
            TradeCalendarDayRecord.exchange == exchange,
            TradeCalendarDayRecord.cal_date >= start_date,
            TradeCalendarDayRecord.cal_date <= end_date,
        )
        .order_by(TradeCalendarDayRecord.cal_date.asc())
        .all()
    )


def upsert_trade_calendar_days(
    db: Session,
    rows: list[dict[str, object]],
) -> int:
    count = 0
    for row in rows:
        existing = get_trade_calendar_day(
            db=db,
            exchange=str(row["exchange"]),
            cal_date=row["cal_date"],  # type: ignore[arg-type]
        )
        if existing is None:
            existing = TradeCalendarDayRecord(
                exchange=str(row["exchange"]),
                cal_date=row["cal_date"],  # type: ignore[arg-type]
            )
            db.add(existing)

        existing.is_open = bool(row["is_open"])
        existing.pretrade_date = row.get("pretrade_date")  # type: ignore[assignment]
        existing.source = str(row.get("source") or "tushare")
        count += 1

    if count:
        db.commit()
    return count


def get_prev_open_trade_day(
    db: Session,
    exchange: str,
    base_date: date,
) -> Optional[TradeCalendarDayRecord]:
    return (
        db.query(TradeCalendarDayRecord)
        .filter(
            TradeCalendarDayRecord.exchange == exchange,
            TradeCalendarDayRecord.is_open.is_(True),
            TradeCalendarDayRecord.cal_date < base_date,
        )
        .order_by(TradeCalendarDayRecord.cal_date.desc())
        .first()
    )


def get_next_open_trade_day(
    db: Session,
    exchange: str,
    base_date: date,
) -> Optional[TradeCalendarDayRecord]:
    return (
        db.query(TradeCalendarDayRecord)
        .filter(
            TradeCalendarDayRecord.exchange == exchange,
            TradeCalendarDayRecord.is_open.is_(True),
            TradeCalendarDayRecord.cal_date > base_date,
        )
        .order_by(TradeCalendarDayRecord.cal_date.asc())
        .first()
    )
