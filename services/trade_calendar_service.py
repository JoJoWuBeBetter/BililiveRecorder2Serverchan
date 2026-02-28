from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from config import get_tushare_token
from crud.trade_calendar_crud import (
    get_next_open_trade_day,
    get_prev_open_trade_day,
    get_trade_calendar_day,
    get_trade_calendar_days_in_range,
    upsert_trade_calendar_days,
)
from database import SessionLocal, create_db_and_tables
from models.trade_calendar import TradeCalendarDayRecord
from services.simple_cache import SimpleTTLCache, app_cache
from services.tushare_guard import guarded_tushare_call

logger = logging.getLogger(__name__)


class TradeCalendarConfigError(RuntimeError):
    """Tushare 交易日历配置缺失。"""


class TradeCalendarPermissionError(PermissionError):
    """Tushare 交易日历权限不足。"""


class TradeCalendarFetchError(RuntimeError):
    """Tushare 交易日历拉取失败。"""


@dataclass
class TradeCalendarDay:
    exchange: str
    cal_date: date
    is_open: bool
    pretrade_date: Optional[date]


class TradeCalendarService:
    def __init__(self, cache: Optional[SimpleTTLCache] = None):
        self.cache = cache or app_cache

    def prewarm_recent_trade_days(
        self,
        days: int = 365,
        exchange: str = "SSE",
        db=None,
        silent: bool = False,
    ) -> int:
        end_date = self._now_shanghai().date()
        start_date = self._shift_days(end_date, -max(days, 1))
        logger.info(
            "开始预热交易日历: exchange=%s, start=%s, end=%s",
            exchange,
            start_date,
            end_date,
        )
        try:
            trade_days = self.get_trade_days(
                start_date=start_date,
                end_date=end_date,
                exchange=exchange,
                db=db,
            )
        except (TradeCalendarConfigError, TradeCalendarPermissionError, TradeCalendarFetchError):
            if silent:
                logger.warning("交易日历预热失败，已按 silent 模式忽略")
                return 0
            raise
        logger.info("交易日历预热完成: exchange=%s, trade_days=%s", exchange, len(trade_days))
        return len(trade_days)

    def get_calendar_day(
        self,
        trade_date: date,
        exchange: str = "SSE",
        db=None,
    ) -> TradeCalendarDay:
        cache_key = self.cache.build_key("trade_calendar", (exchange, trade_date.isoformat()))
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.info("交易日历命中内存缓存: exchange=%s, date=%s", exchange, trade_date)
            return cached  # type: ignore[return-value]

        logger.info("交易日历查询: exchange=%s, date=%s", exchange, trade_date)
        calendar_day = self._with_db(
            db,
            lambda session: self._get_calendar_day_with_db(
                db=session,
                trade_date=trade_date,
                exchange=exchange,
            ),
        )
        self.cache.set(cache_key, calendar_day, ttl_seconds=43200)
        return calendar_day

    def get_effective_trade_date(
        self,
        target_date: date,
        now: Optional[datetime] = None,
        exchange: str = "SSE",
        db=None,
    ) -> date:
        current_time = now or self._now_shanghai()
        calendar_day = self.get_calendar_day(target_date, exchange=exchange, db=db)

        if not calendar_day.is_open:
            if calendar_day.pretrade_date is None:
                raise TradeCalendarFetchError(f"{target_date} 休市且缺少上一交易日数据")
            logger.info(
                "交易日归并为上一交易日: requested=%s, effective=%s, reason=market_closed",
                target_date,
                calendar_day.pretrade_date,
            )
            return calendar_day.pretrade_date

        if target_date < current_time.date():
            return target_date

        if target_date > current_time.date():
            return self.get_effective_trade_date(current_time.date(), now=current_time, exchange=exchange, db=db)

        if current_time.time() < time(15, 0, 0):
            if calendar_day.pretrade_date is None:
                raise TradeCalendarFetchError(f"{target_date} 未收盘且缺少上一交易日数据")
            logger.info(
                "交易日归并为上一交易日: requested=%s, effective=%s, reason=pre_close",
                target_date,
                calendar_day.pretrade_date,
            )
            return calendar_day.pretrade_date

        return target_date

    def normalize_to_trade_date(
        self,
        target_date: date,
        exchange: str = "SSE",
        db=None,
    ) -> date:
        calendar_day = self.get_calendar_day(target_date, exchange=exchange, db=db)
        if calendar_day.is_open:
            return target_date
        if calendar_day.pretrade_date is None:
            raise TradeCalendarFetchError(f"{target_date} 休市且缺少上一交易日数据")
        logger.info(
            "标准化到交易日: requested=%s, effective=%s",
            target_date,
            calendar_day.pretrade_date,
        )
        return calendar_day.pretrade_date

    def get_adjacent_trade_day(
        self,
        base_date: date,
        direction: str,
        exchange: str = "SSE",
        db=None,
    ) -> date:
        normalized_date = self.normalize_to_trade_date(base_date, exchange=exchange, db=db)
        max_trade_date = self.normalize_to_trade_date(self._now_shanghai().date(), exchange=exchange, db=db)
        if direction not in {"prev", "next"}:
            raise TradeCalendarFetchError(f"不支持的交易日方向: {direction}")

        def _load(session):
            self._ensure_trade_calendar_range(
                db=session,
                start_date=self._shift_days(normalized_date, -40),
                end_date=self._shift_days(normalized_date, 40),
                exchange=exchange,
            )
            if direction == "prev":
                record = get_prev_open_trade_day(session, exchange=exchange, base_date=normalized_date)
            else:
                record = get_next_open_trade_day(session, exchange=exchange, base_date=normalized_date)
            if record is None:
                return normalized_date
            if direction == "next" and record.cal_date > max_trade_date:
                return normalized_date
            return record.cal_date

        adjacent_day = self._with_db(db, _load)
        logger.info(
            "相邻交易日查询: base=%s, normalized=%s, direction=%s, result=%s",
            base_date,
            normalized_date,
            direction,
            adjacent_day,
        )
        return adjacent_day

    def get_trade_days(
        self,
        start_date: date,
        end_date: date,
        exchange: str = "SSE",
        db=None,
    ) -> list[date]:
        if start_date > end_date:
            return []

        cache_key = self.cache.build_key(
            "trade_calendar_range",
            (exchange, start_date.isoformat(), end_date.isoformat()),
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.info(
                "交易日区间命中内存缓存: exchange=%s, start=%s, end=%s, count=%s",
                exchange,
                start_date,
                end_date,
                len(cached),
            )
            return cached  # type: ignore[return-value]

        logger.info("交易日区间查询: exchange=%s, start=%s, end=%s", exchange, start_date, end_date)
        trade_days = self._with_db(
            db,
            lambda session: self._get_trade_days_with_db(
                db=session,
                start_date=start_date,
                end_date=end_date,
                exchange=exchange,
            ),
        )
        trade_days.sort()
        self.cache.set(cache_key, trade_days, ttl_seconds=43200)
        logger.info(
            "交易日区间查询完成: exchange=%s, start=%s, end=%s, count=%s",
            exchange,
            start_date,
            end_date,
            len(trade_days),
        )
        return trade_days

    def get_previous_trade_day_map(
        self,
        start_date: date,
        end_date: date,
        exchange: str = "SSE",
        db=None,
    ) -> Dict[date, Optional[date]]:
        return self._with_db(
            db,
            lambda session: self._get_previous_trade_day_map_with_db(
                db=session,
                start_date=start_date,
                end_date=end_date,
                exchange=exchange,
            ),
        )

    def _get_tushare_module(self) -> Any:
        try:
            import tushare as ts
        except ImportError as exc:
            raise TradeCalendarFetchError("tushare 依赖未安装") from exc
        return ts

    @staticmethod
    def _is_permission_error(exc: Exception) -> bool:
        text = str(exc).lower()
        keywords = ("permission", "权限", "积分", "privilege", "points")
        return any(keyword in text for keyword in keywords)

    def _extract_records(self, result: Any) -> list[Dict[str, Any]]:
        if result is None:
            return []

        if hasattr(result, "empty") and result.empty:
            return []

        if hasattr(result, "to_dict"):
            records = result.to_dict("records")
        elif isinstance(result, list):
            records = result
        else:
            raise TradeCalendarFetchError("Tushare 交易日历返回数据格式不支持")

        if not isinstance(records, list):
            raise TradeCalendarFetchError("Tushare 交易日历返回记录格式不正确")

        return records

    def _fetch_trade_cal_rows(
        self,
        start_date: date,
        end_date: date,
        exchange: str,
    ) -> list[Dict[str, Any]]:
        token = get_tushare_token()
        if not token:
            raise TradeCalendarConfigError("TUSHARE_TOKEN 未配置")

        tushare = self._get_tushare_module()
        try:
            logger.info(
                "开始请求 Tushare 交易日历: exchange=%s, start=%s, end=%s",
                exchange,
                start_date,
                end_date,
            )
            with guarded_tushare_call():
                pro = tushare.pro_api(token)
                result = pro.trade_cal(
                    exchange=exchange,
                    start_date=start_date.strftime("%Y%m%d"),
                    end_date=end_date.strftime("%Y%m%d"),
                )
        except Exception as exc:  # noqa: BLE001 - normalize third-party failures
            if self._is_permission_error(exc):
                raise TradeCalendarPermissionError(str(exc)) from exc
            raise TradeCalendarFetchError(f"Tushare 交易日历请求失败: {exc}") from exc

        records = self._extract_records(result)
        if not records:
            raise TradeCalendarFetchError(f"{exchange} 在 {start_date} 到 {end_date} 没有交易日历数据")
        logger.info(
            "Tushare 交易日历返回成功: exchange=%s, start=%s, end=%s, rows=%s",
            exchange,
            start_date,
            end_date,
            len(records),
        )
        return records

    def _get_calendar_day_with_db(self, db, trade_date: date, exchange: str) -> TradeCalendarDay:
        self._ensure_trade_calendar_range(db=db, start_date=trade_date, end_date=trade_date, exchange=exchange)
        record = get_trade_calendar_day(db=db, exchange=exchange, cal_date=trade_date)
        if record is None:
            raise TradeCalendarFetchError(f"{exchange} 在 {trade_date} 没有交易日历数据")
        logger.info("交易日历命中数据库: exchange=%s, date=%s", exchange, trade_date)
        return self._to_calendar_day(record)

    def _get_trade_days_with_db(
        self,
        db,
        start_date: date,
        end_date: date,
        exchange: str,
    ) -> list[date]:
        self._ensure_trade_calendar_range(db=db, start_date=start_date, end_date=end_date, exchange=exchange)
        rows = get_trade_calendar_days_in_range(db=db, exchange=exchange, start_date=start_date, end_date=end_date)
        return [row.cal_date for row in rows if row.is_open]

    def _get_previous_trade_day_map_with_db(
        self,
        db,
        start_date: date,
        end_date: date,
        exchange: str,
    ) -> Dict[date, Optional[date]]:
        self._ensure_trade_calendar_range(db=db, start_date=start_date, end_date=end_date, exchange=exchange)
        rows = get_trade_calendar_days_in_range(db=db, exchange=exchange, start_date=start_date, end_date=end_date)
        return {row.cal_date: row.pretrade_date for row in rows}

    def _ensure_trade_calendar_range(self, db, start_date: date, end_date: date, exchange: str) -> None:
        existing_rows = get_trade_calendar_days_in_range(
            db=db,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
        )
        expected_days = (end_date - start_date).days + 1
        if len(existing_rows) == expected_days:
            logger.info(
                "交易日历区间命中数据库: exchange=%s, start=%s, end=%s, rows=%s",
                exchange,
                start_date,
                end_date,
                len(existing_rows),
            )
            return

        logger.info(
            "交易日历区间缺失，开始回源补齐: exchange=%s, start=%s, end=%s, existing=%s, expected=%s",
            exchange,
            start_date,
            end_date,
            len(existing_rows),
            expected_days,
        )
        rows = self._fetch_trade_cal_rows(start_date=start_date, end_date=end_date, exchange=exchange)
        payloads = []
        for row in rows:
            parsed = self._parse_calendar_row(row)
            payloads.append(
                {
                    "exchange": parsed.exchange,
                    "cal_date": parsed.cal_date,
                    "is_open": parsed.is_open,
                    "pretrade_date": parsed.pretrade_date,
                    "source": "tushare",
                }
            )
        upsert_trade_calendar_days(db=db, rows=payloads)
        logger.info(
            "交易日历区间补齐完成: exchange=%s, start=%s, end=%s, upsert_rows=%s",
            exchange,
            start_date,
            end_date,
            len(payloads),
        )

    @staticmethod
    def _to_calendar_day(row: TradeCalendarDayRecord) -> TradeCalendarDay:
        return TradeCalendarDay(
            exchange=row.exchange,
            cal_date=row.cal_date,
            is_open=bool(row.is_open),
            pretrade_date=row.pretrade_date,
        )

    @staticmethod
    def _shift_days(base_date: date, offset: int) -> date:
        return base_date.fromordinal(base_date.toordinal() + offset)

    @staticmethod
    def _with_db(db, callback):
        if db is not None:
            return callback(db)

        create_db_and_tables()
        session = SessionLocal()
        try:
            return callback(session)
        finally:
            session.close()

    def _parse_calendar_row(self, row: Dict[str, Any]) -> TradeCalendarDay:
        try:
            pretrade_raw = row.get("pretrade_date")
            pretrade_date = None
            if pretrade_raw:
                pretrade_date = self._parse_date(str(pretrade_raw))

            return TradeCalendarDay(
                exchange=str(row["exchange"]),
                cal_date=self._parse_date(str(row["cal_date"])),
                is_open=str(row["is_open"]) == "1",
                pretrade_date=pretrade_date,
            )
        except KeyError as exc:
            raise TradeCalendarFetchError(f"Tushare 交易日历缺少字段: {exc}") from exc
        except ValueError as exc:
            raise TradeCalendarFetchError(f"Tushare 交易日历字段格式错误: {exc}") from exc

    @staticmethod
    def _parse_date(value: str) -> date:
        return datetime.strptime(value, "%Y%m%d").date()

    @staticmethod
    def _now_shanghai() -> datetime:
        return datetime.now(ZoneInfo("Asia/Shanghai"))


trade_calendar_service = TradeCalendarService()
