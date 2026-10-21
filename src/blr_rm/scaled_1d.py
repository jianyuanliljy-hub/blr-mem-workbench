"""保持既有目标函数的对角尺度预处理；仅改变数值坐标。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from ._vendor.memecho import (
    joint_objective_and_gradient,
    pack_log_parameters,
    predict_joint_echo,
    unpack_log_parameters,
)


def scaled_coordinates(problem, continuum, transfer, background, alpha, stiffness):
    origin = pack_log_parameters(continuum, transfer, background)
    _, _, jc, jp = predict_joint_echo(problem, continuum, transfer, background)
    sampling = problem.continuum_sampling_matrix
    hc = np.sum((sampling * continuum[None, :] / problem.continuum_errors[:, None]) ** 2, axis=0)
    hc += np.sum((jc * continuum[None, :] / problem.line_errors[:, None]) ** 2, axis=0)
    hc += alpha * problem.delta_continuum_time * continuum
    hp = np.sum((jp * transfer[None, :] / problem.line_errors[:, None]) ** 2, axis=0)
    hp += alpha * stiffness * problem.delta_tau * transfer
    hb = np.sum((background / problem.line_errors) ** 2)
    scale = 1 / np.sqrt(np.maximum(np.r_[hc, hp, hb], 1e-20))

    def objective(coordinates):
        value, derivative = joint_objective_and_gradient(
            origin + scale * coordinates, problem, continuum, transfer, alpha, stiffness
        )
        return value, derivative * scale

    return origin, scale, objective


@dataclass
class Fit1D:
    continuum: np.ndarray
    transfer_function: np.ndarray
    line_background: float
    objective: float
    success: bool
    message: str
    iterations: int
    history: pd.DataFrame


def fit_scaled_1d(problem, initial_continuum, initial_transfer, initial_background, cfg):
    origin, scale, objective = scaled_coordinates(
        problem,
        initial_continuum,
        initial_transfer,
        initial_background,
        cfg["alpha"],
        cfg["stiffness_weight"],
    )
    records = []

    def record(z):
        value, gradient = objective(z)
        records.append(
            {
                "iteration": len(records) + 1,
                "objective_F": float(value),
                "scaled_gradient_inf": float(np.max(np.abs(gradient))),
                "original_log_gradient_inf": float(np.max(np.abs(gradient / scale))),
            }
        )

    optimization = minimize(
        objective,
        np.zeros_like(origin),
        method="L-BFGS-B",
        jac=True,
        bounds=list(zip((np.log(1e-10) - origin) / scale, (30 - origin) / scale)),
        callback=record,
        options={
            "maxiter": cfg["max_iterations"],
            "gtol": cfg["gradient_tolerance"],
            "ftol": cfg["function_tolerance"],
            "maxcor": 30,
            "maxls": 50,
        },
    )
    continuum, transfer, background = unpack_log_parameters(
        origin + scale * optimization.x, len(initial_continuum), len(initial_transfer)
    )
    return Fit1D(
        continuum,
        transfer,
        background,
        float(optimization.fun),
        bool(optimization.success),
        str(optimization.message),
        int(optimization.nit),
        pd.DataFrame(records),
    )
