from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from models.account_snapshot import AccountDailyPosition, AccountDailySnapshot, SecurityDailyPrice


def get_latest_snapshot_date(db: Session) -> Optional[date]:
    latest = (
        db.query(AccountDailySnapshot.snapshot_date)
        .order_by(AccountDailySnapshot.snapshot_date.desc())
        .first()
    )
    if latest is None:
        return None
    return latest[0]


def get_snapshot_on_date(db: Session, snapshot_date: date) -> Optional[AccountDailySnapshot]:
    return (
        db.query(AccountDailySnapshot)
        .filter(AccountDailySnapshot.snapshot_date == snapshot_date)
        .first()
    )


def get_snapshot_positions_on_date(db: Session, snapshot_date: date) -> list[AccountDailyPosition]:
    return (
        db.query(AccountDailyPosition)
        .filter(AccountDailyPosition.snapshot_date == snapshot_date)
        .order_by(AccountDailyPosition.security_code.asc())
        .all()
    )


def get_latest_snapshot_before(db: Session, before_date: date) -> Optional[AccountDailySnapshot]:
    return (
        db.query(AccountDailySnapshot)
        .filter(AccountDailySnapshot.snapshot_date < before_date)
        .order_by(AccountDailySnapshot.snapshot_date.desc())
        .first()
    )


def get_snapshot_positions_map(db: Session, snapshot_date: date) -> dict[str, AccountDailyPosition]:
    rows = get_snapshot_positions_on_date(db, snapshot_date)
    return {row.security_code: row for row in rows}


def delete_snapshots_from_date(db: Session, from_date: date) -> None:
    db.query(AccountDailyPosition).filter(AccountDailyPosition.snapshot_date >= from_date).delete(
        synchronize_session=False
    )
    db.query(AccountDailySnapshot).filter(AccountDailySnapshot.snapshot_date >= from_date).delete(
        synchronize_session=False
    )
    db.commit()


def replace_security_prices(
    db: Session,
    security_code: str,
    start_date: date,
    end_date: date,
    rows: list[SecurityDailyPrice],
) -> int:
    db.query(SecurityDailyPrice).filter(
        SecurityDailyPrice.security_code == security_code,
        SecurityDailyPrice.trade_date >= start_date,
        SecurityDailyPrice.trade_date <= end_date,
    ).delete(synchronize_session=False)
    if rows:
        db.add_all(rows)
    db.commit()
    return len(rows)


def get_security_prices_in_range(
    db: Session,
    security_codes: list[str],
    start_date: date,
    end_date: date,
) -> list[SecurityDailyPrice]:
    if not security_codes:
        return []

    return (
        db.query(SecurityDailyPrice)
        .filter(SecurityDailyPrice.security_code.in_(security_codes))
        .filter(SecurityDailyPrice.trade_date >= start_date)
        .filter(SecurityDailyPrice.trade_date <= end_date)
        .order_by(SecurityDailyPrice.security_code.asc(), SecurityDailyPrice.trade_date.asc())
        .all()
    )


def get_latest_security_price_on_or_before(
    db: Session,
    security_code: str,
    target_date: date,
) -> Optional[SecurityDailyPrice]:
    return (
        db.query(SecurityDailyPrice)
        .filter(SecurityDailyPrice.security_code == security_code)
        .filter(SecurityDailyPrice.trade_date <= target_date)
        .order_by(SecurityDailyPrice.trade_date.desc())
        .first()
    )


def replace_snapshots(
    db: Session,
    snapshots: list[AccountDailySnapshot],
    positions: list[AccountDailyPosition],
) -> tuple[int, int]:
    if snapshots:
        db.add_all(snapshots)
    if positions:
        db.add_all(positions)
    db.commit()
    return len(snapshots), len(positions)
