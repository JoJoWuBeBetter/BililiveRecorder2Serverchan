# api/routers/settlement_api.py
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from config import logger
from crud.settlement_crud import list_import_batches, get_import_batch, list_settlement_records
from database import SessionLocal
from schemas.settlement import SettlementImportBatch, SettlementImportResult, SettlementRecord, AccountSummary
from services.settlement_import_service import import_settlement_csv
from datetime import date, datetime

from services.settlement_summary_service import build_account_summary

router = APIRouter(
    prefix="/settlements",
    tags=["Settlement Import"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/import", response_model=SettlementImportResult, status_code=status.HTTP_201_CREATED)
async def import_settlement_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少文件名")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 CSV 文件")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件为空")

    try:
        result = import_settlement_csv(db, file_bytes, file.filename)
    except ValueError as exc:
        logger.warning(f"交割单导入失败: {exc}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("交割单导入异常")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="交割单导入失败") from exc

    return SettlementImportResult(batch=result.batch)


@router.get("/batches", response_model=List[SettlementImportBatch])
async def get_import_batches(limit: int = 50, db: Session = Depends(get_db)):
    return list_import_batches(db, limit=limit)


@router.get("/batches/{batch_id}", response_model=SettlementImportBatch)
async def get_import_batch_detail(batch_id: uuid.UUID, db: Session = Depends(get_db)):
    batch = get_import_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到导入批次")
    return batch


@router.get("/records", response_model=List[SettlementRecord])
async def get_settlement_records(
    batch_id: Optional[uuid.UUID] = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return list_settlement_records(db, batch_id=batch_id, limit=limit, offset=offset)


@router.get("/account-summary", response_model=AccountSummary)
async def get_account_summary(
    trade_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if trade_date:
        try:
            price_date = datetime.strptime(trade_date, "%Y%m%d").date()
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="trade_date 格式应为 YYYYMMDD") from exc
    else:
        price_date = date.today()
    return build_account_summary(db, price_date=price_date)
