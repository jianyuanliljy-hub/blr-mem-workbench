"""Horne (1994) 风格的一维连续谱—转移函数联合最大熵反演。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.optimize import minimize

from .interpolation import interpolation_weights

FloatArray = NDArray[np.float64]
DefaultMode = Literal["fixed", "curvature"]


@dataclass(frozen=True)
class JointEchoProblem:
    """联合反演所需的数据和预先计算的线性算子。"""

    continuum_grid_times: FloatArray
    delays: FloatArray
    continuum_observation_times: FloatArray
    continuum_observed: FloatArray
    continuum_errors: FloatArray
    line_times: FloatArray
    line_observed: FloatArray
    line_errors: FloatArray
    continuum_background: float
    delta_continuum_time: float
    delta_tau: float
    continuum_sampling_matrix: FloatArray
    delayed_continuum_tensor: FloatArray

    @property
    def number_of_data(self) -> int:
        return int(self.continuum_observed.size + self.line_observed.size)


@dataclass(frozen=True)
class JointMemOptions:
    max_iterations: int = 1200
    gradient_tolerance: float = 1e-7
    function_tolerance: float = 1e-12
    maximum_outer_iterations: int = 6
    default_tolerance: float = 2e-3
    positivity_floor: float = 1e-10
    maximum_equalization_iterations: int = 4
    equalization_tolerance: float = 0.08
    minimum_error_scale: float = 0.5
    maximum_error_scale: float = 2.0
    history_stride: int = 10


@dataclass(frozen=True)
class JointMemResult:
    continuum: FloatArray
    transfer_function: FloatArray
    line_background: float
    continuum_model_at_observations: FloatArray
    line_model: FloatArray
    chi_square_continuum: float
    chi_square_line: float
    entropy_continuum: float
    entropy_transfer: float
    objective: float
    alpha: float
    stiffness_weight: float
    success: bool
    message: str
    iterations: int
    outer_iterations: int
    scaled_gradient_norm: float
    history: pd.DataFrame
    continuum_error_scale: float = 1.0
    line_error_scale: float = 1.0
    equalization_iterations: int = 0
    effective_chi_square_continuum: float | None = None
    effective_chi_square_line: float | None = None

    @property
    def chi_square_total(self) -> float:
        return self.chi_square_continuum + self.chi_square_line

    @property
    def chi_square_per_datum(self) -> float:
        number_of_data = (
            self.continuum_model_at_observations.size + self.line_model.size
        )
        return self.chi_square_total / number_of_data


@dataclass(frozen=True)
class JointMemPathResult:
    selected: JointMemResult
    candidates: tuple[JointMemResult, ...]
    summary: pd.DataFrame
    target_chi_square_per_datum: float


def _strictly_increasing(values: FloatArray, name: str) -> None:
    if values.ndim != 1 or values.size < 2 or np.any(np.diff(values) <= 0):
        raise ValueError(f"{name} 必须是至少含两个点的严格递增一维数组")


def _constant_spacing(values: FloatArray, name: str) -> float:
    spacing = np.diff(values)
    if not np.allclose(spacing, spacing[0], rtol=1e-7, atol=1e-10):
        raise ValueError(f"{name} 当前必须采用等间隔网格")
    return float(spacing[0])


def build_joint_echo_problem(
    continuum_grid_times: FloatArray,
    delays: FloatArray,
    continuum_observation_times: FloatArray,
    continuum_observed: FloatArray,
    continuum_errors: FloatArray,
    line_times: FloatArray,
    line_observed: FloatArray,
    line_errors: FloatArray,
    continuum_background: float,
) -> JointEchoProblem:
    """建立联合反演问题，并预计算所有时间插值权重。"""
    grid = np.asarray(continuum_grid_times, dtype=float)
    lag = np.asarray(delays, dtype=float)
    continuum_times = np.asarray(continuum_observation_times, dtype=float)
    continuum_data = np.asarray(continuum_observed, dtype=float)
    continuum_sigma = np.asarray(continuum_errors, dtype=float)
    line_time = np.asarray(line_times, dtype=float)
    line_data = np.asarray(line_observed, dtype=float)
    line_sigma = np.asarray(line_errors, dtype=float)

    _strictly_increasing(grid, "连续谱网格")
    _strictly_increasing(lag, "延迟网格")
    _strictly_increasing(continuum_times, "连续谱观测时刻")
    _strictly_increasing(line_time, "发射线观测时刻")
    delta_continuum_time = _constant_spacing(grid, "连续谱网格")
    delta_tau = _constant_spacing(lag, "延迟网格")

    if continuum_data.shape != continuum_times.shape:
        raise ValueError("连续谱观测值与观测时刻形状不一致")
    if continuum_sigma.shape != continuum_times.shape:
        raise ValueError("连续谱误差与观测时刻形状不一致")
    if line_data.shape != line_time.shape or line_sigma.shape != line_time.shape:
        raise ValueError("发射线观测值、误差与观测时刻形状不一致")
    if np.any(continuum_data <= 0) or np.any(line_data <= 0):
        raise ValueError("当前正性参数化要求连续谱和发射线观测值为正")
    if np.any(continuum_sigma <= 0) or np.any(line_sigma <= 0):
        raise ValueError("所有观测误差必须为正")
    if continuum_background <= 0:
        raise ValueError("连续谱基准值必须为正")

    continuum_sampling_matrix = interpolation_weights(grid, continuum_times)
    delayed_queries = line_time[:, None] - lag[None, :]
    delayed_continuum_tensor = interpolation_weights(grid, delayed_queries)

    return JointEchoProblem(
        continuum_grid_times=grid,
        delays=lag,
        continuum_observation_times=continuum_times,
        continuum_observed=continuum_data,
        continuum_errors=continuum_sigma,
        line_times=line_time,
        line_observed=line_data,
        line_errors=line_sigma,
        continuum_background=float(continuum_background),
        delta_continuum_time=delta_continuum_time,
        delta_tau=delta_tau,
        continuum_sampling_matrix=np.asarray(continuum_sampling_matrix, dtype=float),
        delayed_continuum_tensor=np.asarray(delayed_continuum_tensor, dtype=float),
    )


def curvature_default(values: FloatArray, floor: float = 1e-10) -> FloatArray:
    """返回 Horne (1994) 使用的局部几何平均曲率默认图像。"""
    current = np.maximum(np.asarray(values, dtype=float), floor)
    if current.ndim != 1 or current.size < 2:
        raise ValueError("曲率默认图像要求至少两个一维网格点")
    result = np.empty_like(current)
    result[0] = np.sqrt(current[0] * current[1])
    result[-1] = np.sqrt(current[-2] * current[-1])
    if current.size > 2:
        result[1:-1] = np.sqrt(current[:-2] * current[2:])
    return np.maximum(result, floor)


def relative_entropy(values: FloatArray, default: FloatArray, spacing: float) -> float:
    """计算正图像相对于默认图像的离散相对熵。"""
    values = np.asarray(values, dtype=float)
    default = np.asarray(default, dtype=float)
    if values.shape != default.shape or np.any(values <= 0) or np.any(default <= 0):
        raise ValueError("当前图像和默认图像必须同形且严格为正")
    terms = values - default - values * np.log(values / default)
    return float(np.sum(terms) * spacing)


def pack_log_parameters(
    continuum: FloatArray, transfer_function: FloatArray, line_background: float
) -> FloatArray:
    if np.any(continuum <= 0) or np.any(transfer_function <= 0) or line_background <= 0:
        raise ValueError("对数参数化要求所有参数严格为正")
    return np.log(np.r_[continuum, transfer_function, line_background])


def unpack_log_parameters(
    log_parameters: FloatArray, number_of_continuum: int, number_of_delays: int
) -> tuple[FloatArray, FloatArray, float]:
    physical = np.exp(np.asarray(log_parameters, dtype=float))
    expected_size = number_of_continuum + number_of_delays + 1
    if physical.size != expected_size:
        raise ValueError("联合参数向量长度与问题尺寸不一致")
    continuum = physical[:number_of_continuum]
    transfer = physical[number_of_continuum : number_of_continuum + number_of_delays]
    return continuum, transfer, float(physical[-1])


def predict_joint_echo(
    problem: JointEchoProblem,
    continuum: FloatArray,
    transfer_function: FloatArray,
    line_background: float,
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """预测两组观测，并返回发射线对两类图像的 Jacobian。"""
    continuum_delta = continuum - problem.continuum_background
    delayed_continuum = np.einsum(
        "ijk,k->ij", problem.delayed_continuum_tensor, continuum_delta
    )
    continuum_model = problem.continuum_sampling_matrix @ continuum
    line_model = line_background + problem.delta_tau * (
        delayed_continuum @ transfer_function
    )
    line_jacobian_continuum = problem.delta_tau * np.einsum(
        "ijk,j->ik", problem.delayed_continuum_tensor, transfer_function
    )
    line_jacobian_transfer = problem.delta_tau * delayed_continuum
    return (
        np.asarray(continuum_model, dtype=float),
        np.asarray(line_model, dtype=float),
        np.asarray(line_jacobian_continuum, dtype=float),
        np.asarray(line_jacobian_transfer, dtype=float),
    )


def joint_objective_and_gradient(
    log_parameters: FloatArray,
    problem: JointEchoProblem,
    continuum_default: FloatArray,
    transfer_default: FloatArray,
    alpha: float,
    stiffness_weight: float,
) -> tuple[float, FloatArray]:
    """返回联合最大熵目标函数和对数参数坐标中的解析梯度。"""
    if alpha <= 0 or stiffness_weight <= 0:
        raise ValueError("alpha 和 W 必须为正")
    continuum, transfer, line_background = unpack_log_parameters(
        log_parameters,
        problem.continuum_grid_times.size,
        problem.delays.size,
    )
    continuum_model, line_model, jacobian_continuum, jacobian_transfer = (
        predict_joint_echo(problem, continuum, transfer, line_background)
    )

    continuum_residual = continuum_model - problem.continuum_observed
    line_residual = line_model - problem.line_observed
    weighted_continuum_residual = continuum_residual / problem.continuum_errors**2
    weighted_line_residual = line_residual / problem.line_errors**2

    chi_square_continuum = float(
        np.sum((continuum_residual / problem.continuum_errors) ** 2)
    )
    chi_square_line = float(np.sum((line_residual / problem.line_errors) ** 2))
    entropy_continuum = relative_entropy(
        continuum, continuum_default, problem.delta_continuum_time
    )
    entropy_transfer = relative_entropy(
        transfer, transfer_default, problem.delta_tau
    )
    objective = 0.5 * (chi_square_continuum + chi_square_line) - alpha * (
        entropy_continuum + stiffness_weight * entropy_transfer
    )

    gradient_continuum = (
        problem.continuum_sampling_matrix.T @ weighted_continuum_residual
        + jacobian_continuum.T @ weighted_line_residual
        + alpha
        * problem.delta_continuum_time
        * np.log(continuum / continuum_default)
    )
    gradient_transfer = (
        jacobian_transfer.T @ weighted_line_residual
        + alpha
        * stiffness_weight
        * problem.delta_tau
        * np.log(transfer / transfer_default)
    )
    gradient_line_background = float(np.sum(weighted_line_residual))

    log_gradient = np.r_[
        continuum * gradient_continuum,
        transfer * gradient_transfer,
        line_background * gradient_line_background,
    ]
    return float(objective), np.asarray(log_gradient, dtype=float)


def _evaluate_solution(
    problem: JointEchoProblem,
    continuum: FloatArray,
    transfer: FloatArray,
    line_background: float,
    continuum_default: FloatArray,
    transfer_default: FloatArray,
    alpha: float,
    stiffness_weight: float,
) -> dict[str, float | FloatArray]:
    continuum_model, line_model, _, _ = predict_joint_echo(
        problem, continuum, transfer, line_background
    )
    chi_continuum = float(
        np.sum(((continuum_model - problem.continuum_observed) / problem.continuum_errors) ** 2)
    )
    chi_line = float(
        np.sum(((line_model - problem.line_observed) / problem.line_errors) ** 2)
    )
    entropy_continuum = relative_entropy(
        continuum, continuum_default, problem.delta_continuum_time
    )
    entropy_transfer = relative_entropy(transfer, transfer_default, problem.delta_tau)
    objective = 0.5 * (chi_continuum + chi_line) - alpha * (
        entropy_continuum + stiffness_weight * entropy_transfer
    )
    return {
        "continuum_model": continuum_model,
        "line_model": line_model,
        "chi_square_continuum": chi_continuum,
        "chi_square_line": chi_line,
        "entropy_continuum": entropy_continuum,
        "entropy_transfer": entropy_transfer,
        "objective": objective,
    }


def fit_joint_maximum_entropy(
    problem: JointEchoProblem,
    initial_continuum: FloatArray,
    initial_transfer: FloatArray,
    initial_line_background: float,
    alpha: float,
    stiffness_weight: float = 1.0,
    default_mode: DefaultMode = "curvature",
    continuum_default: FloatArray | None = None,
    transfer_default: FloatArray | None = None,
    options: JointMemOptions | None = None,
) -> JointMemResult:
    """求解一次固定 alpha 的联合最大熵问题。"""
    options = options or JointMemOptions()
    continuum = np.asarray(initial_continuum, dtype=float).copy()
    transfer = np.asarray(initial_transfer, dtype=float).copy()
    line_background = float(initial_line_background)
    if continuum.shape != problem.continuum_grid_times.shape:
        raise ValueError("连续谱初值与连续谱网格形状不一致")
    if transfer.shape != problem.delays.shape:
        raise ValueError("转移函数初值与延迟网格形状不一致")
    if default_mode not in {"fixed", "curvature"}:
        raise ValueError(f"未知默认图像模式: {default_mode}")

    floor = options.positivity_floor
    continuum = np.maximum(continuum, floor)
    transfer = np.maximum(transfer, floor)
    line_background = max(line_background, floor)
    q_continuum = np.maximum(
        continuum if continuum_default is None else np.asarray(continuum_default, dtype=float),
        floor,
    )
    q_transfer = np.maximum(
        transfer if transfer_default is None else np.asarray(transfer_default, dtype=float),
        floor,
    )
    if q_continuum.shape != continuum.shape or q_transfer.shape != transfer.shape:
        raise ValueError("默认图像与对应的当前图像形状不一致")

    log_parameters = pack_log_parameters(continuum, transfer, line_background)
    lower_bound = float(np.log(floor))
    bounds = [(lower_bound, 30.0)] * log_parameters.size
    history_rows: list[dict[str, float | int]] = []
    total_iterations = 0
    success = False
    message = "尚未开始优化"
    final_scaled_gradient_norm = float("inf")
    outer_limit = 1 if default_mode == "fixed" else options.maximum_outer_iterations

    for outer_iteration in range(1, outer_limit + 1):
        iteration_in_outer = 0

        def objective(parameters: FloatArray) -> tuple[float, FloatArray]:
            return joint_objective_and_gradient(
                parameters,
                problem,
                q_continuum,
                q_transfer,
                alpha,
                stiffness_weight,
            )

        def callback(intermediate_result) -> None:
            nonlocal iteration_in_outer
            iteration_in_outer += 1
            if iteration_in_outer % options.history_stride != 0:
                return
            parameters = np.asarray(intermediate_result.x, dtype=float)
            value, gradient = objective(parameters)
            current_continuum, current_transfer, current_background = unpack_log_parameters(
                parameters,
                problem.continuum_grid_times.size,
                problem.delays.size,
            )
            evaluated = _evaluate_solution(
                problem,
                current_continuum,
                current_transfer,
                current_background,
                q_continuum,
                q_transfer,
                alpha,
                stiffness_weight,
            )
            history_rows.append(
                {
                    "outer_iteration": outer_iteration,
                    "iteration_in_outer": iteration_in_outer,
                    "objective_F": value,
                    "chi_square_continuum": evaluated["chi_square_continuum"],
                    "chi_square_line": evaluated["chi_square_line"],
                    "entropy_continuum": evaluated["entropy_continuum"],
                    "entropy_transfer": evaluated["entropy_transfer"],
                    "scaled_gradient_norm": float(np.linalg.norm(gradient)),
                }
            )

        optimization = minimize(
            objective,
            log_parameters,
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            callback=callback,
            options={
                "maxiter": options.max_iterations,
                "gtol": options.gradient_tolerance,
                "ftol": options.function_tolerance,
                "maxls": 50,
            },
        )
        total_iterations += int(optimization.nit)
        log_parameters = np.asarray(optimization.x, dtype=float)
        continuum, transfer, line_background = unpack_log_parameters(
            log_parameters,
            problem.continuum_grid_times.size,
            problem.delays.size,
        )
        _, final_gradient = objective(log_parameters)
        final_scaled_gradient_norm = float(np.linalg.norm(final_gradient))
        success = bool(optimization.success)
        message = str(optimization.message)

        if default_mode == "fixed":
            break
        next_q_continuum = curvature_default(continuum, floor)
        next_q_transfer = curvature_default(transfer, floor)
        default_change = max(
            float(np.max(np.abs(np.log(next_q_continuum / q_continuum)))),
            float(np.max(np.abs(np.log(next_q_transfer / q_transfer)))),
        )
        q_continuum = next_q_continuum
        q_transfer = next_q_transfer
        if default_change <= options.default_tolerance:
            message = f"曲率默认图像达到容差；最后一次内层状态: {message}"
            break

    evaluated = _evaluate_solution(
        problem,
        continuum,
        transfer,
        line_background,
        q_continuum,
        q_transfer,
        alpha,
        stiffness_weight,
    )
    history = pd.DataFrame(history_rows)
    return JointMemResult(
        continuum=np.asarray(continuum, dtype=float),
        transfer_function=np.asarray(transfer, dtype=float),
        line_background=float(line_background),
        continuum_model_at_observations=np.asarray(evaluated["continuum_model"], dtype=float),
        line_model=np.asarray(evaluated["line_model"], dtype=float),
        chi_square_continuum=float(evaluated["chi_square_continuum"]),
        chi_square_line=float(evaluated["chi_square_line"]),
        entropy_continuum=float(evaluated["entropy_continuum"]),
        entropy_transfer=float(evaluated["entropy_transfer"]),
        objective=float(evaluated["objective"]),
        alpha=float(alpha),
        stiffness_weight=float(stiffness_weight),
        success=success,
        message=message,
        iterations=total_iterations,
        outer_iterations=outer_iteration,
        scaled_gradient_norm=final_scaled_gradient_norm,
        history=history,
    )


def fit_joint_maximum_entropy_equalized(
    problem: JointEchoProblem,
    initial_continuum: FloatArray,
    initial_transfer: FloatArray,
    initial_line_background: float,
    alpha: float,
    stiffness_weight: float = 1.0,
    default_mode: DefaultMode = "curvature",
    options: JointMemOptions | None = None,
    initial_continuum_error_scale: float = 1.0,
    initial_line_error_scale: float = 1.0,
) -> JointMemResult:
    """迭代调整两组误差权重，使其每点 chi-square 大致相等。

    这是对论文 2.4 节经验性 ``chi-square equalization`` 的显式实现。
    返回的 chi-square 使用均衡后的有效误差；原始误差始终保留在 ``problem`` 中。
    """
    options = options or JointMemOptions()
    continuum_error_scale = float(initial_continuum_error_scale)
    line_error_scale = float(initial_line_error_scale)
    if continuum_error_scale <= 0 or line_error_scale <= 0:
        raise ValueError("两组误差缩放因子必须为正")

    continuum = np.asarray(initial_continuum, dtype=float)
    transfer = np.asarray(initial_transfer, dtype=float)
    line_background = float(initial_line_background)
    result: JointMemResult | None = None
    raw_chi_square_continuum = float("nan")
    raw_chi_square_line = float("nan")
    for equalization_iteration in range(
        1, options.maximum_equalization_iterations + 1
    ):
        scaled_problem = replace(
            problem,
            continuum_errors=problem.continuum_errors * continuum_error_scale,
            line_errors=problem.line_errors * line_error_scale,
        )
        result = fit_joint_maximum_entropy(
            problem=scaled_problem,
            initial_continuum=continuum,
            initial_transfer=transfer,
            initial_line_background=line_background,
            alpha=alpha,
            stiffness_weight=stiffness_weight,
            default_mode=default_mode,
            options=options,
        )
        continuum = result.continuum
        transfer = result.transfer_function
        line_background = result.line_background
        raw_chi_square_continuum = float(
            np.sum(
                (
                    (result.continuum_model_at_observations - problem.continuum_observed)
                    / problem.continuum_errors
                )
                ** 2
            )
        )
        raw_chi_square_line = float(
            np.sum(((result.line_model - problem.line_observed) / problem.line_errors) ** 2)
        )
        reduced_continuum = raw_chi_square_continuum / problem.continuum_observed.size
        reduced_line = raw_chi_square_line / problem.line_observed.size
        common_reduced = (
            raw_chi_square_continuum + raw_chi_square_line
        ) / problem.number_of_data
        imbalance = abs(np.log(max(reduced_continuum, 1e-15) / max(reduced_line, 1e-15)))
        if imbalance <= options.equalization_tolerance:
            break

        if equalization_iteration == options.maximum_equalization_iterations:
            break
        next_continuum_error_scale = float(
            np.clip(
                continuum_error_scale
                * np.sqrt(
                    max(common_reduced, 1e-15) / max(reduced_continuum, 1e-15)
                ),
                options.minimum_error_scale,
                options.maximum_error_scale,
            )
        )
        next_line_error_scale = float(
            np.clip(
                line_error_scale
                * np.sqrt(max(common_reduced, 1e-15) / max(reduced_line, 1e-15)),
                options.minimum_error_scale,
                options.maximum_error_scale,
            )
        )
        if np.isclose(next_continuum_error_scale, continuum_error_scale) and np.isclose(
            next_line_error_scale, line_error_scale
        ):
            break
        continuum_error_scale = next_continuum_error_scale
        line_error_scale = next_line_error_scale

    if result is None:
        raise RuntimeError("chi-square 均衡没有执行")
    return replace(
        result,
        chi_square_continuum=raw_chi_square_continuum,
        chi_square_line=raw_chi_square_line,
        continuum_error_scale=continuum_error_scale,
        line_error_scale=line_error_scale,
        equalization_iterations=equalization_iteration,
        effective_chi_square_continuum=result.chi_square_continuum,
        effective_chi_square_line=result.chi_square_line,
    )


def fit_to_chi_square_target(
    problem: JointEchoProblem,
    initial_continuum: FloatArray,
    initial_transfer: FloatArray,
    initial_line_background: float,
    alphas: FloatArray,
    target_chi_square_per_datum: float = 1.0,
    stiffness_weight: float = 1.0,
    default_mode: DefaultMode = "curvature",
    options: JointMemOptions | None = None,
    equalize_blocks: bool = True,
) -> JointMemPathResult:
    """沿 alpha 路径求解，并选择最接近 Horne 的 Caim 目标的结果。"""
    alpha_values = np.asarray(alphas, dtype=float)
    if alpha_values.ndim != 1 or alpha_values.size == 0 or np.any(alpha_values <= 0):
        raise ValueError("alpha 路径必须是一组正数")
    if target_chi_square_per_datum <= 0:
        raise ValueError("Caim 必须为正")

    candidates: list[JointMemResult] = []
    continuum = np.asarray(initial_continuum, dtype=float)
    transfer = np.asarray(initial_transfer, dtype=float)
    line_background = float(initial_line_background)
    continuum_error_scale = 1.0
    line_error_scale = 1.0
    for alpha in sorted(alpha_values, reverse=True):
        if equalize_blocks:
            result = fit_joint_maximum_entropy_equalized(
                problem=problem,
                initial_continuum=continuum,
                initial_transfer=transfer,
                initial_line_background=line_background,
                alpha=float(alpha),
                stiffness_weight=stiffness_weight,
                default_mode=default_mode,
                options=options,
                initial_continuum_error_scale=continuum_error_scale,
                initial_line_error_scale=line_error_scale,
            )
        else:
            result = fit_joint_maximum_entropy(
                problem=problem,
                initial_continuum=continuum,
                initial_transfer=transfer,
                initial_line_background=line_background,
                alpha=float(alpha),
                stiffness_weight=stiffness_weight,
                default_mode=default_mode,
                options=options,
            )
        candidates.append(result)
        continuum = result.continuum
        transfer = result.transfer_function
        line_background = result.line_background
        continuum_error_scale = result.continuum_error_scale
        line_error_scale = result.line_error_scale

    selected_index = int(
        np.argmin(
            [
                abs(np.log(result.chi_square_per_datum / target_chi_square_per_datum))
                for result in candidates
            ]
        )
    )
    rows = []
    for index, result in enumerate(candidates):
        rows.append(
            {
                "alpha": result.alpha,
                "chi_square_per_datum": result.chi_square_per_datum,
                "chi_square_continuum_per_datum": result.chi_square_continuum
                / problem.continuum_observed.size,
                "chi_square_line_per_datum": result.chi_square_line / problem.line_observed.size,
                "effective_chi_square_continuum_per_datum": (
                    result.effective_chi_square_continuum
                    if result.effective_chi_square_continuum is not None
                    else result.chi_square_continuum
                )
                / problem.continuum_observed.size,
                "effective_chi_square_line_per_datum": (
                    result.effective_chi_square_line
                    if result.effective_chi_square_line is not None
                    else result.chi_square_line
                )
                / problem.line_observed.size,
                "entropy_continuum": result.entropy_continuum,
                "entropy_transfer": result.entropy_transfer,
                "objective_F": result.objective,
                "iterations": result.iterations,
                "continuum_error_scale": result.continuum_error_scale,
                "line_error_scale": result.line_error_scale,
                "equalization_iterations": result.equalization_iterations,
                "success": result.success,
                "selected": index == selected_index,
            }
        )
    return JointMemPathResult(
        selected=candidates[selected_index],
        candidates=tuple(candidates),
        summary=pd.DataFrame(rows),
        target_chi_square_per_datum=float(target_chi_square_per_datum),
    )
