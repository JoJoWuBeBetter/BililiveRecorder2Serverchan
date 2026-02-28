from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from models.settlement import SettlementRecord


def get_existing_hashes(db: Session, hashes: list[str]) -> set[str]:
    if not hashes:
        return set()

    rows = (
        db.query(SettlementRecord.source_hash)
        .filter(SettlementRecord.source_hash.in_(hashes))
        .all()
    )
    return {row[0] for row in rows}


def bulk_create_settlements(db: Session, records: list[SettlementRecord]) -> int:
    if not records:
        return 0

    db.add_all(records)
    db.commit()
    return len(records)


def list_settlements(
    db: Session,
    limit: int = 100,
    offset: int = 0,
    security_code: Optional[str] = None,
    trade_type: Optional[str] = None,
    occur_date: Optional[date] = None,
) -> tuple[int, list[SettlementRecord]]:
    query = db.query(SettlementRecord)

    if security_code:
        query = query.filter(SettlementRecord.security_code == security_code)
    if trade_type:
        query = query.filter(SettlementRecord.trade_type == trade_type)
    if occur_date:
        query = query.filter(SettlementRecord.occur_date == occur_date)

    total_count = query.count()
    items = (
        query.order_by(
            SettlementRecord.occur_date.desc(),
            SettlementRecord.occur_time.desc(),
            SettlementRecord.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total_count, items
