"""连续谱插值权重及观测支撑检查。"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def query_support_mask(
    sample_times: FloatArray,
    query_times: FloatArray,
    max_interpolation_gap: float | None = None,
) -> NDArray[np.bool_]:
    """标记范围内且不落入无支撑长缺口的查询时刻。"""
    times = np.asarray(sample_times, dtype=float)
    query = np.asarray(query_times, dtype=float)
    if times.ndim != 1 or times.size < 2 or np.any(np.diff(times) <= 0):
        raise ValueError("样本时间必须是至少含两个点的严格递增一维数组")
    valid = (query >= times[0]) & (query <= times[-1])
    if max_interpolation_gap is None:
        return valid
    if max_interpolation_gap <= 0:
        raise ValueError("max_interpolation_gap 必须为正或 None")

    insertion = np.searchsorted(times, query, side="left")
    exact_index = np.clip(insertion, 0, times.size - 1)
    exact = np.isclose(query, times[exact_index])
    right = np.clip(insertion, 1, times.size - 1)
    bracket_width = times[right] - times[right - 1]
    return valid & (exact | (bracket_width <= max_interpolation_gap))


def interpolation_weights(
    sample_times: FloatArray,
    query_times: FloatArray,
    method: str = "linear",
    smoothing_days: float | None = None,
    max_interpolation_gap: float | None = None,
) -> FloatArray:
    """返回查询值对样本值的线性算子，末轴对应样本。

    `linear` 是分段线性插值；`gaussian_kernel` 是局部 Gaussian 核回归。
    当给定长缺口阈值时，核权重不会跨越被判定为无支撑的时间段。
    """
    times = np.asarray(sample_times, dtype=float)
    query = np.asarray(query_times, dtype=float)
    supported = query_support_mask(times, query, max_interpolation_gap)
    if not np.all(supported):
        raise ValueError("插值权重不允许范围外或长缺口内查询")

    flat_query = query.ravel()
    if method == "linear":
        right = np.searchsorted(times, flat_query, side="right")
        right = np.clip(right, 1, times.size - 1)
        left = right - 1
        denominator = times[right] - times[left]
        right_weight = (flat_query - times[left]) / denominator
        left_weight = 1.0 - right_weight
        weights = np.zeros((flat_query.size, times.size), dtype=float)
        rows = np.arange(flat_query.size)
        weights[rows, left] += left_weight
        weights[rows, right] += right_weight
    elif method == "gaussian_kernel":
        if smoothing_days is None or smoothing_days <= 0:
            raise ValueError("gaussian_kernel 要求 smoothing_days > 0")
        distance = (flat_query[:, None] - times[None, :]) / float(smoothing_days)
        weights = np.exp(-0.5 * distance**2)
        if max_interpolation_gap is not None:
            segment = np.r_[0, np.cumsum(np.diff(times) > max_interpolation_gap)]
            insertion = np.searchsorted(times, flat_query, side="left")
            exact_index = np.clip(insertion, 0, times.size - 1)
            exact = np.isclose(flat_query, times[exact_index])
            right = np.clip(insertion, 1, times.size - 1)
            query_segment = np.where(exact, segment[exact_index], segment[right - 1])
            weights *= segment[None, :] == query_segment[:, None]
        normalization = weights.sum(axis=1)
        if np.any(normalization <= 0):
            raise ValueError("Gaussian 核在部分查询点没有观测支撑")
        weights /= normalization[:, None]
    else:
        raise ValueError(f"未知连续谱插值方法: {method}")
    return np.asarray(weights.reshape(query.shape + (times.size,)), dtype=float)
