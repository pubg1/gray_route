"""Utility helpers for score calibration and normalization."""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Tuple


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp *value* to the inclusive range [low, high]."""

    return max(low, min(high, value))


def sigmoid(x: float) -> float:
    """Numerically stable logistic function returning a value in (0, 1)."""

    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def logistic_from_stats(value: float, stats: Optional[Tuple[float, float]], *, fallback: Optional[float] = None) -> float:
    """Normalize ``value`` using logistic scaling based on ``stats``.

    Args:
        value: Raw score.
        stats: Tuple of (mean, std). When std is very small the function falls
            back to a simple threshold around the mean.
        fallback: Optional value returned when ``stats`` is not available.

    Returns:
        A float in [0, 1].
    """

    if stats is None:
        return clamp(fallback if fallback is not None else value)

    mean, std = stats
    if std <= 1e-6:
        return 1.0 if value >= mean else 0.0
    z = (value - mean) / std
    return clamp(sigmoid(z))


def compute_stats(values: Iterable[float]) -> Optional[Tuple[float, float]]:
    """Return ``(mean, std)`` for the provided ``values`` if possible."""

    items = [float(v) for v in values if v is not None]
    if not items:
        return None
    mean = fmean(items)
    std = pstdev(items) if len(items) > 1 else 0.0
    return mean, std


def load_calibration_profile(path: str) -> Dict[str, Any]:
    """Load an optional calibration profile.

    The expected file format is JSON with a structure similar to::

        {
            "pass_threshold": 0.87,
            "gray_low_threshold": 0.66,
            "fusion_weights": {
                "rerank": 0.5,
                "semantic": 0.25,
                "keyword": 0.15,
                "knowledge": 0.05,
                "popularity": 0.05
            }
        }

    Any missing fields are ignored. The function returns an empty dictionary
    when the file is absent or malformed.
    """

    if not path:
        return {}

    try:
        data_path = Path(path)
    except (TypeError, ValueError):
        return {}

    if not data_path.is_file():
        return {}

    try:
        with data_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return {}

    if not isinstance(payload, MutableMapping):
        return {}

    return dict(payload)


def normalize_weight_mapping(mapping: Mapping[str, float], *, defaults: Mapping[str, float]) -> Dict[str, float]:
    """Normalize arbitrary weights so they sum up to 1.0.

    Args:
        mapping: Raw weights (may be partial).
        defaults: Fallback weights when a field is missing or the total weight
            is zero.
    """

    merged: Dict[str, float] = {k: float(v) for k, v in defaults.items()}
    for key, value in mapping.items():
        try:
            merged[key] = float(value)
        except (TypeError, ValueError):
            continue

    total = sum(merged.values())
    if total <= 0:
        return {k: float(v) for k, v in defaults.items()}

    return {k: float(v) / total for k, v in merged.items()}

