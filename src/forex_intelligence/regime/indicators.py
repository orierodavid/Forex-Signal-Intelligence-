from __future__ import annotations

from math import sqrt


def ema(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError(f"Need at least {period} observations")
    alpha = 2.0 / (period + 1)
    value = sum(values[:period]) / period
    for item in values[period:]:
        value = alpha * item + (1 - alpha) * value
    return value


def true_ranges(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    if not (len(highs) == len(lows) == len(closes)) or len(closes) < 2:
        raise ValueError("OHLC series must have equal length and at least two bars")
    return [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, len(closes))
    ]


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    trs = true_ranges(highs, lows, closes)
    if len(trs) < period:
        raise ValueError(f"Need at least {period + 1} bars for ATR")
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = ((period - 1) * value + tr) / period
    return value


def adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    if len(closes) < period * 2 + 1:
        raise ValueError(f"Need at least {period * 2 + 1} bars for ADX")
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))

    tr_s = sum(trs[:period])
    plus_s = sum(plus_dm[:period])
    minus_s = sum(minus_dm[:period])
    dx_values: list[float] = []
    for i in range(period, len(trs)):
        tr_s = tr_s - tr_s / period + trs[i]
        plus_s = plus_s - plus_s / period + plus_dm[i]
        minus_s = minus_s - minus_s / period + minus_dm[i]
        if tr_s == 0:
            dx_values.append(0.0)
            continue
        plus_di = 100 * plus_s / tr_s
        minus_di = 100 * minus_s / tr_s
        total = plus_di + minus_di
        dx_values.append(100 * abs(plus_di - minus_di) / total if total else 0.0)
    if len(dx_values) < period:
        raise ValueError("Insufficient DX values for ADX")
    return sum(dx_values[-period:]) / period


def linear_slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        raise ValueError("At least two values are required")
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (value - y_mean) for i, value in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    return numerator / denominator if denominator else 0.0


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))
