from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy.orm import Session

from crud.settlement_crud import bulk_create_settlements, get_existing_hashes
from models.settlement import SettlementRecord
from schemas.settlement import SettlementImportResponse


class SettlementImportError(ValueError):
    """交割单导入失败。"""


class SettlementImportService:
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

    DECIMAL_FIELDS = {
        "成交均价",
        "成交金额",
        "发生金额",
        "佣金",
        "其他费用",
        "印花税",
        "过户费",
        "资金余额",
    }
    INTEGER_FIELDS = {"成交数量", "股份余额"}

    def parse_csv(self, file_bytes: bytes) -> list[dict[str, str]]:
        if not file_bytes:
            raise SettlementImportError("CSV 文件为空")

        text = self._decode_csv(file_bytes)
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            raise SettlementImportError("CSV 文件为空")

        headers = [cell.strip() for cell in rows[0]]
        effective_headers = [header for header in headers if header]
        if effective_headers != self.EXPECTED_HEADERS:
            raise SettlementImportError("CSV 列结构不符合东方财富交割单格式")

        parsed_rows: list[dict[str, str]] = []
        header_count = len(self.EXPECTED_HEADERS)

        for row in rows[1:]:
            if not any(cell.strip() for cell in row):
                continue

            padded_row = (row[:header_count] + [""] * header_count)[:header_count]
            parsed_rows.append(
                {
                    self.EXPECTED_HEADERS[index]: padded_row[index].strip()
                    for index in range(header_count)
                }
            )

        if not parsed_rows:
            raise SettlementImportError("CSV 文件中没有可导入的数据")

        return parsed_rows

    def import_csv(
        self,
        db: Session,
        file_bytes: bytes,
        filename: str,
    ) -> SettlementImportResponse:
        raw_rows = self.parse_csv(file_bytes)

        deduplicated_rows: dict[str, dict[str, Any]] = {}
        for index, raw_row in enumerate(raw_rows, start=2):
            normalized = self.normalize_row(raw_row, row_number=index)
            source_hash = self.build_source_hash(normalized)
            if source_hash not in deduplicated_rows:
                deduplicated_rows[source_hash] = normalized

        file_hashes = list(deduplicated_rows.keys())
        existing_hashes = get_existing_hashes(db, file_hashes)

        records_to_insert = [
            self._build_model(deduplicated_rows[source_hash])
            for source_hash in file_hashes
            if source_hash not in existing_hashes
        ]
        inserted_count = bulk_create_settlements(db, records_to_insert)
        total_count = len(file_hashes)

        return SettlementImportResponse(
            filename=filename,
            total_count=total_count,
            inserted_count=inserted_count,
            skipped_count=total_count - inserted_count,
        )

    def normalize_row(self, raw_row: dict[str, str], row_number: int) -> dict[str, Any]:
        normalized = {
            "settlement_date": self._parse_date(raw_row["交收日期"], row_number, "交收日期"),
            "occur_date": self._parse_date(raw_row["发生日期"], row_number, "发生日期"),
            "occur_time": self._parse_time(raw_row["发生时间"], row_number, "发生时间"),
            "security_code": self._normalize_text(raw_row["证券代码"]),
            "security_name": self._normalize_text(raw_row["证券名称"]),
            "trade_type": self._require_text(raw_row["交易类别"], row_number, "交易类别"),
            "volume": self._parse_integer(raw_row["成交数量"], row_number, "成交数量"),
            "price": self._parse_decimal(raw_row["成交均价"], row_number, "成交均价"),
            "turnover": self._parse_decimal(raw_row["成交金额"], row_number, "成交金额"),
            "amount": self._parse_decimal(raw_row["发生金额"], row_number, "发生金额"),
            "commission": self._parse_decimal(raw_row["佣金"], row_number, "佣金"),
            "other_fee": self._parse_decimal(raw_row["其他费用"], row_number, "其他费用"),
            "stamp_duty": self._parse_decimal(raw_row["印花税"], row_number, "印花税"),
            "transfer_fee": self._parse_decimal(raw_row["过户费"], row_number, "过户费"),
            "share_balance": self._parse_integer(raw_row["股份余额"], row_number, "股份余额"),
            "cash_balance": self._parse_decimal(raw_row["资金余额"], row_number, "资金余额"),
            "trade_no": self._normalize_text(raw_row["成交编号"]),
            "shareholder_account": self._normalize_text(raw_row["股东账号"]),
            "serial_no": self._normalize_text(raw_row["流水号"]),
            "market": self._normalize_text(raw_row["交易市场"]),
            "currency": self._normalize_text(raw_row["币种"]),
        }
        normalized["source_hash"] = self.build_source_hash(normalized)
        normalized["raw_row"] = {key: raw_row.get(key, "") for key in self.EXPECTED_HEADERS}
        return normalized

    def build_source_hash(self, normalized_row: dict[str, Any]) -> str:
        payload = {
            "settlement_date": normalized_row["settlement_date"].isoformat(),
            "occur_date": normalized_row["occur_date"].isoformat(),
            "occur_time": normalized_row["occur_time"].isoformat(),
            "security_code": normalized_row["security_code"],
            "security_name": normalized_row["security_name"],
            "trade_type": normalized_row["trade_type"],
            "volume": normalized_row["volume"],
            "price": self._decimal_to_string(normalized_row["price"]),
            "turnover": self._decimal_to_string(normalized_row["turnover"]),
            "amount": self._decimal_to_string(normalized_row["amount"]),
            "commission": self._decimal_to_string(normalized_row["commission"]),
            "other_fee": self._decimal_to_string(normalized_row["other_fee"]),
            "stamp_duty": self._decimal_to_string(normalized_row["stamp_duty"]),
            "transfer_fee": self._decimal_to_string(normalized_row["transfer_fee"]),
            "share_balance": normalized_row["share_balance"],
            "cash_balance": self._decimal_to_string(normalized_row["cash_balance"]),
            "trade_no": normalized_row["trade_no"],
            "shareholder_account": normalized_row["shareholder_account"],
            "serial_no": normalized_row["serial_no"],
            "market": normalized_row["market"],
            "currency": normalized_row["currency"],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _build_model(self, normalized_row: dict[str, Any]) -> SettlementRecord:
        return SettlementRecord(**normalized_row)

    @staticmethod
    def _decode_csv(file_bytes: bytes) -> str:
        for encoding in ("gb18030", "gbk"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise SettlementImportError("仅支持东方财富导出的 GBK/GB18030 CSV")

    @staticmethod
    def _normalize_text(value: str) -> Optional[str]:
        text = value.strip()
        if not text or text == "--":
            return None

        match = re.fullmatch(r'=\s*"(.+)"', text)
        if match:
            text = match.group(1).strip()

        return text or None

    def _require_text(self, value: str, row_number: int, field_name: str) -> str:
        text = self._normalize_text(value)
        if text is None:
            raise SettlementImportError(f"第 {row_number} 行字段 {field_name} 不能为空")
        return text

    @staticmethod
    def _parse_date(value: str, row_number: int, field_name: str):
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise SettlementImportError(f"第 {row_number} 行字段 {field_name} 日期格式不正确") from exc

    @staticmethod
    def _parse_time(value: str, row_number: int, field_name: str):
        try:
            return datetime.strptime(value.strip(), "%H:%M:%S").time()
        except ValueError as exc:
            raise SettlementImportError(f"第 {row_number} 行字段 {field_name} 时间格式不正确") from exc

    def _parse_integer(self, value: str, row_number: int, field_name: str) -> int:
        parsed = self._parse_decimal(value, row_number, field_name)
        return int(parsed)

    @staticmethod
    def _parse_decimal(value: str, row_number: int, field_name: str) -> Decimal:
        text = value.strip()
        if not text:
            text = "0"
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise SettlementImportError(f"第 {row_number} 行字段 {field_name} 数值格式不正确") from exc

    @staticmethod
    def _decimal_to_string(value: Decimal) -> str:
        normalized = value.normalize()
        text = format(normalized, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"


settlement_import_service = SettlementImportService()
