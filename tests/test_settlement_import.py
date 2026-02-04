# tests/test_settlement_import.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import settlement  # noqa: F401 - 确保模型注册
from models.settlement import SettlementRecord
from services.settlement_import_service import import_settlement_csv


def _make_csv(rows):
    header = [
        "交收日期",
        "发生日期",
        "发生时间",
        "证券代码",
        "证券名称",
        "交易类别",
        "成交数量",
        "成交均价",
        "成交金额",
        "发生金额",
        "佣金",
        "其他费用",
        "印花税",
        "过户费",
        "股份余额",
        "资金余额",
        "成交编号",
        "股东账号",
        "流水号",
        "交易市场",
        "币种",
    ]
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(row))
    return ("\n".join(lines)).encode("gb18030")


def test_import_settlement_csv_deduplicate():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    rows = [
        ["2025/8/6", "2025/8/6", "9:29:53", "000597", "东北制药", "证券买入", "200", "6.09", "1218", "-1223",
         "4.93", "0.07", "0", "0", "200", "3777", "105", "0909655210", "S1", "深市A股", "人民币"],
        ["2025/8/6", "2025/8/6", "9:29:53", "000597", "东北制药", "证券买入", "200", "6.09", "1218", "-1223",
         "4.93", "0.07", "0", "0", "200", "3777", "105", "0909655210", "S1", "深市A股", "人民币"],
        ["2025/8/6", "2025/8/6", "7:07:26", "--", "--", "银行转证券", "0", "0", "0", "5000",
         "0", "0", "0", "0", "0", "5000", "0", "--", "--", "人民币", "人民币"],
        ["2025/8/6", "2025/8/6", "7:07:26", "--", "--", "银行转证券", "0", "0", "0", "5000",
         "0", "0", "0", "0", "0", "5000", "0", "--", "--", "人民币", "人民币"],
    ]

    csv_bytes = _make_csv(rows)
    db = TestingSessionLocal()
    try:
        result = import_settlement_csv(db, csv_bytes, "Table_349.csv")
        assert result.batch.imported_count == 2
        assert result.batch.skipped_count == 2
        assert result.batch.error_count == 0

        records = db.query(SettlementRecord).all()
        assert len(records) == 2

        buy_record = next(r for r in records if r.serial_no == "S1")
        assert buy_record.price_cent == 609
        assert buy_record.amount_cent == 121800
        assert buy_record.occur_amount_cent == -122300
    finally:
        db.close()
