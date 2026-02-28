import asyncio
import io
from datetime import date

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers, UploadFile

from api.routers import settlement_api
from database import Base


def _create_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session_local()


def _build_csv(rows: list[str]) -> bytes:
    header = (
        "交收日期,发生日期,发生时间,证券代码,证券名称,交易类别,成交数量,成交均价,成交金额,"
        "发生金额,佣金,其他费用,印花税,过户费,股份余额,资金余额,成交编号,股东账号,流水号,交易市场,币种,"
    )
    content = "\n".join([header, *rows])
    return content.encode("gb18030")


def _build_upload_file(filename: str, content: bytes) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": "text/csv"}),
    )


def test_import_settlement_csv_returns_counts():
    db = _create_db()

    try:
        result = asyncio.run(
            settlement_api.import_settlement_csv(
                file=_build_upload_file(
                    "jgd.csv",
                    _build_csv(
                        [
                            '2025-08-06,2025-08-06,09:29:53,= "000597      ",东北制药,证券买入,200,6.090,1218.000,-1223.000,4.930,0.07,0.00,0.00,200,3777.00,0105000000894747,= "0909655210    ",= "0100083586    ",深市A股,人民币,',
                        ]
                    ),
                ),
                db=db,
            )
        )
    finally:
        db.close()

    assert result.inserted_count == 1
    assert result.skipped_count == 0


def test_import_settlement_csv_rejects_non_csv_filename():
    db = _create_db()

    try:
        asyncio.run(
            settlement_api.import_settlement_csv(
                file=_build_upload_file("jgd.txt", b"abc"),
                db=db,
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("Expected HTTPException")
    finally:
        db.close()


def test_import_settlement_csv_reimport_skips_duplicates():
    db = _create_db()
    payload = _build_csv(
        [
            '2025-08-06,2025-08-06,09:29:53,= "000597      ",东北制药,证券买入,200,6.090,1218.000,-1223.000,4.930,0.07,0.00,0.00,200,3777.00,0105000000894747,= "0909655210    ",= "0100083586    ",深市A股,人民币,',
        ]
    )

    try:
        first = asyncio.run(
            settlement_api.import_settlement_csv(
                file=_build_upload_file("jgd.csv", payload),
                db=db,
            )
        )
        second = asyncio.run(
            settlement_api.import_settlement_csv(
                file=_build_upload_file("jgd.csv", payload),
                db=db,
            )
        )
    finally:
        db.close()

    assert first.inserted_count == 1
    assert second.inserted_count == 0
    assert second.skipped_count == 1


def test_get_settlement_list_supports_filters():
    db = _create_db()
    payload = _build_csv(
        [
            '2025-08-06,2025-08-06,09:29:53,= "000597      ",东北制药,证券买入,200,6.090,1218.000,-1223.000,4.930,0.07,0.00,0.00,200,3777.00,0105000000894747,= "0909655210    ",= "0100083586    ",深市A股,人民币,',
            '2025-08-08,2025-08-08,09:40:48,= "000001      ",平安银行,证券卖出,600,5.750,3450.000,3443.270,4.780,0.22,1.73,0.00,0,4807.27,0104000010283073,= "0909655210    ",= "0100281425    ",深市A股,人民币,',
        ]
    )

    try:
        asyncio.run(
            settlement_api.import_settlement_csv(
                file=_build_upload_file("jgd.csv", payload),
                db=db,
            )
        )
        result = asyncio.run(
            settlement_api.get_settlement_list(
                limit=100,
                offset=0,
                security_code="000597",
                trade_type="证券买入",
                occur_date=date(2025, 8, 6),
                db=db,
            )
        )
    finally:
        db.close()

    assert result.total_count == 1
    assert len(result.items) == 1
    assert result.items[0].security_code == "000597"
