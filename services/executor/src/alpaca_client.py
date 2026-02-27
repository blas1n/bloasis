"""Alpaca trading client wrapper for paper trading."""

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from .models import AccountInfo, OrderResult, OrderStatus, PositionInfo

if TYPE_CHECKING:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.models import Position, TradeAccount

logger = logging.getLogger(__name__)


class AlpacaClient:
    """Alpaca trading client for order execution.

    This client wraps the Alpaca Trading API for paper trading.
    In Phase 1, only paper trading is supported.
    """

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        paper: bool = True,
    ) -> None:
        """Initialize Alpaca client.

        Args:
            api_key: Alpaca API key (default from config)
            secret_key: Alpaca secret key (default from config)
            paper: Use paper trading (default True, required for Phase 1)
        """
        self.api_key = api_key or ""
        self.secret_key = secret_key or ""
        self.paper = paper
        self._client: "TradingClient | None" = None

        if not paper:
            raise ValueError("Live trading is not supported in Phase 1")

    def _get_client(self) -> "TradingClient":
        """Get or create the Alpaca trading client.

        Returns:
            TradingClient instance

        Raises:
            ValueError: If API keys are not configured
        """
        if self._client is None:
            if not self.api_key or not self.secret_key:
                raise ValueError("Alpaca API keys not configured")

            from alpaca.trading.client import TradingClient

            self._client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper,
            )
            logger.info(f"Alpaca client initialized (paper={self.paper})")

        return self._client

    async def submit_market_order(
        self,
        symbol: str,
        qty: Decimal,
        side: str,
        client_order_id: str | None = None,
    ) -> OrderResult:
        """Submit a market order.

        Args:
            symbol: Stock ticker symbol
            qty: Quantity to trade
            side: "buy" or "sell"
            client_order_id: Optional client-side order ID

        Returns:
            OrderResult with execution details
        """
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

        request = MarketOrderRequest(
            symbol=symbol,
            qty=float(qty),
            side=order_side,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )

        try:
            client = self._get_client()
            order = client.submit_order(request)
            logger.info(f"Market order submitted: {symbol} {side} {qty}")
            return self._to_order_result(order)
        except Exception as e:
            logger.error(f"Market order submission failed: {e}")
            return self._create_rejected_result(
                symbol=symbol,
                side=side,
                qty=qty,
                client_order_id=client_order_id or "",
                error_message=str(e),
            )

    async def submit_limit_order(
        self,
        symbol: str,
        qty: Decimal,
        side: str,
        limit_price: Decimal,
        client_order_id: str | None = None,
    ) -> OrderResult:
        """Submit a limit order.

        Args:
            symbol: Stock ticker symbol
            qty: Quantity to trade
            side: "buy" or "sell"
            limit_price: Limit price for the order
            client_order_id: Optional client-side order ID

        Returns:
            OrderResult with execution details
        """
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest

        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

        request = LimitOrderRequest(
            symbol=symbol,
            qty=float(qty),
            side=order_side,
            time_in_force=TimeInForce.DAY,
            limit_price=float(limit_price),
            client_order_id=client_order_id,
        )

        try:
            client = self._get_client()
            order = client.submit_order(request)
            logger.info(f"Limit order submitted: {symbol} {side} {qty} @ {limit_price}")
            return self._to_order_result(order)
        except Exception as e:
            logger.error(f"Limit order submission failed: {e}")
            return self._create_rejected_result(
                symbol=symbol,
                side=side,
                qty=qty,
                client_order_id=client_order_id or "",
                error_message=str(e),
            )

    async def submit_bracket_order(
        self,
        symbol: str,
        qty: Decimal,
        side: str,
        stop_loss: Decimal,
        take_profit: Decimal,
        client_order_id: str | None = None,
    ) -> OrderResult:
        """Submit a bracket order with stop-loss and take-profit.

        This is the recommended order type for risk-managed trades.
        If the first attempt fails due to stale bracket prices (entry_price
        vs current market price gap), adjusts SL/TP using the base_price
        from Alpaca's error response and retries once.

        Args:
            symbol: Stock ticker symbol
            qty: Quantity to trade
            side: "buy" or "sell"
            stop_loss: Stop loss price
            take_profit: Take profit price
            client_order_id: Optional client-side order ID

        Returns:
            OrderResult with execution details
        """
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import (
            MarketOrderRequest,
            StopLossRequest,
            TakeProfitRequest,
        )

        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

        # Round prices to cents — Alpaca rejects sub-penny values
        rounded_sl = float(stop_loss.quantize(Decimal("0.01")))
        rounded_tp = float(take_profit.quantize(Decimal("0.01")))

        def _build_bracket_request(sl_price: float, tp_price: float) -> MarketOrderRequest:
            return MarketOrderRequest(
                symbol=symbol,
                qty=float(qty),
                side=order_side,
                time_in_force=TimeInForce.DAY,
                client_order_id=client_order_id,
                order_class="bracket",
                stop_loss=StopLossRequest(stop_price=sl_price),
                take_profit=TakeProfitRequest(limit_price=tp_price),
            )

        try:
            client = self._get_client()
            order = client.submit_order(_build_bracket_request(rounded_sl, rounded_tp))
            logger.info(
                f"Bracket order submitted: {symbol} {side} {qty} (SL={rounded_sl}, TP={rounded_tp})"
            )
            result = self._to_order_result(order)
            result.order_type = "bracket"
            return result
        except Exception as e:
            # Try to extract base_price from Alpaca error and retry with adjusted prices
            adjusted = self._adjust_bracket_prices(
                str(e), side.lower(), rounded_sl, rounded_tp,
            )
            if adjusted:
                adj_sl, adj_tp = adjusted
                try:
                    order = client.submit_order(_build_bracket_request(adj_sl, adj_tp))
                    logger.info(
                        f"BRACKET_RETRY: Adjusted bracket order submitted: "
                        f"{symbol} {side} {qty} (SL={adj_sl}, TP={adj_tp})"
                    )
                    result = self._to_order_result(order)
                    result.order_type = "bracket"
                    return result
                except Exception as retry_err:
                    logger.warning(
                        f"BRACKET_DOWNGRADE: Retry also failed for {symbol} {side}, "
                        f"falling back to market order: {retry_err}"
                    )
            else:
                logger.warning(
                    f"BRACKET_DOWNGRADE: Bracket order failed for {symbol} {side}, "
                    f"falling back to market order without SL/TP protection: {e}"
                )

            result = await self.submit_market_order(
                symbol=symbol,
                qty=qty,
                side=side,
                client_order_id=client_order_id,
            )
            result.order_type = "market"
            return result

    @staticmethod
    def _adjust_bracket_prices(
        error_msg: str,
        side: str,
        sl: float,
        tp: float,
    ) -> tuple[float, float] | None:
        """Try to adjust bracket prices using base_price from Alpaca error.

        Alpaca errors include the current base_price when bracket prices are
        invalid. We use it to recalculate valid SL/TP with a 3% buffer.

        Args:
            error_msg: Alpaca error message (JSON string).
            side: "buy" or "sell".
            sl: Original stop loss price.
            tp: Original take profit price.

        Returns:
            Tuple of (adjusted_sl, adjusted_tp) or None if not adjustable.
        """
        import json as _json
        import re

        # Extract base_price from error like {"base_price":"69.47","code":42210000,...}
        match = re.search(r'"base_price"\s*:\s*"([0-9.]+)"', error_msg)
        if not match:
            return None

        try:
            base_price = float(match.group(1))
        except ValueError:
            return None

        buffer = Decimal("0.03")  # 3% buffer from market price
        base = Decimal(str(base_price))

        if side == "sell":
            # Sell bracket: SL must be above base_price
            new_sl = float((base * (1 + buffer)).quantize(Decimal("0.01")))
            # TP must be below base_price
            new_tp = float((base * (1 - buffer)).quantize(Decimal("0.01")))
            if new_tp <= 0:
                return None
            return new_sl, new_tp
        else:
            # Buy bracket: SL must be below base_price
            new_sl = float((base * (1 - buffer)).quantize(Decimal("0.01")))
            # TP must be above base_price
            new_tp = float((base * (1 + buffer)).quantize(Decimal("0.01")))
            if new_sl <= 0:
                return None
            return new_sl, new_tp

    async def get_order_status(self, order_id: str) -> OrderResult:
        """Get current status of an order.

        Args:
            order_id: Alpaca order ID

        Returns:
            OrderResult with current status

        Raises:
            Exception: If order not found or API error
        """
        try:
            client = self._get_client()
            order = client.get_order_by_id(order_id)
            return self._to_order_result(order)
        except Exception as e:
            logger.error(f"Failed to get order status for {order_id}: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order.

        Args:
            order_id: Alpaca order ID to cancel

        Returns:
            True if cancelled successfully, False otherwise
        """
        try:
            client = self._get_client()
            client.cancel_order_by_id(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_account(self) -> AccountInfo:
        """Get account information.

        Returns:
            AccountInfo with balance details
        """
        client = self._get_client()
        account = cast("TradeAccount", client.get_account())

        return AccountInfo(
            cash=Decimal(str(account.cash)),
            buying_power=Decimal(str(account.buying_power)),
            portfolio_value=Decimal(str(account.portfolio_value)),
            equity=Decimal(str(account.equity)),
        )

    async def get_positions(self) -> list[PositionInfo]:
        """Get all open positions from Alpaca.

        Returns:
            List of PositionInfo with current position data.
        """
        try:
            client = self._get_client()
            positions = cast(list["Position"], client.get_all_positions())

            return [
                PositionInfo(
                    symbol=pos.symbol,
                    qty=Decimal(str(pos.qty)),
                    avg_entry_price=Decimal(str(pos.avg_entry_price)),
                    current_price=Decimal(str(pos.current_price)),
                    market_value=Decimal(str(pos.market_value)),
                    unrealized_pl=Decimal(str(pos.unrealized_pl)),
                    unrealized_plpc=Decimal(str(pos.unrealized_plpc)),
                    side=pos.side.value if hasattr(pos.side, "value") else str(pos.side),
                )
                for pos in positions
            ]
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise

    def _to_order_result(self, order) -> OrderResult:
        """Convert Alpaca order to OrderResult.

        Args:
            order: Alpaca Order object

        Returns:
            OrderResult dataclass
        """
        # Map Alpaca status to our OrderStatus enum
        status_mapping = {
            "new": OrderStatus.SUBMITTED,
            "pending_new": OrderStatus.PENDING,
            "accepted": OrderStatus.SUBMITTED,
            "pending_cancel": OrderStatus.SUBMITTED,
            "pending_replace": OrderStatus.SUBMITTED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "filled": OrderStatus.FILLED,
            "done_for_day": OrderStatus.EXPIRED,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.EXPIRED,
            "replaced": OrderStatus.SUBMITTED,
            "stopped": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "suspended": OrderStatus.REJECTED,
            "calculated": OrderStatus.PENDING,
        }

        status = status_mapping.get(order.status.value, OrderStatus.PENDING)

        return OrderResult(
            order_id=str(order.id),
            client_order_id=order.client_order_id or "",
            symbol=order.symbol,
            side=order.side.value,
            qty=Decimal(str(order.qty)),
            status=status,
            filled_qty=Decimal(str(order.filled_qty or 0)),
            filled_avg_price=(
                Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None
            ),
            submitted_at=str(order.submitted_at) if order.submitted_at else "",
            filled_at=str(order.filled_at) if order.filled_at else None,
        )

    def _create_rejected_result(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        client_order_id: str,
        error_message: str,
    ) -> OrderResult:
        """Create a rejected OrderResult for failed submissions.

        Args:
            symbol: Stock ticker symbol
            side: Order side
            qty: Quantity
            client_order_id: Client order ID
            error_message: Error message

        Returns:
            OrderResult with REJECTED status
        """
        return OrderResult(
            order_id="",
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            status=OrderStatus.REJECTED,
            filled_qty=Decimal("0"),
            filled_avg_price=None,
            submitted_at="",
            filled_at=None,
            error_message=error_message,
        )
