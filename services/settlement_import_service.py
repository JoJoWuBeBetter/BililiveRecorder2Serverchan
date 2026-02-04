# services/settlement_import_service.py
import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from config import logger
from crud.settlement_crud import (
    create_import_batch,
    update_import_batch,
    create_settlement_records,
    get_existing_serials,
    get_existing_hashes,
)
from models.settlement import SettlementImportBatch, SettlementRecord


EXPECTED_HEADERS = [
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

MONEY_FIELDS = {
    "成交均价",
    "成交金额",
    "发生金额",
    "佣金",
    "其他费用",
    "印花税",
    "过户费",
    "资金余额",
}

INT_FIELDS = {
    "成交数量",
    "股份余额",
}

DATE_FIELDS = {
    "交收日期",
    "发生日期",
}


@dataclass
class ImportResult:
    batch: SettlementImportBatch


def _decode_csv_bytes(file_bytes: bytes) -> Tuple[str, str]:
    for encoding in ("gb18030", "utf-8-sig"):
        try:
            return file_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("gb18030", errors="replace"), "gb18030"


def _normalize_text(value: str) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if value == "" or value == "--":
        return None
    return value


def _parse_date(value: Optional[str]) -> Optional[datetime.date]:
    if not value:
        return None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    logger.warning(f"日期格式无法解析: {value}")
    return None


def _to_cents(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    value = value.strip()
    if value == "" or value == "--":
        return None
    try:
        dec = Decimal(value)
    except Exception:
        logger.warning(f"金额字段解析失败: {value}")
        return None
    cents = (dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _to_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    value = value.strip()
    if value == "" or value == "--":
        return None
    try:
        dec = Decimal(value)
    except Exception:
        logger.warning(f"整数字段解析失败: {value}")
        return None
    return int(dec)


def _build_row_hash(normalized_values: List[str]) -> str:
    joined = "|".join(normalized_values)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _normalize_row(header: List[str], row: List[str]) -> Dict[str, Optional[str]]:
    normalized = {}
    for idx, name in enumerate(header):
        raw = row[idx] if idx < len(row) else ""
        normalized[name] = _normalize_text(raw)
    return normalized


def _normalize_for_hash(header: List[str], parsed: Dict[str, Optional[object]]) -> List[str]:
    values: List[str] = []
    for name in header:
        value = parsed.get(name)
        if value is None:
            values.append("")
            continue
        if isinstance(value, int):
            values.append(str(value))
            continue
        if hasattr(value, "isoformat"):
            values.append(value.isoformat())
            continue
        values.append(str(value))
    return values


def import_settlement_csv(db: Session, file_bytes: bytes, filename: str) -> ImportResult:
    text, encoding = _decode_csv_bytes(file_bytes)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError("CSV 文件为空")

    raw_header = [cell.strip() for cell in rows[0]]
    header = ["".join(cell.split()) for cell in raw_header]
    if header != EXPECTED_HEADERS:
        raise ValueError("CSV 表头不符合东方财富模板")

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    batch = SettlementImportBatch(
        filename=filename,
        file_hash=file_hash,
        row_count=max(len(rows) - 1, 0),
        imported_count=0,
        skipped_count=0,
        error_count=0,
        encoding=encoding.upper(),
    )
    batch = create_import_batch(db, batch)

    parsed_rows = []
    for row in rows[1:]:
        try:
            normalized = _normalize_row(header, row)
            parsed: Dict[str, Optional[object]] = {}
            for name, value in normalized.items():
                if name in DATE_FIELDS:
                    parsed[name] = _parse_date(value)
                elif name in MONEY_FIELDS:
                    parsed[name] = _to_cents(value)
                elif name in INT_FIELDS:
                    parsed[name] = _to_int(value)
                else:
                    parsed[name] = value

            if all(value is None for value in parsed.values()):
                batch.error_count += 1
                continue

            normalized_for_hash = _normalize_for_hash(header, parsed)
            row_hash = _build_row_hash(normalized_for_hash)
            parsed_rows.append((parsed, row_hash))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"行解析失败: {exc}")
            batch.error_count += 1

    serials = [
        parsed.get("流水号")
        for parsed, _ in parsed_rows
        if parsed.get("流水号") and parsed.get("流水号") != "--"
    ]
    hashes = [row_hash for _, row_hash in parsed_rows]

    existing_serials = get_existing_serials(db, serials)
    existing_hashes = get_existing_hashes(db, hashes)

    seen_serials = set()
    seen_hashes = set()
    records: List[SettlementRecord] = []

    for parsed, row_hash in parsed_rows:
        serial_no = parsed.get("流水号")
        if serial_no == "--":
            serial_no = None

        if serial_no:
            if serial_no in existing_serials or serial_no in seen_serials:
                batch.skipped_count += 1
                continue
            seen_serials.add(serial_no)
        else:
            if row_hash in existing_hashes or row_hash in seen_hashes:
                batch.skipped_count += 1
                continue
            seen_hashes.add(row_hash)

        record = SettlementRecord(
            batch_id=batch.id,
            settlement_date=parsed.get("交收日期"),
            trade_date=parsed.get("发生日期"),
            trade_time=parsed.get("发生时间"),
            symbol=parsed.get("证券代码"),
            symbol_name=parsed.get("证券名称"),
            trade_type=parsed.get("交易类别"),
            volume=parsed.get("成交数量"),
            price_cent=parsed.get("成交均价"),
            amount_cent=parsed.get("成交金额"),
            occur_amount_cent=parsed.get("发生金额"),
            commission_cent=parsed.get("佣金"),
            other_fee_cent=parsed.get("其他费用"),
            stamp_tax_cent=parsed.get("印花税"),
            transfer_fee_cent=parsed.get("过户费"),
            share_balance=parsed.get("股份余额"),
            cash_balance_cent=parsed.get("资金余额"),
            deal_no=parsed.get("成交编号"),
            shareholder_account=parsed.get("股东账号"),
            serial_no=serial_no,
            market=parsed.get("交易市场"),
            currency=parsed.get("币种"),
            raw_row_hash=row_hash,
        )
        records.append(record)

    create_settlement_records(db, records)

    batch.imported_count = len(records)
    batch.error_count = 0
    update_import_batch(db, batch)

    logger.info(
        "交割单导入完成: file=%s, total=%s, imported=%s, skipped=%s",
        filename,
        batch.row_count,
        batch.imported_count,
        batch.skipped_count,
    )
    return ImportResult(batch=batch)
