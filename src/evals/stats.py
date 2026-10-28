"""Small-sample statistics: a proportion is reported as k/n with its 95 % Wilson interval."""

import math
from typing import Any


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95 % Wilson score interval for k successes out of n (better than k/n ± for small n)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, center - half), min(1.0, center + half))


def proportion(k: int, n: int) -> dict[str, Any]:
    low, high = wilson(k, n)
    return {
        "k": k,
        "n": n,
        "rate": round(k / n, 4) if n else None,
        "wilson95": [round(low, 4), round(high, 4)],
    }
