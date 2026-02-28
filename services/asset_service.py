from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from crud.account_snapshot_crud import (
    get_latest_security_price_on_or_before,
    replace_security_prices,
)
from crud.asset_crud import (
    get_trade_records_for_codes_on_or_before,
    has_settlement_records,
    list_records_on_or_before,
)
from models.account_snapshot import SecurityDailyPrice
from models.settlement import SettlementRecord, SettlementTradeType
from schemas.asset import AssetCashFlowItem, AssetCashFlowResponse, AssetDetailResponse, AssetPositionItem
from services.simple_cache import SimpleTTLCache, app_cache
from services.stock_history_service import (
    StockHistoryFetchError,
    StockHistoryService,
)
from services.trade_calendar_service import TradeCalendarService, trade_calendar_service

logger = logging.getLogger(__name__)


class AssetDetailNotFoundError(LookupError):
    """资产详情数据不存在。"""


@dataclass
class CostBasisState:
    shares: int = 0
    remaining_cost_milli: int = 0


class AssetService:
    def __init__(
        self,
        stock_history_service: Optional[StockHistoryService] = None,
        trade_calendar_service_instance: Optional[TradeCalendarService] = None,
        cache: Optional[SimpleTTLCache] = None,
    ):
        self.stock_history_service = stock_history_service or StockHistoryService()
        self.trade_calendar_service = trade_calendar_service_instance or trade_calendar_service
        self.cache = cache or app_cache

    def get_asset_detail(
        self,
        db: Session,
        target_date: Optional[date] = None,
    ) -> AssetDetailResponse:
        now_shanghai = self._now_shanghai()
        resolved_target_date = target_date or now_shanghai.date()
        cache_key = self._build_asset_cache_key(resolved_target_date, now_shanghai)
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.info("资产详情命中内存缓存: target_date=%s", resolved_target_date)
            return cached  # type: ignore[return-value]
        logger.info("开始查询资产详情: target_date=%s", resolved_target_date)

        if not has_settlement_records(db):
            raise AssetDetailNotFoundError("暂无交割单数据")

        records = list_records_on_or_before(db, resolved_target_date)
        if not records:
            raise AssetDetailNotFoundError("目标日期及之前没有交割记录")
        logger.info("资产详情交割记录加载完成: target_date=%s, records=%s", resolved_target_date, len(records))

        cash_balance_milli_by_record = self._build_cash_balance_milli_by_record(records)
        cash_balance = self._milli_to_decimal(cash_balance_milli_by_record[records[-1].id])
        total_deposit, total_withdrawal, net_deposit = self._calculate_cash_flow_metrics(records)
        position_snapshots = self._extract_position_snapshots(records)

        if not position_snapshots:
            logger.info("资产详情无持仓: target_date=%s", resolved_target_date)
            response = AssetDetailResponse(
                target_date=resolved_target_date,
                pricing_trade_date=resolved_target_date,
                cash_balance=cash_balance,
                total_deposit=total_deposit,
                total_withdrawal=total_withdrawal,
                net_deposit=net_deposit,
                positions_market_value=Decimal("0"),
                total_assets=cash_balance,
                position_count=0,
                positions=[],
            )
            self.cache.set(cache_key, response, ttl_seconds=self._get_asset_cache_ttl(resolved_target_date, now_shanghai))
            return response

        security_codes = [record.security_code for record in position_snapshots if record.security_code]
        trade_records = get_trade_records_for_codes_on_or_before(db, resolved_target_date, security_codes)
        cost_states = self._build_cost_basis(trade_records)
        logger.info(
            "资产详情开始估值持仓: target_date=%s, positions=%s, trade_records=%s",
            resolved_target_date,
            len(position_snapshots),
            len(trade_records),
        )

        positions = []
        pricing_dates = []

        for snapshot in position_snapshots:
            if not snapshot.security_code:
                continue

            quantity = int(snapshot.share_balance)
            state = cost_states.get(snapshot.security_code, CostBasisState())
            cost_price, cost_amount = self._resolve_cost_values(state, quantity)
            close_price, price_trade_date = self._fetch_close_price(
                db=db,
                security_code=snapshot.security_code,
                target_date=resolved_target_date,
            )
            market_value = close_price * Decimal(quantity)
            unrealized_pnl = market_value - cost_amount
            unrealized_pnl_pct = None
            if cost_amount > 0:
                unrealized_pnl_pct = unrealized_pnl / cost_amount

            positions.append(
                AssetPositionItem(
                    security_code=snapshot.security_code,
                    security_name=snapshot.security_name,
                    market=snapshot.market,
                    quantity=quantity,
                    cost_price=cost_price,
                    cost_amount=cost_amount,
                    close_price=close_price,
                    price_trade_date=price_trade_date,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                )
            )
            pricing_dates.append(price_trade_date)

        positions.sort(key=lambda item: item.market_value, reverse=True)
        positions_market_value = sum((item.market_value for item in positions), Decimal("0"))

        response = AssetDetailResponse(
            target_date=resolved_target_date,
            pricing_trade_date=max(pricing_dates) if pricing_dates else resolved_target_date,
            cash_balance=cash_balance,
            total_deposit=total_deposit,
            total_withdrawal=total_withdrawal,
            net_deposit=net_deposit,
            positions_market_value=positions_market_value,
            total_assets=cash_balance + positions_market_value,
            position_count=len(positions),
            positions=positions,
        )
        self.cache.set(cache_key, response, ttl_seconds=self._get_asset_cache_ttl(resolved_target_date, now_shanghai))
        logger.info(
            "资产详情查询完成: target_date=%s, positions=%s, total_assets=%s",
            resolved_target_date,
            len(positions),
            response.total_assets,
        )
        return response

    def get_cash_flows(
        self,
        db: Session,
        target_date: Optional[date] = None,
        limit: int = 10,
    ) -> AssetCashFlowResponse:
        resolved_target_date = target_date or self._now_shanghai().date()
        normalized_limit = max(1, min(limit, 50))

        if not has_settlement_records(db):
            raise AssetDetailNotFoundError("暂无交割单数据")

        cache_key = self._build_cash_flow_cache_key(resolved_target_date, normalized_limit)
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.info(
                "资金流水命中内存缓存: target_date=%s, limit=%s",
                resolved_target_date,
                normalized_limit,
            )
            return cached  # type: ignore[return-value]
        logger.info("开始查询资金流水: target_date=%s, limit=%s", resolved_target_date, normalized_limit)

        records = list_records_on_or_before(db, resolved_target_date)
        cash_balance_milli_by_record = self._build_cash_balance_milli_by_record(records)
        cash_flow_records = [
            record
            for record in reversed(records)
            if record.trade_type in {
                SettlementTradeType.BANK_TO_SECURITY.value,
                SettlementTradeType.SECURITY_TO_BANK.value,
            }
        ]

        items = [
            AssetCashFlowItem(
                occur_date=record.occur_date,
                occur_time=record.occur_time,
                trade_type=record.trade_type,
                amount=record.amount,
                cash_balance=self._milli_to_decimal(cash_balance_milli_by_record[record.id]),
            )
            for record in cash_flow_records[:normalized_limit]
        ]

        response = AssetCashFlowResponse(
            target_date=resolved_target_date,
            count=len(items),
            items=items,
        )
        self.cache.set(
            cache_key,
            response,
            ttl_seconds=self._get_list_cache_ttl(resolved_target_date, self._now_shanghai()),
        )
        logger.info(
            "资金流水查询完成: target_date=%s, items=%s",
            resolved_target_date,
            len(items),
        )
        return response

    @staticmethod
    def _calculate_cash_flow_metrics(records: list[SettlementRecord]) -> tuple[Decimal, Decimal, Decimal]:
        deposit_milli = 0
        withdrawal_milli = 0

        for record in records:
            if record.trade_type == SettlementTradeType.BANK_TO_SECURITY.value:
                deposit_milli += max(int(record.amount_milli), 0)
            elif record.trade_type == SettlementTradeType.SECURITY_TO_BANK.value:
                withdrawal_milli += abs(int(record.amount_milli))

        total_deposit = AssetService._milli_to_decimal(deposit_milli)
        total_withdrawal = AssetService._milli_to_decimal(withdrawal_milli)
        net_deposit = AssetService._milli_to_decimal(deposit_milli - withdrawal_milli)
        return total_deposit, total_withdrawal, net_deposit

    @staticmethod
    def _extract_position_snapshots(records: list[SettlementRecord]) -> list[SettlementRecord]:
        latest_by_code: Dict[str, SettlementRecord] = {}

        for record in records:
            if not record.security_code or not AssetService._is_a_share_code(record.security_code):
                continue
            latest_by_code[record.security_code] = record

        snapshots = [record for record in latest_by_code.values() if int(record.share_balance) > 0]
        snapshots.sort(key=lambda item: item.security_code or "")
        return snapshots

    @staticmethod
    def _build_cost_basis(trade_records: list[SettlementRecord]) -> dict[str, CostBasisState]:
        states: dict[str, CostBasisState] = {}

        for record in trade_records:
            if not record.security_code:
                continue

            state = states.setdefault(record.security_code, CostBasisState())
            volume = int(record.volume)

            if record.trade_type == SettlementTradeType.SECURITY_BUY.value:
                state.shares += volume
                state.remaining_cost_milli += abs(int(record.amount_milli))
            elif record.trade_type == SettlementTradeType.SECURITY_SELL.value:
                if state.shares <= 0:
                    state.shares = 0
                    state.remaining_cost_milli = 0
                    continue

                sell_volume = min(volume, state.shares)
                sell_proceeds_milli = max(int(record.amount_milli), 0)
                state.shares -= sell_volume
                state.remaining_cost_milli -= sell_proceeds_milli

                if state.shares <= 0:
                    state.shares = 0
                    state.remaining_cost_milli = 0
                elif state.remaining_cost_milli < 0:
                    state.remaining_cost_milli = 0

        return states

    @staticmethod
    def _build_cash_balance_milli_by_record(records: list[SettlementRecord]) -> dict[int, int]:
        if not records:
            return {}

        current_cash_balance_milli = (
            int(records[0].cash_balance_milli) - int(records[0].amount_milli)
        )
        balances: dict[int, int] = {}
        for record in records:
            current_cash_balance_milli += int(record.amount_milli)
            balances[record.id] = current_cash_balance_milli
        return balances

    def _fetch_close_price(self, db: Session, security_code: str, target_date: date) -> tuple[Decimal, date]:
        pricing_trade_date = self.trade_calendar_service.get_effective_trade_date(
            target_date,
            now=self._now_shanghai(),
        )
        local_price = get_latest_security_price_on_or_before(
            db=db,
            security_code=security_code,
            target_date=pricing_trade_date,
        )
        if local_price is not None:
            logger.info(
                "本地价格命中: security_code=%s, trade_date=%s, close=%s",
                security_code,
                local_price.trade_date,
                self._milli_to_decimal(int(local_price.close_milli)),
            )
            return self._milli_to_decimal(int(local_price.close_milli)), local_price.trade_date

        logger.info(
            "开始估值证券: security_code=%s, target_date=%s, pricing_trade_date=%s",
            security_code,
            target_date,
            pricing_trade_date,
        )
        query_start = pricing_trade_date - timedelta(days=3)
        history = self.stock_history_service.get_stock_history(
            ts_code=security_code,
            start_date=query_start,
            end_date=pricing_trade_date,
        )
        if not history.items:
            raise StockHistoryFetchError(f"{security_code} 在 {pricing_trade_date} 及之前没有可用行情")

        selected_bar = None
        for bar in history.items:
            if bar.trade_date == pricing_trade_date:
                selected_bar = bar

        if selected_bar is None:
            for bar in history.items:
                if bar.trade_date <= pricing_trade_date:
                    selected_bar = bar

        if selected_bar is None:
            raise StockHistoryFetchError(f"{security_code} 在 {pricing_trade_date} 没有匹配的估值行情")

        self._store_security_price(
            db=db,
            security_code=security_code,
            trade_date=selected_bar.trade_date,
            ts_code=selected_bar.ts_code,
            close_price=Decimal(str(selected_bar.close)),
            open_price=Decimal(str(selected_bar.open)),
            high_price=Decimal(str(selected_bar.high)),
            low_price=Decimal(str(selected_bar.low)),
        )
        logger.info(
            "证券估值完成: security_code=%s, pricing_trade_date=%s, close=%s",
            security_code,
            selected_bar.trade_date,
            selected_bar.close,
        )
        return Decimal(str(selected_bar.close)), selected_bar.trade_date

    def _store_security_price(
        self,
        db: Session,
        security_code: str,
        trade_date: date,
        ts_code: str,
        close_price: Decimal,
        open_price: Decimal,
        high_price: Decimal,
        low_price: Decimal,
    ) -> None:
        row = SecurityDailyPrice(
            security_code=security_code,
            trade_date=trade_date,
            ts_code=ts_code,
            asset_type=None,
            close_milli=self._decimal_to_milli(close_price),
            open_milli=self._decimal_to_milli(open_price),
            high_milli=self._decimal_to_milli(high_price),
            low_milli=self._decimal_to_milli(low_price),
            source="tushare",
        )
        replace_security_prices(
            db=db,
            security_code=security_code,
            start_date=trade_date,
            end_date=trade_date,
            rows=[row],
        )
        logger.info("本地价格回填完成: security_code=%s, trade_date=%s", security_code, trade_date)

    @staticmethod
    def _resolve_cost_values(state: CostBasisState, final_shares: int) -> tuple[Decimal, Decimal]:
        if final_shares <= 0:
            return Decimal("0"), Decimal("0")

        if state.remaining_cost_milli <= 0:
            return Decimal("0"), Decimal("0")

        cost_amount = AssetService._milli_to_decimal(state.remaining_cost_milli)
        cost_price = cost_amount / Decimal(final_shares)
        return cost_price, cost_amount

    @staticmethod
    def _is_a_share_code(security_code: str) -> bool:
        return len(security_code) == 6 and security_code.isdigit()

    @staticmethod
    def _now_shanghai() -> datetime:
        return datetime.now(ZoneInfo("Asia/Shanghai"))

    def _build_asset_cache_key(self, target_date: date, now_shanghai: datetime) -> str:
        phase_bucket = self._get_pricing_phase_bucket(target_date, now_shanghai)
        parts: tuple[object, ...]
        if phase_bucket is None:
            parts = (target_date.isoformat(),)
        else:
            parts = (target_date.isoformat(), phase_bucket)
        return self.cache.build_key("asset_detail", parts)

    def _build_cash_flow_cache_key(self, target_date: date, limit: int) -> str:
        return self.cache.build_key(
            "asset_cash_flows",
            (
                target_date.isoformat(),
                limit,
            ),
        )

    def _get_asset_cache_ttl(self, target_date: date, now_shanghai: datetime) -> int:
        return self._get_list_cache_ttl(target_date, now_shanghai)

    @staticmethod
    def _get_list_cache_ttl(target_date: date, now_shanghai: datetime) -> int:
        if target_date >= now_shanghai.date():
            return 30
        return 300

    @staticmethod
    def _get_pricing_phase_bucket(target_date: date, now_shanghai: datetime) -> Optional[str]:
        if target_date < now_shanghai.date():
            return None
        if now_shanghai.time().hour < 15:
            return "pre_close"
        return "post_close"

    @staticmethod
    def _milli_to_decimal(value: int) -> Decimal:
        return Decimal(value) / Decimal("1000")

    @staticmethod
    def _decimal_to_milli(value: Decimal) -> int:
        return int((value * Decimal("1000")).quantize(Decimal("1")))


asset_service = AssetService()
