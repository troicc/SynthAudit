"""Held-out score calibration; raw model scores remain explicitly uncalibrated."""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from synthaudit.models.evidence import CalibrationMethod


class FittedScoreCalibrator(Protocol):
    method: CalibrationMethod

    def transform(self, scores: np.ndarray) -> np.ndarray: ...


class PlattScoreCalibrator:
    method = CalibrationMethod.PLATT

    def __init__(self, model: Any) -> None:
        self.model = model

    @classmethod
    def fit(cls, scores: np.ndarray, labels: np.ndarray) -> PlattScoreCalibrator:
        model = LogisticRegression(random_state=0, solver="lbfgs")
        model.fit(scores.reshape(-1, 1), labels)
        return cls(model)

    def transform(self, scores: np.ndarray) -> np.ndarray:
        return np.asarray(self.model.predict_proba(scores.reshape(-1, 1))[:, 1], dtype=float)


class IsotonicScoreCalibrator:
    method = CalibrationMethod.ISOTONIC

    def __init__(self, model: Any) -> None:
        self.model = model

    @classmethod
    def fit(cls, scores: np.ndarray, labels: np.ndarray) -> IsotonicScoreCalibrator:
        model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        model.fit(scores, labels)
        return cls(model)

    def transform(self, scores: np.ndarray) -> np.ndarray:
        return np.asarray(self.model.predict(scores), dtype=float)


def fit_score_calibrator(
    method: CalibrationMethod,
    scores: np.ndarray,
    labels: np.ndarray,
) -> FittedScoreCalibrator:
    if len(scores) != len(labels) or not len(scores):
        raise ValueError("calibration requires aligned non-empty scores and labels")
    if len(set(int(value) for value in labels)) != 2:
        raise ValueError("calibration requires both support annotation classes")
    if method == CalibrationMethod.PLATT:
        return PlattScoreCalibrator.fit(scores, labels)
    if method == CalibrationMethod.ISOTONIC:
        return IsotonicScoreCalibrator.fit(scores, labels)
    raise ValueError("calibrator fitting requires Platt or isotonic method")
