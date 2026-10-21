"""既有联合 MEM 的观测适配层；真值仅由独立检测器读取。"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from ._vendor.mem2d import MEM2DProblem, reconstruct_mem2d
from ._vendor.memecho import build_joint_echo_problem
from .config import resolved_solver
from .data import validate_observations
from .scaled_1d import fit_scaled_1d
from .storage import array_identity, environment, load_arrays, save_arrays, save_json, seal, sha256, verify


def load_observations(dataset: str | Path) -> tuple[dict, dict]:
    dataset = Path(dataset)
    # 指定文件白名单，避免在优化阶段读取或校验 truth.npz。
    meta = verify(dataset, "dataset.json", names=("observations.npz",))
    obs = load_arrays(dataset / "observations.npz")
    validate_observations(obs, meta["dimension"])
    if not np.isfinite(meta["c0"]) or meta["c0"] <= 0:
        raise ValueError("C0 必须是有限正数")
    if meta["observation_id"] != array_identity(obs):
        raise ValueError("观测数组身份不匹配")
    nc, nt, nk = len(obs["t_c"]), len(obs["t_l"]), len(obs["delays"])
    if nc * nt * nk * 8 > 512 * 1024**2:
        raise ValueError("当前密集插值算子预计超过 512 MiB；禁止隐式降低科学网格")
    return meta, obs


def effective_errors(obs: dict, error_floor: tuple[float, float] | None) -> tuple[np.ndarray, np.ndarray]:
    if error_floor is not None:
        if len(error_floor) != 2 or not all(np.isfinite(x) and x > 0 for x in error_floor):
            raise ValueError("error_floor 要求两个有限正数，单位分别为连续谱和发射线通量")
        return np.maximum(obs["c_sigma"], error_floor[0]), np.maximum(obs["l_sigma"], error_floor[1])
    if np.any(obs["c_sigma"] <= 0) or np.any(obs["l_sigma"][:, obs["time_mask"]] <= 0):
        raise ValueError(
            "无噪声数据的标准差为零。反演时必须显式指定 --error-floor C L；该值是拟合权重假设，会写入结果"
        )
    # 未观测时刻的零标准差不参与似然；采用已有正标准差填充，避免 0/0。
    line = obs["l_sigma"].copy()
    line[:, ~obs["time_mask"]] = np.maximum(line[:, ~obs["time_mask"]], np.min(line[:, obs["time_mask"]]))
    return obs["c_sigma"].copy(), line


def fit_arrays(meta: dict, obs: dict, cfg: dict, error_floor=None) -> tuple[dict, dict, list]:
    c_err, l_err = effective_errors(obs, error_floor)
    if np.any(obs["c_obs"] <= 0) or np.any(obs["l_obs"][:, obs["time_mask"]] <= 0):
        raise ValueError("既有正联合 MEM 要求观测通量为正；请检查背景/标定，程序不自动平移或裁剪数据")
    step = float(np.diff(obs["delays"])[0])
    dimension = meta["dimension"]
    if dimension == 1:
        mask = obs["time_mask"]
        problem = build_joint_echo_problem(
            obs["t_c"],
            obs["delays"],
            obs["t_c"],
            obs["c_obs"],
            c_err,
            obs["t_l"][mask],
            obs["l_obs"][0, mask],
            l_err[0, mask],
            meta["c0"],
        )
        initial_c = obs["c_obs"].copy()
        initial_psi = np.full(len(obs["delays"]), 1 / (len(obs["delays"]) * step))
        initial_bg = max(float(np.percentile(obs["l_obs"][0, mask], 10)), 1e-6)
        result = fit_scaled_1d(problem, initial_c, initial_psi, initial_bg, cfg)
        # 用真实坐标在全部时刻导出预测，包括被掩码的时刻。
        from .data import forward_matrix

        prediction = (
            result.transfer_function[None, :]
            @ forward_matrix(obs["t_c"], result.continuum, obs["t_l"], obs["delays"], meta["c0"]).T
            * step
            + result.line_background
        )
        arrays = {
            "psi": result.transfer_function[None, :],
            "continuum": result.continuum,
            "l_bg": np.array([result.line_background]),
            "l_pred": prediction,
            "default_map": initial_psi[None, :],
            "default_continuum": initial_c,
            "default_background": np.array([initial_bg]),
            "c_error_used": c_err,
            "l_error_used": l_err,
        }
        diag = {
            "optimizer_success": bool(result.success),
            "message": result.message,
            "iterations": result.iterations,
            "objective_F": result.objective,
            "objective_Q": -result.objective,
            "objective_convention": "0.5*(chi2_C+chi2_L)-alpha*(S_C+W*S_map); spacings included",
            "continuum_errors_rescaled": False,
            "defaults_updated": False,
            "numerical_change": "Diagonal Gauss-Newton scaling of log coordinates; identical MEM objective and defaults; ftol=1e-15 by default",
        }
        return arrays, diag, result.history.to_dict(orient="records")
    problem = MEM2DProblem(
        obs["t_c"],
        obs["c_obs"],
        c_err,
        obs["t_l"],
        obs["l_obs"],
        l_err,
        obs["velocities"],
        obs["delays"],
        obs["time_mask"],
        meta["c0"],
    )
    result = reconstruct_mem2d(problem, cfg)
    diag = dict(result.diagnostics)
    arrays = {
        "psi": result.psi,
        "continuum": result.continuum,
        "l_bg": result.l_bg,
        "l_pred": result.l_pred,
        "default_map": diag.pop("final_default_map"),
        "default_continuum": diag.pop("final_default_continuum"),
        "default_background": diag.pop("final_default_background"),
        "c_error_used": c_err,
        "l_error_used": l_err,
    }
    diag.update(
        optimizer_success=bool(result.success),
        objective_convention="chi2_C+chi2_L-alpha_map*S_map-alpha_c*S_C-alpha_lbg*S_bg; pixel sums",
        continuum_errors_rescaled=False,
        defaults_updated=True,
    )
    return arrays, diag, result.history


def optimize(
    dataset: str | Path,
    output: str | Path,
    overrides: dict | None = None,
    error_floor: tuple[float, float] | None = None,
) -> dict:
    started = time.perf_counter()
    meta, obs = load_observations(dataset)
    cfg = resolved_solver(meta["dimension"], overrides)
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"不覆盖已有结果: {output}")
    compute_start = time.perf_counter()
    arrays, diag, history = fit_arrays(meta, obs, cfg, error_floor)
    compute_seconds = time.perf_counter() - compute_start
    if any(not np.all(np.isfinite(value)) for value in arrays.values()):
        raise ValueError("求解器产生非有限数组；不能保存为可用结果")
    output.mkdir(parents=True, exist_ok=False)
    save_arrays(output / "solution.npz", arrays)
    save_json(output / "history.json", history)
    save_json(output / "diagnostics.json", diag)
    seal(
        output,
        "result.json",
        {
            "schema_version": 1,
            "dimension": meta["dimension"],
            "observation_id": meta["observation_id"],
            "input_sha256": sha256(Path(dataset) / "observations.npz"),
            "solver_config": cfg,
            "error_floor": list(error_floor) if error_floor else None,
            "compute_seconds": compute_seconds,
            "elapsed_before_seal_seconds": time.perf_counter() - started,
            "environment": environment(),
        },
    )
    from .detector import inspect_result

    return inspect_result(dataset, output, include_truth=False)
