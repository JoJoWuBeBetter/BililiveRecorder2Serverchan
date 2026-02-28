from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from crud.settlement_crud import list_settlements
from database import SessionLocal
from schemas.settlement import SettlementImportResponse, SettlementListResponse
from services.settlement_import_service import (
    SettlementImportError,
    settlement_import_service,
)

router = APIRouter(
    prefix="/settlements",
    tags=["Settlement Records"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/import", response_model=SettlementImportResponse)
async def import_settlement_csv(
    file: UploadFile = File(..., description="东方财富导出的交割单 CSV 文件"),
    db: Session = Depends(get_db),
):
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持导入 .csv 文件",
        )

    try:
        file_content = await file.read()
        return settlement_import_service.import_csv(
            db=db,
            file_bytes=file_content,
            filename=filename,
        )
    except SettlementImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("", response_model=SettlementListResponse)
async def get_settlement_list(
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    security_code: Optional[str] = Query(default=None),
    trade_type: Optional[str] = Query(default=None),
    occur_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
):
    total_count, items = list_settlements(
        db=db,
        limit=limit,
        offset=offset,
        security_code=security_code,
        trade_type=trade_type,
        occur_date=occur_date,
    )
    return SettlementListResponse(total_count=total_count, items=items)
