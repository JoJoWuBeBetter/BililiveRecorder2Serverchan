# tests/test_settlement_summary.py
import uuid
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import settlement  # noqa: F401
from models.settlement import SettlementRecord
from services.settlement_summary_service import build_account_summary


def test_account_summary_basic():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        record_buy = SettlementRecord(
            id=uuid.uuid4(),
            batch_id=uuid.uuid4(),
            trade_date=date(2025, 8, 6),
            trade_time="09:30:00",
            symbol="000597",
            symbol_name="东北制药",
            trade_type="证券买入",
            share_balance=200,
            price_cent=609,
            cash_balance_cent=377700,
            occur_amount_cent=-122300,
            raw_row_hash="h1",
        )
        record_cash = SettlementRecord(
            id=uuid.uuid4(),
            batch_id=uuid.uuid4(),
            trade_date=date(2025, 8, 6),
            trade_time="10:00:00",
            trade_type="银行转证券",
            cash_balance_cent=500000,
            occur_amount_cent=500000,
            raw_row_hash="h2",
        )
        db.add_all([record_buy, record_cash])
        db.commit()

        summary = build_account_summary(db)

        assert summary.cash_balance_yuan == "5000.00"
        assert summary.total_asset_yuan == "6218.00"
        assert summary.position_ratio is not None
        assert len(summary.positions) == 1
        assert summary.positions[0].symbol == "000597"
        assert summary.positions[0].shares == 200
        assert summary.positions[0].last_price_yuan == "6.09"
        assert summary.positions[0].market_value_yuan == "1218.00"
    finally:
        db.close()
