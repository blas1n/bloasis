"""Broker layer — provider-agnostic order execution.

`BrokerAdapter` Protocol decouples the trade pipeline from any specific
broker SDK. Concrete impls:
  - `InMemoryPaperBroker` for offline tests / `bloasis trade dry-run`.
  - `AlpacaBrokerAdapter(mode="paper"|"live")` for real Alpaca paper/live.

The protocol is intentionally minimal in v1 — market BUY + market SELL,
position read, account read. Limit / stop orders land in v2 once the
backtest is shown to produce useful signals on real data.
"""

from bloasis.broker.alpaca import AlpacaBrokerAdapter
from bloasis.broker.paper_simulator import InMemoryPaperBroker
from bloasis.broker.protocols import (
    AccountInfo,
    BrokerAdapter,
    BrokerOrder,
    BrokerPosition,
    OrderResult,
)

__all__ = [
    "AccountInfo",
    "AlpacaBrokerAdapter",
    "BrokerAdapter",
    "BrokerOrder",
    "BrokerPosition",
    "InMemoryPaperBroker",
    "OrderResult",
]
