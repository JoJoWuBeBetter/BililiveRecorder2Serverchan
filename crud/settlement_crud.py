# crud/settlement_crud.py
from typing import Iterable, List, Optional, Set
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.settlement import AccountDailySummary, SettlementImportBatch, SettlementRecord


def create_import_batch(db: Session, batch: SettlementImportBatch) -> SettlementImportBatch:
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def update_import_batch(db: Session, batch: SettlementImportBatch) -> SettlementImportBatch:
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def list_import_batches(db: Session, limit: int = 50) -> List[SettlementImportBatch]:
    return (
        db.query(SettlementImportBatch)
        .order_by(SettlementImportBatch.created_at.desc())
        .limit(limit)
        .all()
    )


def get_import_batch(db: Session, batch_id: UUID) -> Optional[SettlementImportBatch]:
    return db.query(SettlementImportBatch).filter(SettlementImportBatch.id == batch_id).first()


def create_settlement_records(db: Session, records: List[SettlementRecord]) -> None:
    if not records:
        return
    db.add_all(records)
    db.commit()


def list_settlement_records(
    db: Session,
    batch_id: Optional[UUID] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[SettlementRecord]:
    query = db.query(SettlementRecord).order_by(SettlementRecord.trade_date.desc(), SettlementRecord.trade_time.desc())
    if batch_id:
        query = query.filter(SettlementRecord.batch_id == batch_id)
    return query.offset(offset).limit(limit).all()


def get_daily_summary(db: Session, summary_date) -> Optional[AccountDailySummary]:
    return (
        db.query(AccountDailySummary)
        .filter(AccountDailySummary.summary_date == summary_date)
        .first()
    )


def upsert_daily_summary(db: Session, summary: AccountDailySummary) -> AccountDailySummary:
    existing = get_daily_summary(db, summary.summary_date)
    if existing:
        existing.total_asset_cent = summary.total_asset_cent
        existing.cash_balance_cent = summary.cash_balance_cent
        existing.total_market_value_cent = summary.total_market_value_cent
        existing.position_ratio = summary.position_ratio
        db.commit()
        db.refresh(existing)
        return existing

    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


def get_existing_serials(db: Session, serials: Iterable[str]) -> Set[str]:
    serials = [s for s in serials if s]
    if not serials:
        return set()
    rows = db.execute(select(SettlementRecord.serial_no).where(SettlementRecord.serial_no.in_(serials))).all()
    return {row[0] for row in rows if row[0]}


def get_existing_hashes(db: Session, hashes: Iterable[str]) -> Set[str]:
    hashes = [h for h in hashes if h]
    if not hashes:
        return set()
    rows = db.execute(select(SettlementRecord.raw_row_hash).where(SettlementRecord.raw_row_hash.in_(hashes))).all()
    return {row[0] for row in rows if row[0]}
