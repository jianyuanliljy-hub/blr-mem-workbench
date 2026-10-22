"""显式配置、单位和首版支持范围。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np


def defaults(dimension: int = 1) -> dict:
    if isinstance(dimension, bool) or dimension not in (1, 2):
        raise ValueError("dimension 只支持 1 或 2")
    return {
        "schema_version": 1,
        "dimension": dimension,
        "seed": 731,
        "family": "gaussian" if dimension == 1 else "tilted_gaussian",
        "duration_days": 60.0,
        "cadence_days": 1.0,
        "delay_max_days": 15.0,
        "delay_step_days": 1.0,
        "n_velocity": 1 if dimension == 1 else 9,
        "velocity_max_kms": 3000.0,
        "continuum_background": 10.0,
        "line_background": 5.0,
        "psd_beta": 1.5,
        "noise_fraction": 0.0,
        "missing_fraction": 0.0,
    }


def solver_defaults(dimension: int) -> dict:
    if dimension == 1:
        return {
            "engine": "joint_mem_1d_scaled_fixed_default",
            "alpha": 0.2,
            "stiffness_weight": 1.0,
            "max_iterations": 1200,
            "gradient_tolerance": 1e-7,
            "function_tolerance": 1e-15,
            "stationarity_tolerance": 1e-3,
        }
    if dimension != 2:
        raise ValueError("dimension 只支持 1 或 2")
    return {
        "engine": "joint_mem_2d_floating_default",
        "alpha_map": 1000.0,
        "alpha_c": 200.0,
        "alpha_lbg": 10.0,
        "smoothness_ratio": 1.0,
        "default_iterations": 6,
        "optimizer_maxiter": 1200,
        "default_damping": 0.5,
        "coordinate_cycles": 80,
        "test_threshold": 1e-4,
        "q_gradient_threshold": 5e-3,
        "default_change_tolerance": 2e-3,
    }


def read_config(path: str | Path | None, dimension: int = 1) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig")) if path else {}
    return resolved_generator(raw, dimension)


def resolved_generator(raw: dict, dimension: int = 1) -> dict:
    if not isinstance(raw, dict):
        raise ValueError('生成配置必须是 JSON 对象，例如 {"noise_fraction": 0.05}')  # noqa: TRY004
    cfg = defaults(raw.get("dimension", dimension))
    unknown = set(raw) - set(cfg)
    if unknown:
        raise ValueError(f"未识别的生成参数: {sorted(unknown)}")
    cfg.update(raw)
    validate_config(cfg)
    return cfg


def validate_config(cfg: dict) -> None:
    if not isinstance(cfg, dict) or "dimension" not in cfg:
        raise ValueError("生成配置必须包含 dimension，取值为 1 或 2")
    base = defaults(cfg["dimension"])
    if set(cfg) != set(base) or cfg["schema_version"] != 1:
        raise ValueError("生成配置字段或 schema_version 不符合版本 1")
    if isinstance(cfg["seed"], bool) or not isinstance(cfg["seed"], int) or cfg["seed"] < 0:
        raise ValueError("seed 必须为非负整数")
    for name in (
        "duration_days",
        "cadence_days",
        "delay_max_days",
        "delay_step_days",
        "velocity_max_kms",
        "continuum_background",
        "line_background",
    ):
        value = cfg[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not np.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} 必须为有限正数")
    for name in ("noise_fraction", "missing_fraction"):
        value = cfg[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not np.isfinite(value)
            or not 0 <= value < 1
        ):
            raise ValueError(f"{name} 必须在 [0,1) 内")
    beta = cfg["psd_beta"]
    if (
        isinstance(beta, bool)
        or not isinstance(beta, (int, float))
        or not np.isfinite(beta)
        or not 0 <= beta <= 4
    ):
        raise ValueError("psd_beta 必须在 [0,4] 内")
    if cfg["family"] not in ("gaussian", "double_gaussian", "top_hat", "tilted_gaussian", "two_blobs"):
        raise ValueError("未知传递函数族")
    if cfg["dimension"] == 1 and cfg["family"] not in ("gaussian", "double_gaussian", "top_hat"):
        raise ValueError("该形态仅适用于二维")
    nv = cfg["n_velocity"]
    if not isinstance(nv, int) or isinstance(nv, bool) or (nv != 1 if cfg["dimension"] == 1 else nv < 2):
        raise ValueError("一维要求 n_velocity=1；二维要求整数 n_velocity>=2")
    regular_grid(0, cfg["duration_days"], cfg["cadence_days"])
    regular_grid(0, cfg["delay_max_days"], cfg["delay_step_days"])
    regular_grid(-cfg["delay_max_days"], cfg["duration_days"], cfg["cadence_days"])
    nt = round(cfg["duration_days"] / cfg["cadence_days"]) + 1
    if nt * (1 - cfg["missing_fraction"]) < 3:
        raise ValueError("至少需要三个观测时刻")


def regular_grid(start: float, stop: float, step: float) -> np.ndarray:
    count = (float(stop) - float(start)) / float(step)
    if count < 1 or not np.isclose(count, round(count), rtol=0, atol=1e-9):
        raise ValueError("范围必须包含至少两个点，且可被步长整除")
    return np.linspace(start, stop, round(count) + 1)


def resolved_solver(dimension: int, overrides: dict | None = None) -> dict:
    cfg = copy.deepcopy(solver_defaults(dimension))
    overrides = {} if overrides is None else overrides
    if not isinstance(overrides, dict):
        raise ValueError("优化配置必须是 JSON 对象")  # noqa: TRY004 -- JSON 配置错误统一使用 ValueError。
    autumn = overrides.get('engine') == 'autumn_normalized_joint_mem'
    if autumn:
        cfg.update(engine='autumn_normalized_joint_mem', gradient_backend='manual',
                   jax_device='cpu', jax_jit=False, use_numba=False, adam_steps=40,
                   alpha_map=.2, alpha_c=1200., alpha_lbg=.02,
                   smoothness_ratio=1., default_iterations=1000,
                   optimizer_maxiter=800, default_damping=.5,
                   test_threshold=1e-5, q_gradient_threshold=.003,
                   default_change_tolerance=.01)
    if set(overrides) - set(cfg):
        raise ValueError(f"未识别的优化参数: {sorted(set(overrides) - set(cfg))}")
    cfg.update(overrides)
    if not autumn and cfg["engine"] != solver_defaults(dimension)["engine"]:
        raise ValueError("engine 必须与数据维度对应")
    for name, value in cfg.items():
        if name == "engine":
            continue
        if autumn and name in ('gradient_backend', 'jax_device'):
            allowed = ('manual', 'jax') if name == 'gradient_backend' else ('cpu', 'gpu', 'auto')
            if value not in allowed:
                raise ValueError(f'{name} must be one of {allowed}')
            continue
        if autumn and name in ('jax_jit', 'use_numba'):
            if not isinstance(value, bool):
                raise ValueError(f'{name} must be boolean')
            continue
        if autumn and name == 'adam_steps':
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError('adam_steps must be a nonnegative integer')
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not np.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} 必须为有限正数")
        if (
            name.endswith("iterations")
            or name in ("default_iterations", "optimizer_maxiter", "coordinate_cycles")
        ) and not isinstance(value, int):
            raise ValueError(f"{name} 必须为整数")
    if cfg.get("default_damping", 1) > 1:
        raise ValueError("default_damping 必须在 (0,1] 内")
    return cfg
