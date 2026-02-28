from datetime import date

from sqlalchemy.orm import Session

from models.settlement import SettlementRecord


def has_settlement_records(db: Session) -> bool:
    return db.query(SettlementRecord.id).first() is not None


def list_records_on_or_before(db: Session, target_date: date) -> list[SettlementRecord]:
    return (
        db.query(SettlementRecord)
        .filter(SettlementRecord.occur_date <= target_date)
        .order_by(
            SettlementRecord.occur_date.asc(),
            SettlementRecord.occur_time.asc(),
            SettlementRecord.id.asc(),
        )
        .all()
    )


def get_trade_records_for_codes_on_or_before(
    db: Session,
    target_date: date,
    security_codes: list[str],
) -> list[SettlementRecord]:
    if not security_codes:
        return []

    return (
        db.query(SettlementRecord)
        .filter(SettlementRecord.occur_date <= target_date)
        .filter(SettlementRecord.security_code.in_(security_codes))
        .filter(SettlementRecord.trade_type.in_(("证券买入", "证券卖出")))
        .order_by(
            SettlementRecord.occur_date.asc(),
            SettlementRecord.occur_time.asc(),
            SettlementRecord.id.asc(),
        )
        .all()
    )
