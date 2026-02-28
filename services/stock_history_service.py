from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from config import get_tushare_token
from schemas.stock import AdjustmentType, StockDailyBar, StockHistoryQuery, StockHistoryResponse


class StockHistoryConfigError(RuntimeError):
    """Tushare 配置缺失。"""


class StockHistoryPermissionError(PermissionError):
    """Tushare 权限不足。"""


class StockHistoryFetchError(RuntimeError):
    """Tushare 拉取失败。"""


class StockHistoryService:
    """封装 Tushare A 股历史行情查询。"""

    _ADJUST_MAP = {
        AdjustmentType.NONE: None,
        AdjustmentType.QFQ: "qfq",
        AdjustmentType.HFQ: "hfq",
    }

    def get_stock_history(
        self,
        ts_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        trade_date: Optional[date] = None,
        adjust: AdjustmentType = AdjustmentType.NONE,
    ) -> StockHistoryResponse:
        normalized_ts_code = self._normalize_ts_code(ts_code)
        token = get_tushare_token()
        if not token:
            raise StockHistoryConfigError("TUSHARE_TOKEN 未配置")

        tushare = self._get_tushare_module()
        formatted_start = self._format_tushare_date(trade_date or start_date)
        formatted_end = self._format_tushare_date(trade_date or end_date)
        tushare.set_token(token)

        items: List[StockDailyBar] = []
        for asset in self._get_asset_candidates(normalized_ts_code):
            try:
                result = tushare.pro_bar(
                    ts_code=normalized_ts_code,
                    start_date=formatted_start,
                    end_date=formatted_end,
                    adj=self._ADJUST_MAP[adjust],
                    asset=asset,
                    freq="D",
                )
            except Exception as exc:  # noqa: BLE001 - need to normalize third-party failures
                if self._is_permission_error(exc):
                    raise StockHistoryPermissionError(str(exc)) from exc
                raise StockHistoryFetchError(f"Tushare 请求失败: {exc}") from exc

            records = self._extract_records(result)
            items = self._normalize_items(records)
            if items:
                break

        return StockHistoryResponse(
            ts_code=normalized_ts_code,
            adjust=adjust,
            query=StockHistoryQuery(
                start_date=start_date,
                end_date=end_date,
                trade_date=trade_date,
            ),
            count=len(items),
            items=items,
        )

    def _get_tushare_module(self) -> Any:
        try:
            import tushare as ts
        except ImportError as exc:
            raise StockHistoryFetchError("tushare 依赖未安装") from exc
        return ts

    @staticmethod
    def _format_tushare_date(value: Optional[date]) -> Optional[str]:
        if value is None:
            return None
        return value.strftime("%Y%m%d")

    @staticmethod
    def _normalize_ts_code(ts_code: str) -> str:
        code = ts_code.strip().upper()
        if not code:
            raise StockHistoryFetchError("ts_code 不能为空")

        if "." in code:
            return code

        if not (len(code) == 6 and code.isdigit()):
            return code

        first_digit = code[0]
        if first_digit in {"5", "6", "9"}:
            return f"{code}.SH"
        if first_digit in {"0", "1", "2", "3"}:
            return f"{code}.SZ"
        if first_digit in {"4", "8"}:
            return f"{code}.BJ"
        return code

    @staticmethod
    def _get_asset_candidates(ts_code: str) -> List[str]:
        code = ts_code.strip().upper()
        if "." not in code:
            return ["E"]

        symbol, market = code.split(".", 1)
        if (
            len(symbol) == 6
            and symbol.isdigit()
            and (
                (market == "SH" and symbol.startswith("5"))
                or (market == "SZ" and symbol.startswith("1"))
            )
        ):
            return ["FD", "E"]

        return ["E"]

    @staticmethod
    def _is_permission_error(exc: Exception) -> bool:
        text = str(exc).lower()
        keywords = ("permission", "权限", "积分", "privilege", "points")
        return any(keyword in text for keyword in keywords)

    def _extract_records(self, result: Any) -> List[Dict[str, Any]]:
        if result is None:
            return []

        if hasattr(result, "empty") and result.empty:
            return []

        if hasattr(result, "to_dict"):
            records = result.to_dict("records")
        elif isinstance(result, list):
            records = result
        else:
            raise StockHistoryFetchError("Tushare 返回数据格式不支持")

        if not isinstance(records, list):
            raise StockHistoryFetchError("Tushare 返回记录格式不正确")

        return records

    def _normalize_items(self, records: List[Dict[str, Any]]) -> List[StockDailyBar]:
        normalized: List[StockDailyBar] = []

        for record in records:
            normalized.append(
                StockDailyBar(
                    ts_code=str(record["ts_code"]),
                    trade_date=self._parse_trade_date(record["trade_date"]),
                    open=self._to_float(record["open"]),
                    high=self._to_float(record["high"]),
                    low=self._to_float(record["low"]),
                    close=self._to_float(record["close"]),
                    pre_close=self._to_float(record["pre_close"]),
                    change=self._to_float(record["change"]),
                    pct_chg=self._to_float(record["pct_chg"]),
                    vol=self._to_float(record["vol"]),
                    amount=self._to_float(record["amount"]),
                )
            )

        normalized.sort(key=lambda item: item.trade_date)
        return normalized

    @staticmethod
    def _parse_trade_date(value: Any) -> date:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return datetime.strptime(value, "%Y%m%d").date()
        raise StockHistoryFetchError("trade_date 格式不支持")

    @staticmethod
    def _to_float(value: Any) -> float:
        return float(value)
