"""Reliability and novelty-stratified calibration summaries."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from synthaudit.models.evidence import CalibrationSliceV1, ReliabilityBinV1


def reliability_summary(
    labels: Sequence[int],
    scores: Sequence[float],
    *,
    slice_id: str,
    bin_count: int = 10,
) -> CalibrationSliceV1:
    if len(labels) != len(scores):
        raise ValueError("calibration labels and scores must be aligned")
    if bin_count < 2:
        raise ValueError("reliability summary requires at least two bins")
    if not labels:
        return CalibrationSliceV1(
            slice_id=slice_id,
            sample_count=0,
            reliability_bins=tuple(
                ReliabilityBinV1(
                    lower_bound=index / bin_count,
                    upper_bound=(index + 1) / bin_count,
                    sample_count=0,
                )
                for index in range(bin_count)
            ),
        )
    label_array = np.asarray(labels, dtype=float)
    score_array = np.asarray(scores, dtype=float)
    if np.any((score_array < 0) | (score_array > 1)):
        raise ValueError("calibrated evidence scores must be within [0, 1]")
    bins: list[ReliabilityBinV1] = []
    weighted_gap = 0.0
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        mask = (score_array >= lower) & (
            (score_array <= upper) if index == bin_count - 1 else (score_array < upper)
        )
        count = int(np.sum(mask))
        mean_score = float(np.mean(score_array[mask])) if count else None
        support_fraction = float(np.mean(label_array[mask])) if count else None
        if mean_score is not None and support_fraction is not None:
            weighted_gap += count * abs(mean_score - support_fraction)
        bins.append(
            ReliabilityBinV1(
                lower_bound=lower,
                upper_bound=upper,
                sample_count=count,
                mean_evidence_score=mean_score,
                observed_support_fraction=support_fraction,
            )
        )
    return CalibrationSliceV1(
        slice_id=slice_id,
        sample_count=len(labels),
        brier_score=float(np.mean((score_array - label_array) ** 2)),
        expected_calibration_error=weighted_gap / len(labels),
        reliability_bins=tuple(bins),
    )


def novelty_stratified_calibration(
    labels: Sequence[int],
    scores: Sequence[float],
    novelty: Sequence[float | None],
    *,
    bin_count: int = 10,
) -> tuple[CalibrationSliceV1, ...]:
    if not (len(labels) == len(scores) == len(novelty)):
        raise ValueError("novelty-stratified calibration inputs must be aligned")
    strata = (
        ("novelty-low-[0,0.33)", 0.0, 0.33, False),
        ("novelty-mid-[0.33,0.66)", 0.33, 0.66, False),
        ("novelty-high-[0.66,1]", 0.66, 1.0, True),
    )
    results: list[CalibrationSliceV1] = []
    for name, lower, upper, inclusive in strata:
        indexes = [
            index
            for index, value in enumerate(novelty)
            if value is not None
            and value >= lower
            and (value <= upper if inclusive else value < upper)
        ]
        results.append(
            reliability_summary(
                [labels[index] for index in indexes],
                [scores[index] for index in indexes],
                slice_id=name,
                bin_count=bin_count,
            )
        )
    missing_indexes = [index for index, value in enumerate(novelty) if value is None]
    results.append(
        reliability_summary(
            [labels[index] for index in missing_indexes],
            [scores[index] for index in missing_indexes],
            slice_id="novelty-unavailable",
            bin_count=bin_count,
        )
    )
    return tuple(results)
