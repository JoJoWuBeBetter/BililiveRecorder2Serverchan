from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from crud.asset_crud import (
    get_trade_records_for_codes_on_or_before,
    has_settlement_records,
    list_records_on_or_before,
)
from models.settlement import SettlementRecord
from schemas.asset import AssetDetailResponse, AssetPositionItem
from services.stock_history_service import (
    StockHistoryFetchError,
    StockHistoryService,
)


class AssetDetailNotFoundError(LookupError):
    """资产详情数据不存在。"""


@dataclass
class CostBasisState:
    shares: int = 0
    remaining_cost: Decimal = Decimal("0")


class AssetService:
    def __init__(self, stock_history_service: Optional[StockHistoryService] = None):
        self.stock_history_service = stock_history_service or StockHistoryService()

    def get_asset_detail(
        self,
        db: Session,
        target_date: Optional[date] = None,
    ) -> AssetDetailResponse:
        resolved_target_date = target_date or self._now_shanghai().date()

        if not has_settlement_records(db):
            raise AssetDetailNotFoundError("暂无交割单数据")

        records = list_records_on_or_before(db, resolved_target_date)
        if not records:
            raise AssetDetailNotFoundError("目标日期及之前没有交割记录")

        cash_balance = Decimal(str(records[-1].cash_balance))
        position_snapshots = self._extract_position_snapshots(records)

        if not position_snapshots:
            return AssetDetailResponse(
                target_date=resolved_target_date,
                pricing_trade_date=resolved_target_date,
                cash_balance=cash_balance,
                positions_market_value=Decimal("0"),
                total_assets=cash_balance,
                position_count=0,
                positions=[],
            )

        security_codes = [record.security_code for record in position_snapshots if record.security_code]
        trade_records = get_trade_records_for_codes_on_or_before(db, resolved_target_date, security_codes)
        cost_states = self._build_cost_basis(trade_records)

        positions = []
        pricing_dates = []

        for snapshot in position_snapshots:
            if not snapshot.security_code:
                continue

            quantity = int(snapshot.share_balance)
            state = cost_states.get(snapshot.security_code, CostBasisState())
            cost_price, cost_amount = self._resolve_cost_values(state, quantity)
            close_price, price_trade_date = self._fetch_close_price(snapshot.security_code, resolved_target_date)
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

        return AssetDetailResponse(
            target_date=resolved_target_date,
            pricing_trade_date=max(pricing_dates) if pricing_dates else resolved_target_date,
            cash_balance=cash_balance,
            positions_market_value=positions_market_value,
            total_assets=cash_balance + positions_market_value,
            position_count=len(positions),
            positions=positions,
        )

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

            if record.trade_type == "证券买入":
                state.shares += volume
                state.remaining_cost += abs(Decimal(str(record.amount)))
            elif record.trade_type == "证券卖出":
                if state.shares <= 0:
                    state.shares = 0
                    state.remaining_cost = Decimal("0")
                    continue

                sell_volume = min(volume, state.shares)
                average_cost = state.remaining_cost / Decimal(state.shares) if state.shares > 0 else Decimal("0")
                deducted_cost = average_cost * Decimal(sell_volume)
                state.shares -= sell_volume
                state.remaining_cost -= deducted_cost

                if state.shares <= 0:
                    state.shares = 0
                    state.remaining_cost = Decimal("0")
                elif state.remaining_cost < 0:
                    state.remaining_cost = Decimal("0")

        return states

    def _fetch_close_price(self, security_code: str, target_date: date) -> tuple[Decimal, date]:
        query_start = target_date - timedelta(days=10)
        history = self.stock_history_service.get_stock_history(
            ts_code=security_code,
            start_date=query_start,
            end_date=target_date,
        )
        if not history.items:
            raise StockHistoryFetchError(f"{security_code} 在 {target_date} 及之前没有可用行情")

        selected_bar = history.items[-1]
        now = self._now_shanghai()
        if target_date == now.date() and now.time() < time(15, 0, 0) and selected_bar.trade_date == target_date:
            if len(history.items) < 2:
                raise StockHistoryFetchError(f"{security_code} 在 {target_date} 未收盘且没有上一交易日行情")
            selected_bar = history.items[-2]

        return Decimal(str(selected_bar.close)), selected_bar.trade_date

    @staticmethod
    def _resolve_cost_values(state: CostBasisState, final_shares: int) -> tuple[Decimal, Decimal]:
        if final_shares <= 0:
            return Decimal("0"), Decimal("0")

        if state.remaining_cost <= 0:
            return Decimal("0"), Decimal("0")

        cost_price = state.remaining_cost / Decimal(final_shares)
        cost_amount = cost_price * Decimal(final_shares)
        return cost_price, cost_amount

    @staticmethod
    def _is_a_share_code(security_code: str) -> bool:
        return len(security_code) == 6 and security_code.isdigit()

    @staticmethod
    def _now_shanghai() -> datetime:
        return datetime.now(ZoneInfo("Asia/Shanghai"))


asset_service = AssetService()
