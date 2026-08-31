"""Held-out evidence-score calibration and reliability analysis."""

# ruff: noqa: F401 -- TYPE_CHECKING imports document the lazy public API.

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from synthaudit.calibration.calibrators import (
        FittedScoreCalibrator,
        IsotonicScoreCalibrator,
        PlattScoreCalibrator,
        fit_score_calibrator,
    )
    from synthaudit.calibration.metrics import (
        novelty_stratified_calibration,
        reliability_summary,
    )

_EXPORTS = {
    "FittedScoreCalibrator": (
        "synthaudit.calibration.calibrators",
        "FittedScoreCalibrator",
    ),
    "IsotonicScoreCalibrator": (
        "synthaudit.calibration.calibrators",
        "IsotonicScoreCalibrator",
    ),
    "PlattScoreCalibrator": (
        "synthaudit.calibration.calibrators",
        "PlattScoreCalibrator",
    ),
    "fit_score_calibrator": (
        "synthaudit.calibration.calibrators",
        "fit_score_calibrator",
    ),
    "novelty_stratified_calibration": (
        "synthaudit.calibration.metrics",
        "novelty_stratified_calibration",
    ),
    "reliability_summary": (
        "synthaudit.calibration.metrics",
        "reliability_summary",
    ),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
