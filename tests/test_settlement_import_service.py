from decimal import Decimal
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models.settlement import SettlementRecord
from services.simple_cache import app_cache
from services.settlement_import_service import (
    SettlementImportError,
    SettlementImportService,
)


def _create_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session_local()


def _build_csv(rows: list[str], header: Optional[str] = None) -> bytes:
    actual_header = header or (
        "交收日期,发生日期,发生时间,证券代码,证券名称,交易类别,成交数量,成交均价,成交金额,"
        "发生金额,佣金,其他费用,印花税,过户费,股份余额,资金余额,成交编号,股东账号,流水号,交易市场,币种,"
    )
    content = "\n".join([actual_header, *rows])
    return content.encode("gb18030")


def test_import_csv_inserts_records_and_deduplicates_within_file():
    service = SettlementImportService()
    db = _create_db()
    app_cache.clear()
    file_bytes = _build_csv(
        [
            '2025-08-06,2025-08-06,09:29:53,= "000597      ",东北制药,证券买入,200,6.090,1218.000,-1223.000,4.930,0.07,0.00,0.00,200,3777.00,0105000000894747,= "0909655210    ",= "0100083586    ",深市A股,人民币,',
            '2025-08-06,2025-08-06,09:29:53,= "000597      ",东北制药,证券买入,200,6.090,1218.000,-1223.000,4.930,0.07,0.00,0.00,200,3777.00,0105000000894747,= "0909655210    ",= "0100083586    ",深市A股,人民币,',
            '2025-08-08,2025-08-08,09:40:48,= "000597      ",东北制药,证券卖出,600,5.750,3450.000,3443.270,4.780,0.22,1.73,0.00,0,4807.27,0104000010283073,= "0909655210    ",= "0100281425    ",深市A股,人民币,',
        ]
    )

    try:
        result = service.import_csv(db, file_bytes, "jgd.csv")
    finally:
        db.close()

    assert result.total_count == 2
    assert result.inserted_count == 2
    assert result.skipped_count == 0


def test_import_csv_skips_existing_records():
    service = SettlementImportService()
    db = _create_db()
    app_cache.clear()
    file_bytes = _build_csv(
        [
            '2025-08-06,2025-08-06,09:29:53,= "000597      ",东北制药,证券买入,200,6.090,1218.000,-1223.000,4.930,0.07,0.00,0.00,200,3777.00,0105000000894747,= "0909655210    ",= "0100083586    ",深市A股,人民币,',
        ]
    )

    try:
        first = service.import_csv(db, file_bytes, "jgd.csv")
        second = service.import_csv(db, file_bytes, "jgd.csv")
    finally:
        db.close()

    assert first.inserted_count == 1
    assert second.inserted_count == 0
    assert second.skipped_count == 1


def test_normalize_row_cleans_excel_style_text():
    service = SettlementImportService()
    normalized = service.normalize_row(
        {
            "交收日期": "2025-08-06",
            "发生日期": "2025-08-06",
            "发生时间": "09:29:53",
            "证券代码": '= "000597      "',
            "证券名称": "东北制药",
            "交易类别": "证券买入",
            "成交数量": "200",
            "成交均价": "6.090",
            "成交金额": "1218.000",
            "发生金额": "-1223.000",
            "佣金": "4.930",
            "其他费用": "0.07",
            "印花税": "0.00",
            "过户费": "0.00",
            "股份余额": "200",
            "资金余额": "3777.00",
            "成交编号": "0105000000894747",
            "股东账号": '= "0909655210    "',
            "流水号": '= "0100083586    "',
            "交易市场": "深市A股",
            "币种": "人民币",
        },
        row_number=2,
    )

    assert normalized["security_code"] == "000597"
    assert normalized["shareholder_account"] == "0909655210"
    assert normalized["serial_no"] == "0100083586"


def test_import_csv_stores_money_as_milli_integer():
    service = SettlementImportService()
    db = _create_db()
    app_cache.clear()
    file_bytes = _build_csv(
        [
            '2025-08-06,2025-08-06,09:29:53,= "000597      ",东北制药,证券买入,200,6.090,1218.000,-1223.000,4.930,0.07,0.00,0.00,200,3777.00,0105000000894747,= "0909655210    ",= "0100083586    ",深市A股,人民币,',
        ]
    )

    try:
        service.import_csv(db, file_bytes, "jgd.csv")
        record = db.query(SettlementRecord).one()
    finally:
        db.close()

    assert record.turnover_milli == 1218000
    assert record.amount_milli == -1223000
    assert record.cash_balance_milli == 3777000
    assert record.turnover ==  Decimal("1218")
    assert record.amount == Decimal("-1223")


def test_parse_csv_rejects_invalid_header():
    service = SettlementImportService()
    file_bytes = _build_csv(
        ['2025-08-06,2025-08-06,09:29:53,--,--,银行转证券,0,0,0,5000,0,0,0,0,0,5000,0,--,--,--,人民币,'],
        header="错误表头\n",
    )

    try:
        service.parse_csv(file_bytes)
    except SettlementImportError as exc:
        assert "列结构" in str(exc)
    else:
        raise AssertionError("Expected SettlementImportError")


def test_import_csv_rejects_invalid_decimal_value():
    service = SettlementImportService()
    db = _create_db()
    app_cache.clear()
    file_bytes = _build_csv(
        [
            '2025-08-06,2025-08-06,09:29:53,--,--,银行转证券,0,NOT_A_NUMBER,0,5000,0,0,0,0,0,5000,0,--,--,--,人民币,',
        ]
    )

    try:
        service.import_csv(db, file_bytes, "jgd.csv")
    except SettlementImportError as exc:
        assert "第 2 行字段 成交均价 数值格式不正确" == str(exc)
    else:
        raise AssertionError("Expected SettlementImportError")
    finally:
        db.close()


def test_import_csv_clears_asset_detail_cache_when_new_records_inserted():
    service = SettlementImportService()
    db = _create_db()
    app_cache.clear()
    app_cache.set("asset_detail:2025-08-06", {"cached": True}, ttl_seconds=300)
    file_bytes = _build_csv(
        [
            '2025-08-06,2025-08-06,09:29:53,= "000597      ",东北制药,证券买入,200,6.090,1218.000,-1223.000,4.930,0.07,0.00,0.00,200,3777.00,0105000000894747,= "0909655210    ",= "0100083586    ",深市A股,人民币,',
        ]
    )

    try:
        service.import_csv(db, file_bytes, "jgd.csv")
    finally:
        db.close()

    assert app_cache.get("asset_detail:2025-08-06") is None


def test_import_csv_clears_asset_cash_flows_cache_when_new_records_inserted():
    service = SettlementImportService()
    db = _create_db()
    app_cache.clear()
    app_cache.set("asset_cash_flows:2025-08-06:10", {"cached": True}, ttl_seconds=300)
    file_bytes = _build_csv(
        [
            '2025-08-06,2025-08-06,09:29:53,= "000597      ",东北制药,证券买入,200,6.090,1218.000,-1223.000,4.930,0.07,0.00,0.00,200,3777.00,0105000000894747,= "0909655210    ",= "0100083586    ",深市A股,人民币,',
        ]
    )

    try:
        service.import_csv(db, file_bytes, "jgd.csv")
    finally:
        db.close()

    assert app_cache.get("asset_cash_flows:2025-08-06:10") is None
