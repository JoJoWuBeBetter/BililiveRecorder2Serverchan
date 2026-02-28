from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from crud.account_snapshot_crud import (
    delete_snapshots_from_date,
    get_latest_snapshot_before,
    get_latest_snapshot_date,
    get_latest_security_price_on_or_before,
    get_security_prices_in_range,
    get_snapshot_on_date,
    get_snapshot_positions_map,
    get_snapshot_positions_on_date,
    replace_security_prices,
    replace_snapshots,
)
from crud.asset_crud import has_settlement_records
from models.account_snapshot import AccountDailyPosition, AccountDailySnapshot, SecurityDailyPrice
from models.settlement import SettlementRecord, SettlementTradeType
from schemas.asset import AssetDetailResponse, AssetPositionItem, AssetSnapshotRebuildResponse
from services.asset_service import AssetDetailNotFoundError
from services.simple_cache import app_cache
from services.stock_history_service import StockHistoryService
from services.trade_calendar_service import TradeCalendarService, trade_calendar_service

logger = logging.getLogger(__name__)


@dataclass
class PositionState:
    security_code: str
    security_name: Optional[str] = None
    market: Optional[str] = None
    quantity: int = 0
    book_shares: int = 0
    remaining_cost_milli: int = 0


class AccountSnapshotService:
    def __init__(
        self,
        stock_history_service: Optional[StockHistoryService] = None,
        trade_calendar_service_instance: Optional[TradeCalendarService] = None,
    ):
        self.stock_history_service = stock_history_service or StockHistoryService()
        self.trade_calendar_service = trade_calendar_service_instance or trade_calendar_service

    def rebuild_snapshots(
        self,
        db: Session,
        mode: str = "incremental",
        from_date: Optional[date] = None,
        include_pricing: bool = True,
    ) -> AssetSnapshotRebuildResponse:
        settlement_records = self._load_settlement_records(db)
        overall_start = settlement_records[0].occur_date
        overall_end = settlement_records[-1].occur_date
        rebuild_from_date = self._resolve_rebuild_from_date(
            db=db,
            mode=mode,
            explicit_from_date=from_date,
            overall_start=overall_start,
        )
        logger.info(
            "开始重建账户快照: mode=%s, from=%s, overall_start=%s, overall_end=%s, include_pricing=%s, settlement_records=%s",
            mode,
            rebuild_from_date,
            overall_start,
            overall_end,
            include_pricing,
            len(settlement_records),
        )

        try:
            trade_days = self.trade_calendar_service.get_trade_days(rebuild_from_date, overall_end, db=db)
        except TypeError:
            trade_days = self.trade_calendar_service.get_trade_days(rebuild_from_date, overall_end)
        if not trade_days:
            raise AssetDetailNotFoundError("目标区间内没有交易日，无法生成快照")
        logger.info("账户快照交易日装载完成: from=%s, to=%s, trade_days=%s", rebuild_from_date, overall_end, len(trade_days))

        seed_state = self._load_seed_state(db, rebuild_from_date)
        records_from_date = [record for record in settlement_records if record.occur_date >= rebuild_from_date]

        snapshot_payloads, position_payloads = self._build_ledger_snapshots(
            trade_days=trade_days,
            settlement_records=records_from_date,
            seed_state=seed_state,
        )

        security_codes = sorted(
            {
                position.security_code
                for positions in position_payloads.values()
                for position in positions
            }
        )

        if include_pricing and security_codes:
            logger.info(
                "开始回填快照行情: from=%s, to=%s, securities=%s",
                rebuild_from_date,
                overall_end,
                len(security_codes),
            )
            self._sync_security_prices(
                db=db,
                security_codes=security_codes,
                start_date=rebuild_from_date,
                end_date=overall_end,
            )
            logger.info("快照行情回填完成: from=%s, to=%s", rebuild_from_date, overall_end)
            self._apply_pricing(
                db=db,
                snapshots=snapshot_payloads,
                positions_by_date=position_payloads,
                trade_days=trade_days,
                security_codes=security_codes,
                start_date=rebuild_from_date,
                end_date=overall_end,
            )

        snapshots = []
        positions = []
        for snapshot_date in trade_days:
            snapshots.append(snapshot_payloads[snapshot_date])
            positions.extend(position_payloads[snapshot_date])

        delete_snapshots_from_date(db, rebuild_from_date)
        snapshot_count, position_count = replace_snapshots(db, snapshots=snapshots, positions=positions)
        logger.info(
            "账户快照重建完成: from=%s, to=%s, snapshots=%s, positions=%s, include_pricing=%s",
            rebuild_from_date,
            overall_end,
            snapshot_count,
            position_count,
            include_pricing,
        )

        return AssetSnapshotRebuildResponse(
            mode=mode,
            from_date=rebuild_from_date,
            to_date=overall_end,
            trade_day_count=len(trade_days),
            security_count=len(security_codes),
            snapshot_count=snapshot_count,
            position_count=position_count,
            include_pricing=include_pricing,
        )

    def get_snapshot_detail(self, db: Session, snapshot_date: date) -> AssetDetailResponse:
        logger.info("读取持久化账户快照: snapshot_date=%s", snapshot_date)
        snapshot = get_snapshot_on_date(db, snapshot_date)
        if snapshot is None:
            raise AssetDetailNotFoundError("该日期没有已持久化的账户快照")

        positions = []
        positions_market_value_milli = 0
        latest_price_trade_date: Optional[date] = snapshot.pricing_trade_date
        for row in get_snapshot_positions_on_date(db, snapshot_date):
            close_price_milli = row.close_price_milli
            market_value_milli = row.market_value_milli
            unrealized_pnl_milli = row.unrealized_pnl_milli
            unrealized_pnl_pct_bp = row.unrealized_pnl_pct_bp
            price_trade_date = row.price_trade_date or snapshot.snapshot_date

            if close_price_milli is None or market_value_milli is None:
                price_row = get_latest_security_price_on_or_before(
                    db=db,
                    security_code=row.security_code,
                    target_date=snapshot.snapshot_date,
                )
                if price_row is not None:
                    close_price_milli = int(price_row.close_milli)
                    market_value_milli = close_price_milli * int(row.quantity)
                    unrealized_pnl_milli = market_value_milli - int(row.cost_amount_milli)
                    if int(row.cost_amount_milli) > 0:
                        unrealized_pnl_pct_bp = int(
                            (
                                Decimal(unrealized_pnl_milli)
                                / Decimal(row.cost_amount_milli)
                                * Decimal("10000")
                            ).quantize(Decimal("1"))
                        )
                    else:
                        unrealized_pnl_pct_bp = None
                    price_trade_date = price_row.trade_date
                else:
                    market_value_milli = int(row.cost_amount_milli)
                    unrealized_pnl_milli = 0
                    if int(row.cost_amount_milli) > 0 and int(row.quantity) > 0:
                        close_price_milli = int(int(row.cost_amount_milli) / int(row.quantity))
                        unrealized_pnl_pct_bp = 0
                    else:
                        close_price_milli = 0
                        unrealized_pnl_pct_bp = None

            positions_market_value_milli += int(market_value_milli or 0)
            if latest_price_trade_date is None or price_trade_date > latest_price_trade_date:
                latest_price_trade_date = price_trade_date
            positions.append(
                AssetPositionItem(
                    security_code=row.security_code,
                    security_name=row.security_name,
                    market=row.market,
                    quantity=row.quantity,
                    cost_price=self._milli_to_decimal(row.cost_price_milli),
                    cost_amount=self._milli_to_decimal(row.cost_amount_milli),
                    close_price=self._milli_to_decimal(close_price_milli or 0),
                    price_trade_date=price_trade_date,
                    market_value=self._milli_to_decimal(market_value_milli or 0),
                    unrealized_pnl=self._milli_to_decimal(unrealized_pnl_milli or 0),
                    unrealized_pnl_pct=self._bp_to_ratio(unrealized_pnl_pct_bp),
                )
            )

        positions.sort(key=lambda item: item.market_value, reverse=True)
        total_assets_milli = int(snapshot.cash_balance_milli) + positions_market_value_milli

        return AssetDetailResponse(
            target_date=snapshot.snapshot_date,
            pricing_trade_date=latest_price_trade_date or snapshot.snapshot_date,
            cash_balance=self._milli_to_decimal(snapshot.cash_balance_milli),
            total_deposit=self._milli_to_decimal(snapshot.total_deposit_milli),
            total_withdrawal=self._milli_to_decimal(snapshot.total_withdrawal_milli),
            net_deposit=self._milli_to_decimal(snapshot.net_deposit_milli),
            positions_market_value=self._milli_to_decimal(positions_market_value_milli),
            total_assets=self._milli_to_decimal(total_assets_milli),
            position_count=snapshot.position_count,
            positions=positions,
        )

    def _load_settlement_records(self, db: Session) -> list[SettlementRecord]:
        if not has_settlement_records(db):
            raise AssetDetailNotFoundError("暂无交割单数据")

        records = (
            db.query(SettlementRecord)
            .order_by(
                SettlementRecord.occur_date.asc(),
                SettlementRecord.occur_time.asc(),
                SettlementRecord.id.asc(),
            )
            .all()
        )
        if not records:
            raise AssetDetailNotFoundError("暂无交割单数据")
        return records

    def _resolve_rebuild_from_date(
        self,
        db: Session,
        mode: str,
        explicit_from_date: Optional[date],
        overall_start: date,
    ) -> date:
        if explicit_from_date is not None:
            return explicit_from_date

        if mode != "incremental":
            return overall_start

        latest_snapshot_date = get_latest_snapshot_date(db)
        if latest_snapshot_date is None:
            return overall_start
        return latest_snapshot_date

    def _load_seed_state(self, db: Session, rebuild_from_date: date) -> dict[str, object]:
        previous_snapshot = get_latest_snapshot_before(db, rebuild_from_date)
        if previous_snapshot is None:
            opening_cash_balance_milli = 0
            if first_record := self._get_first_settlement_record(db):
                opening_cash_balance_milli = (
                    int(first_record.cash_balance_milli) - int(first_record.amount_milli)
                )
            return {
                "cash_balance_milli": opening_cash_balance_milli,
                "total_deposit_milli": 0,
                "total_withdrawal_milli": 0,
                "positions": {},
            }

        previous_positions = get_snapshot_positions_map(db, previous_snapshot.snapshot_date)
        positions: dict[str, PositionState] = {}
        for code, row in previous_positions.items():
            positions[code] = PositionState(
                security_code=code,
                security_name=row.security_name,
                market=row.market,
                quantity=int(row.quantity),
                book_shares=int(row.quantity),
                remaining_cost_milli=int(row.cost_amount_milli),
            )

        return {
            "cash_balance_milli": int(previous_snapshot.cash_balance_milli),
            "total_deposit_milli": int(previous_snapshot.total_deposit_milli),
            "total_withdrawal_milli": int(previous_snapshot.total_withdrawal_milli),
            "positions": positions,
        }

    def _build_ledger_snapshots(
        self,
        trade_days: list[date],
        settlement_records: list[SettlementRecord],
        seed_state: dict[str, object],
    ) -> tuple[dict[date, AccountDailySnapshot], dict[date, list[AccountDailyPosition]]]:
        ordered_trade_days = sorted(trade_days)
        cash_balance_milli = int(seed_state["cash_balance_milli"])
        total_deposit_milli = int(seed_state["total_deposit_milli"])
        total_withdrawal_milli = int(seed_state["total_withdrawal_milli"])
        positions: dict[str, PositionState] = dict(seed_state["positions"])  # shallow copy is sufficient

        record_index = 0
        snapshots: dict[date, AccountDailySnapshot] = {}
        positions_by_date: dict[date, list[AccountDailyPosition]] = {}

        for trade_day in ordered_trade_days:
            while record_index < len(settlement_records) and settlement_records[record_index].occur_date <= trade_day:
                record = settlement_records[record_index]
                cash_balance_milli += int(record.amount_milli)

                if record.trade_type == SettlementTradeType.BANK_TO_SECURITY.value:
                    total_deposit_milli += max(int(record.amount_milli), 0)
                elif record.trade_type == SettlementTradeType.SECURITY_TO_BANK.value:
                    total_withdrawal_milli += abs(int(record.amount_milli))

                self._apply_position_record(positions, record)
                record_index += 1

            daily_positions: list[AccountDailyPosition] = []
            positions_cost_milli = 0

            for state in positions.values():
                if state.quantity <= 0:
                    continue

                cost_amount_milli = max(state.remaining_cost_milli, 0)
                positions_cost_milli += cost_amount_milli
                cost_price_milli = int(cost_amount_milli / state.quantity) if state.quantity > 0 else 0
                daily_positions.append(
                    AccountDailyPosition(
                        snapshot_date=trade_day,
                        security_code=state.security_code,
                        security_name=state.security_name,
                        market=state.market,
                        quantity=state.quantity,
                        cost_price_milli=cost_price_milli,
                        cost_amount_milli=cost_amount_milli,
                    )
                )

            daily_positions.sort(key=lambda item: item.security_code)
            net_deposit_milli = total_deposit_milli - total_withdrawal_milli
            estimated_positions_value_milli = positions_cost_milli
            estimated_total_assets_milli = cash_balance_milli + estimated_positions_value_milli
            estimated_net_profit_milli = estimated_total_assets_milli - net_deposit_milli
            estimated_return_rate_bp = None
            if net_deposit_milli > 0:
                estimated_return_rate_bp = int(
                    (
                        Decimal(estimated_net_profit_milli)
                        / Decimal(net_deposit_milli)
                        * Decimal("10000")
                    ).quantize(Decimal("1"))
                )
            snapshots[trade_day] = AccountDailySnapshot(
                snapshot_date=trade_day,
                is_trade_day=True,
                cash_balance_milli=cash_balance_milli,
                total_deposit_milli=total_deposit_milli,
                total_withdrawal_milli=total_withdrawal_milli,
                net_deposit_milli=net_deposit_milli,
                positions_cost_milli=positions_cost_milli,
                positions_market_value_milli=estimated_positions_value_milli,
                total_assets_milli=estimated_total_assets_milli,
                net_profit_milli=estimated_net_profit_milli,
                return_rate_bp=estimated_return_rate_bp,
                position_count=len(daily_positions),
            )
            positions_by_date[trade_day] = daily_positions

        return snapshots, positions_by_date

    @staticmethod
    def _get_first_settlement_record(db: Session) -> Optional[SettlementRecord]:
        return (
            db.query(SettlementRecord)
            .order_by(
                SettlementRecord.occur_date.asc(),
                SettlementRecord.occur_time.asc(),
                SettlementRecord.id.asc(),
            )
            .first()
        )

    def _apply_position_record(self, positions: dict[str, PositionState], record: SettlementRecord) -> None:
        if not record.security_code or not self._is_a_share_code(record.security_code):
            return

        state = positions.setdefault(record.security_code, PositionState(security_code=record.security_code))
        state.security_name = record.security_name
        state.market = record.market
        state.quantity = int(record.share_balance)

        if record.trade_type == SettlementTradeType.SECURITY_BUY.value:
            state.book_shares += int(record.volume)
            state.remaining_cost_milli += abs(int(record.amount_milli))
        elif record.trade_type == SettlementTradeType.SECURITY_SELL.value:
            sell_volume = min(int(record.volume), state.book_shares)
            if state.book_shares > 0 and sell_volume > 0:
                sell_proceeds_milli = max(int(record.amount_milli), 0)
                state.book_shares -= sell_volume
                state.remaining_cost_milli -= sell_proceeds_milli
                if state.book_shares <= 0:
                    state.book_shares = 0
                    state.remaining_cost_milli = 0
                elif state.remaining_cost_milli < 0:
                    state.remaining_cost_milli = 0

        if state.quantity <= 0:
            state.book_shares = 0
            state.remaining_cost_milli = 0

    def _sync_security_prices(
        self,
        db: Session,
        security_codes: list[str],
        start_date: date,
        end_date: date,
    ) -> None:
        for security_code in security_codes:
            logger.info(
                "同步证券价格: security_code=%s, start=%s, end=%s",
                security_code,
                start_date,
                end_date,
            )
            history = self.stock_history_service.get_stock_history(
                ts_code=security_code,
                start_date=start_date,
                end_date=end_date,
            )

            rows: list[SecurityDailyPrice] = []
            for item in history.items:
                rows.append(
                    SecurityDailyPrice(
                        security_code=security_code,
                        trade_date=item.trade_date,
                        ts_code=item.ts_code,
                        asset_type=None,
                        close_milli=self._decimal_to_milli(Decimal(str(item.close))),
                        open_milli=self._decimal_to_milli(Decimal(str(item.open))),
                        high_milli=self._decimal_to_milli(Decimal(str(item.high))),
                        low_milli=self._decimal_to_milli(Decimal(str(item.low))),
                        source="tushare",
                    )
                )

            replace_security_prices(
                db=db,
                security_code=security_code,
                start_date=start_date,
                end_date=end_date,
                rows=rows,
            )
            logger.info(
                "证券价格同步完成: security_code=%s, rows=%s",
                security_code,
                len(rows),
            )

    def _apply_pricing(
        self,
        db: Session,
        snapshots: dict[date, AccountDailySnapshot],
        positions_by_date: dict[date, list[AccountDailyPosition]],
        trade_days: list[date],
        security_codes: list[str],
        start_date: date,
        end_date: date,
    ) -> None:
        price_rows = get_security_prices_in_range(
            db=db,
            security_codes=security_codes,
            start_date=start_date,
            end_date=end_date,
        )
        price_lookup: dict[str, list[SecurityDailyPrice]] = {}
        for row in price_rows:
            price_lookup.setdefault(row.security_code, []).append(row)

        for trade_day in trade_days:
            positions = positions_by_date[trade_day]
            market_value_total = 0
            latest_price_trade_date: Optional[date] = None

            for position in positions:
                price_row = self._find_latest_price(price_lookup.get(position.security_code, []), trade_day)
                if price_row is None:
                    continue

                close_price_milli = int(price_row.close_milli)
                market_value_milli = close_price_milli * int(position.quantity)
                unrealized_pnl_milli = market_value_milli - int(position.cost_amount_milli)
                unrealized_pnl_pct_bp = None
                if int(position.cost_amount_milli) > 0:
                    unrealized_pnl_pct_bp = int(
                        (
                            Decimal(unrealized_pnl_milli)
                            / Decimal(position.cost_amount_milli)
                            * Decimal("10000")
                        ).quantize(Decimal("1"))
                    )

                position.close_price_milli = close_price_milli
                position.market_value_milli = market_value_milli
                position.unrealized_pnl_milli = unrealized_pnl_milli
                position.unrealized_pnl_pct_bp = unrealized_pnl_pct_bp
                position.price_trade_date = price_row.trade_date
                market_value_total += market_value_milli

                if latest_price_trade_date is None or price_row.trade_date > latest_price_trade_date:
                    latest_price_trade_date = price_row.trade_date

            snapshot = snapshots[trade_day]
            snapshot.pricing_trade_date = latest_price_trade_date or trade_day
            snapshot.positions_market_value_milli = market_value_total
            snapshot.total_assets_milli = int(snapshot.cash_balance_milli) + market_value_total
            snapshot.net_profit_milli = int(snapshot.total_assets_milli) - int(snapshot.net_deposit_milli)
            if int(snapshot.net_deposit_milli) > 0:
                snapshot.return_rate_bp = int(
                    (
                        Decimal(snapshot.net_profit_milli)
                        / Decimal(snapshot.net_deposit_milli)
                        * Decimal("10000")
                    ).quantize(Decimal("1"))
                )
            else:
                snapshot.return_rate_bp = None

    @staticmethod
    def _find_latest_price(
        rows: list[SecurityDailyPrice], target_date: date
    ) -> Optional[SecurityDailyPrice]:
        selected = None
        for row in rows:
            if row.trade_date <= target_date:
                selected = row
            else:
                break
        return selected

    @staticmethod
    def _is_a_share_code(security_code: str) -> bool:
        return len(security_code) == 6 and security_code.isdigit()

    @staticmethod
    def _milli_to_decimal(value: int) -> Decimal:
        return Decimal(value) / Decimal("1000")

    @staticmethod
    def _bp_to_ratio(value: Optional[int]) -> Optional[Decimal]:
        if value is None:
            return None
        return Decimal(value) / Decimal("10000")

    @staticmethod
    def _decimal_to_milli(value: Decimal) -> int:
        return int((value * Decimal("1000")).quantize(Decimal("1")))


account_snapshot_service = AccountSnapshotService()
