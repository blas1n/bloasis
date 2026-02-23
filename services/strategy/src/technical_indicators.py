"""Technical Indicators using TA-Lib.

Provides a high-level wrapper around TA-Lib for computing common
technical indicators used in signal generation and factor scoring.
"""

import logging
from dataclasses import dataclass, field

import numpy as np
import talib

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicators:
    """Computed technical indicators for a single symbol."""

    symbol: str

    # Trend
    rsi_14: float = 50.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0
    adx: float = 0.0

    # Volatility
    atr_14: float = 0.0
    bb_upper: float = 0.0
    bb_mid: float = 0.0
    bb_lower: float = 0.0

    # Moving Averages
    sma_20: float = 0.0
    sma_50: float = 0.0
    ema_12: float = 0.0
    ema_26: float = 0.0

    # Momentum
    stoch_k: float = 50.0
    stoch_d: float = 50.0
    obv: float = 0.0

    # Raw arrays for downstream use
    atr_series: np.ndarray = field(
        default_factory=lambda: np.array([]),
        repr=False,
    )


def calculate_indicators(
    symbol: str,
    bars: list[dict],
) -> TechnicalIndicators | None:
    """Calculate all technical indicators for a symbol.

    Args:
        symbol: Stock ticker symbol.
        bars: OHLCV bars (dicts with open/high/low/close/volume keys).

    Returns:
        TechnicalIndicators or None if insufficient data.
    """
    if len(bars) < 26:
        logger.warning(
            f"Insufficient data for indicators: {symbol} "
            f"({len(bars)} bars, need 26)"
        )
        return None

    close = np.array([b["close"] for b in bars], dtype=np.float64)
    high = np.array([b["high"] for b in bars], dtype=np.float64)
    low = np.array([b["low"] for b in bars], dtype=np.float64)
    volume = np.array([b["volume"] for b in bars], dtype=np.float64)

    # RSI
    rsi = talib.RSI(close, timeperiod=14)

    # MACD
    macd, macd_signal, macd_hist = talib.MACD(
        close, fastperiod=12, slowperiod=26, signalperiod=9,
    )

    # ADX
    adx = talib.ADX(high, low, close, timeperiod=14)

    # ATR
    atr = talib.ATR(high, low, close, timeperiod=14)

    # Bollinger Bands
    bb_upper, bb_mid, bb_lower = talib.BBANDS(
        close, timeperiod=20, nbdevup=2, nbdevdn=2,
    )

    # Moving Averages
    sma_20 = talib.SMA(close, timeperiod=20)
    sma_50 = talib.SMA(close, timeperiod=min(50, len(bars)))
    ema_12 = talib.EMA(close, timeperiod=12)
    ema_26 = talib.EMA(close, timeperiod=26)

    # Stochastic
    stoch_k, stoch_d = talib.STOCH(
        high, low, close,
        fastk_period=14, slowk_period=3, slowd_period=3,
    )

    # OBV
    obv = talib.OBV(close, volume)

    def _last(arr: np.ndarray) -> float:
        """Get last non-NaN value from array."""
        valid = arr[~np.isnan(arr)]
        return float(valid[-1]) if len(valid) > 0 else 0.0

    return TechnicalIndicators(
        symbol=symbol,
        rsi_14=_last(rsi),
        macd=_last(macd),
        macd_signal=_last(macd_signal),
        macd_hist=_last(macd_hist),
        adx=_last(adx),
        atr_14=_last(atr),
        bb_upper=_last(bb_upper),
        bb_mid=_last(bb_mid),
        bb_lower=_last(bb_lower),
        sma_20=_last(sma_20),
        sma_50=_last(sma_50),
        ema_12=_last(ema_12),
        ema_26=_last(ema_26),
        stoch_k=_last(stoch_k),
        stoch_d=_last(stoch_d),
        obv=_last(obv),
        atr_series=atr,
    )


def format_indicators_summary(indicators: TechnicalIndicators) -> str:
    """Format indicators as a human-readable summary for Claude prompts.

    Args:
        indicators: Computed technical indicators.

    Returns:
        Multi-line formatted string.
    """
    return (
        f"{indicators.symbol}: "
        f"RSI={indicators.rsi_14:.1f}, "
        f"MACD={indicators.macd:.2f} (sig={indicators.macd_signal:.2f}, "
        f"hist={indicators.macd_hist:.2f}), "
        f"ADX={indicators.adx:.1f}, "
        f"ATR={indicators.atr_14:.2f}, "
        f"BB=[{indicators.bb_lower:.2f}/{indicators.bb_mid:.2f}/"
        f"{indicators.bb_upper:.2f}], "
        f"SMA20={indicators.sma_20:.2f}, SMA50={indicators.sma_50:.2f}, "
        f"Stoch={indicators.stoch_k:.1f}/{indicators.stoch_d:.1f}, "
        f"OBV={indicators.obv:,.0f}"
    )
