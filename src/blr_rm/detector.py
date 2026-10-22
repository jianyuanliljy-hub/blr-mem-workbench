"""独立重算前向模型、目标函数和一阶残差；禁止复用求解器预测函数。"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .solver import effective_errors, load_observations
from .storage import array_identity, load_arrays, read_json, sha256, verify


def independent_prediction(obs, continuum, psi, background, c0):
    """直接按物理坐标逐延迟累加，独立于生产矩阵乘法路径。"""
    step = float(obs["delays"][1] - obs["delays"][0])
    prediction = np.repeat(np.asarray(background)[:, None], len(obs["t_l"]), axis=1)
    for index, delay in enumerate(obs["delays"]):
        query = obs["t_l"] - delay
        if query.min() < obs["t_c"][0] - 1e-10 or query.max() > obs["t_c"][-1] + 1e-10:
            raise ValueError("检测到越界卷积")
        shifted = np.interp(query, obs["t_c"], continuum) - c0
        prediction += np.asarray(psi)[:, index, None] * shifted[None, :] * step
    return prediction


def _relative_error(first, second):
    return float(np.linalg.norm(first - second) / max(1.0, np.linalg.norm(first), np.linalg.norm(second)))


def recovery_metrics(psi, truth, delays, velocities):
    raw_nmse = float(np.sum((psi - truth) ** 2) / max(np.sum(truth**2), 1e-300))
    p, t = psi / psi.sum(), truth / truth.sum()
    p_tau, t_tau = p.sum(0), t.sum(0)
    p_v, t_v = p.sum(1), t.sum(1)
    return {
        "raw_nmse": raw_nmse,
        "shape_nmse": float(np.sum((p - t) ** 2) / np.sum(t**2)),
        "lag_centroid_error_days": float(p_tau @ delays - t_tau @ delays),
        "velocity_centroid_error_kms": float(p_v @ velocities - t_v @ velocities),
        "recovered_area": float(psi.sum() * (delays[1] - delays[0])),
        "true_area": float(truth.sum() * (delays[1] - delays[0])),
    }


def inspect_dataset(dataset: str | Path) -> dict:
    dataset = Path(dataset)
    meta, obs = load_observations(dataset)
    report = {
        "schema_version": 1,
        "observation_id": meta["observation_id"],
        "integrity": "PASS",
        "dimension": meta["dimension"],
        "truth_status": "UNAVAILABLE",
        "observed_epochs": int(obs["time_mask"].sum()),
    }
    if (dataset / "truth.npz").exists():
        verify(dataset, "dataset.json", names=("truth.npz",))
        truth = load_arrays(dataset / "truth.npz")
        expected_shapes = {
            "c_true": obs["c_obs"].shape,
            "l_true": obs["l_obs"].shape,
            "psi_true": (len(obs["velocities"]), len(obs["delays"])),
            "l_bg_true": obs["velocities"].shape,
        }
        if set(truth) != set(expected_shapes) or any(
            truth[key].shape != shape for key, shape in expected_shapes.items()
        ):
            raise ValueError("真值字段或数组形状不正确")
        if any(not np.isfinite(value).all() for value in truth.values()) or np.any(truth["psi_true"] < 0):
            raise ValueError("真值数组含非有限值或负响应")
        if meta.get("truth_id") != array_identity(truth):
            raise ValueError("真值数组身份不匹配")
        prediction = independent_prediction(
            obs, truth["c_true"], truth["psi_true"], truth["l_bg_true"], meta["c0"]
        )
        error = _relative_error(prediction, truth["l_true"])
        report.update(
            truth_status="AVAILABLE",
            generator_forward_relative_error=error,
            generator_forward="PASS" if error < 1e-11 else "FAIL",
            true_area=float(truth["psi_true"].sum() * np.diff(obs["delays"])[0]),
        )
        if meta.get("config", {}).get("noise_fraction") == 0:
            identical = np.array_equal(obs["c_obs"], truth["c_true"]) and np.array_equal(
                obs["l_obs"], truth["l_true"]
            )
            zero_sigma = not np.any(obs["c_sigma"]) and not np.any(obs["l_sigma"])
            report["noiseless_identity"] = "PASS" if identical and zero_sigma else "FAIL"
    return report


def _entropy(p, q, spacing=1):
    return float(np.sum(p - q - p * np.log(p / q)) * spacing)


def independent_objective_gradient(obs, solution, cfg, c0, dimension):
    """显式累加连续谱插值的伴随；包括所有参数块的相对熵导数。"""
    p, c, bg = solution["psi"], solution["continuum"], solution["l_bg"]
    qc, qp, qb = solution["default_continuum"], solution["default_map"], solution["default_background"]
    ec, el = solution["c_error_used"], solution["l_error_used"]
    predicted = independent_prediction(obs, c, p, bg, c0)
    line_weight = obs["time_mask"][None, :] / el**2
    residual = predicted - obs["l_obs"]
    chi_c = float(np.sum(((c - obs["c_obs"]) / ec) ** 2))
    chi_l = float(np.sum(residual**2 * line_weight))
    autumn = cfg['engine'] == 'autumn_normalized_joint_mem'
    factor = 2.0 if autumn or dimension == 2 else 1.0
    wr = factor * residual * line_weight / (p.shape[0]*obs['time_mask'].sum() if autumn else 1)
    gc_data = factor * (c - obs["c_obs"]) / ec**2 / (len(c) if autumn else 1)
    gp_data = np.zeros_like(p)
    gb_data = wr.sum(axis=1)
    step = float(np.diff(obs["delays"])[0])
    times = obs["t_c"]
    for j, delay in enumerate(obs["delays"]):
        query = obs["t_l"] - delay
        right = np.clip(np.searchsorted(times, query, side="right"), 1, len(times) - 1)
        left = right - 1
        fraction = (query - times[left]) / (times[right] - times[left])
        shifted = (1 - fraction) * c[left] + fraction * c[right] - c0
        gp_data[:, j] = wr @ shifted * step
        influence = (wr * p[:, j, None]).sum(axis=0) * step
        np.add.at(gc_data, left, influence * (1 - fraction))
        np.add.at(gc_data, right, influence * fraction)
    if autumn:
        weights = tuple(cfg[key]/np.sum(default) for key, default in
                        zip(('alpha_map', 'alpha_c', 'alpha_lbg'), (qp, qc, qb)))
        entropy = sum(a*_entropy(value, default) for a, value, default in
                      zip(weights, (p, c, bg), (qp, qc, qb)))
        objective = chi_c/len(c) + chi_l/(p.shape[0]*obs['time_mask'].sum()) - entropy
    elif dimension == 1:
        dc = float(times[1] - times[0])
        weights = (cfg["alpha"] * cfg["stiffness_weight"] * step, cfg["alpha"] * dc, 0.0)
        entropy = cfg["alpha"] * (_entropy(c, qc, dc) + cfg["stiffness_weight"] * _entropy(p, qp, step))
        objective = 0.5 * (chi_c + chi_l) - entropy
    else:
        weights = (cfg["alpha_map"], cfg["alpha_c"], cfg["alpha_lbg"])
        entropy = sum(
            a * _entropy(value, default) for a, value, default in zip(weights, (p, c, bg), (qp, qc, qb))
        )
        objective = chi_c + chi_l - entropy
    gradients, relative_blocks, tests = [], {}, {}
    for name, value, default, data_grad, weight in zip(
        ("map", "continuum", "background"), (p, c, bg), (qp, qc, qb), (gp_data, gc_data, gb_data), weights
    ):
        regularization = weight * np.log(value / default)
        full = data_grad + regularization
        gradients.append(full.ravel())
        active = value > 1e-8
        g, r = data_grad[active], regularization[active]
        relative_blocks[name] = float(
            np.linalg.norm(g + r) / max(np.linalg.norm(g), np.linalg.norm(r), 1e-14)
        )
        ng, nr = np.linalg.norm(g), np.linalg.norm(r)
        if ng < 1e-14 and nr < 1e-14:
            tests[name] = 0.0
        elif ng < 1e-14 or nr < 1e-14:
            tests[name] = 1.0
        else:
            tests[name] = float(1 + np.clip(np.dot(g, r) / (ng * nr), -1, 1))
    gradient = np.concatenate(gradients)
    parameters = np.concatenate([p.ravel(), c.ravel(), bg.ravel()])
    return {
        "objective_F": float(objective),
        "objective_Q": float(-objective),
        "chi2_C": chi_c,
        "chi2_L": chi_l,
        "chi2_C_per_datum": chi_c / len(c),
        "chi2_L_per_datum": chi_l / (p.shape[0] * obs["time_mask"].sum()),
        "log_gradient_inf": float(np.max(np.abs(gradient * parameters))),
        "relative_gradient_blocks": relative_blocks,
        "component_tests": tests,
    }, gradient


def inspect_result(dataset: str | Path, result: str | Path, include_truth: bool = True) -> dict:
    dataset, result = Path(dataset), Path(result)
    meta, obs = load_observations(dataset)
    run = verify(result, "result.json")
    if (
        run["dimension"] != meta["dimension"]
        or run["observation_id"] != meta["observation_id"]
        or run["input_sha256"] != sha256(dataset / "observations.npz")
    ):
        raise ValueError("结果与输入数据不匹配")
    solution = load_arrays(result / "solution.npz")
    shape_map = (len(obs["velocities"]), len(obs["delays"]))
    shapes = {
        "psi": shape_map,
        "continuum": obs["c_obs"].shape,
        "l_bg": obs["velocities"].shape,
        "l_pred": obs["l_obs"].shape,
        "default_map": shape_map,
        "default_continuum": obs["c_obs"].shape,
        "default_background": obs["velocities"].shape,
        "c_error_used": obs["c_obs"].shape,
        "l_error_used": obs["l_obs"].shape,
    }
    if set(solution) != set(shapes) or any(solution[name].shape != shape for name, shape in shapes.items()):
        raise ValueError("结果字段或数组形状不符合接口")
    if any(not np.isfinite(value).all() for value in solution.values()):
        raise ValueError("结果含 NaN/Inf")
    if any(np.any(value <= 0) for name, value in solution.items() if name != "l_pred"):
        raise ValueError("正性或误差标准差约束失败")
    expected_c, expected_l = effective_errors(obs, tuple(run["error_floor"]) if run["error_floor"] else None)
    if not np.array_equal(expected_c, solution["c_error_used"]) or not np.array_equal(
        expected_l, solution["l_error_used"]
    ):
        raise ValueError("结果使用的误差权重与输入/显式误差下限不一致")
    reference = independent_prediction(
        obs, solution["continuum"], solution["psi"], solution["l_bg"], meta["c0"]
    )
    forward_error = _relative_error(reference, solution["l_pred"])
    numerical, _ = independent_objective_gradient(
        obs, solution, run["solver_config"], meta["c0"], meta["dimension"]
    )
    diag = read_json(result / "diagnostics.json")
    if meta["dimension"] == 1 and run['solver_config']['engine'] != 'autumn_normalized_joint_mem':
        converged = (
            diag["optimizer_success"]
            and numerical["log_gradient_inf"] <= run["solver_config"]["stationarity_tolerance"]
        )
        stable = "NOT_APPLICABLE_FIXED_DEFAULT"
    else:
        cfg = run["solver_config"]
        converged = (
            diag["final_inner_converged"]
            and max(numerical["relative_gradient_blocks"].values()) <= cfg["q_gradient_threshold"]
            and max(numerical["component_tests"].values()) <= cfg["test_threshold"]
        )
        stable = "PASS" if diag["final_default_change"] <= cfg["default_change_tolerance"] else "WARN"
    checks = {
        "integrity": "PASS",
        "forward_consistency": "PASS" if forward_error < 1e-10 else "FAIL",
        "numerical_convergence": "PASS" if converged else "FAIL",
        "floating_default_stability": stable,
    }
    report = {
        "schema_version": 1,
        "observation_id": meta["observation_id"],
        "checks": checks,
        "forward_relative_error": forward_error,
        "independent_numerics": numerical,
        "optimizer_success": diag["optimizer_success"],
        "compute_seconds": run["compute_seconds"],
        "scientific_acceptance": "NOT_ASSESSED",
        "real_agn_validation": "NOT_RUN",
    }
    report["optimizer_history_warning"] = (
        "NONE"
        if diag["optimizer_success"]
        else "At least one optimizer call reported failure; final stationarity is assessed independently"
    )
    if include_truth and (dataset / "truth.npz").exists():
        truth_check = inspect_dataset(dataset)
        if (
            truth_check.get("generator_forward") != "PASS"
            or truth_check.get("noiseless_identity", "PASS") != "PASS"
        ):
            raise ValueError("生成真值未通过独立前向检测")
        truth = load_arrays(dataset / "truth.npz")
        report["truth_metrics"] = recovery_metrics(
            solution["psi"], truth["psi_true"], obs["delays"], obs["velocities"]
        )
    return report
