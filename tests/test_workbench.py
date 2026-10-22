import copy
import json
from pathlib import Path

import numpy as np
import pytest

from blr_rm.config import defaults, read_config, resolved_solver, solver_defaults, legacy_solver_defaults, validate_config
from blr_rm.data import batch_generate, generate, simulate, validate_observations
from blr_rm.detector import (
    independent_objective_gradient,
    independent_prediction,
    inspect_dataset,
    inspect_result,
)
from blr_rm.scan import scan
from blr_rm.solver import load_observations, optimize
from blr_rm.storage import load_arrays, read_json, sha256


@pytest.mark.parametrize("dimension", [1, 2])
def test_exact_noiseless_identity_and_independent_forward(tmp_path, dimension):
    path = generate(defaults(dimension), tmp_path / "case", plots=False)
    report = inspect_dataset(path)
    assert report["noiseless_identity"] == "PASS"
    assert report["generator_forward_relative_error"] < 1e-14
    assert report["true_area"] == pytest.approx(1)
    assert np.all(load_arrays(path / "observations.npz")["c_sigma"] == 0)


def test_analytic_impulse_uses_physical_zero_lag_and_nonunit_spacing():
    t_c = np.arange(-2, 3.5, 0.5)
    t_l = np.arange(0, 2.5, 0.5)
    obs = {"t_c": t_c, "t_l": t_l, "delays": np.array([0, 0.5, 1])}
    continuum = 10 + t_c**2
    prediction = independent_prediction(obs, continuum, np.array([[0.0, 2.0, 0.0]]), np.array([5.0]), 10)
    np.testing.assert_allclose(prediction[0], 5 + (t_l - 0.5) ** 2, rtol=0, atol=1e-14)
    zero = independent_prediction(obs, continuum, np.array([[2.0, 0.0, 0.0]]), np.array([5.0]), 10)
    np.testing.assert_allclose(zero[0], 5 + t_l**2, rtol=0, atol=1e-14)


@pytest.mark.parametrize("dimension", [1, 2])
def test_independent_random_streams_and_reproducibility(dimension):
    cfg = {**defaults(dimension), "noise_fraction": 0.05}
    first, truth_first = simulate(cfg)
    second, truth_second = simulate(cfg)
    for key in first:
        np.testing.assert_array_equal(first[key], second[key])
    for key in truth_first:
        np.testing.assert_array_equal(truth_first[key], truth_second[key])
    changed, truth_changed = simulate({**cfg, "noise_fraction": 0.10, "missing_fraction": 0.15})
    for key in truth_first:
        np.testing.assert_array_equal(truth_first[key], truth_changed[key])
    np.testing.assert_allclose(
        (first["c_obs"] - truth_first["c_true"]) / first["c_sigma"],
        (changed["c_obs"] - truth_first["c_true"]) / changed["c_sigma"],
        atol=2e-13,
    )


@pytest.mark.parametrize(
    "bad_key,bad_value",
    [
        ("noise_fraction", -0.01),
        ("cadence_days", 0),
        ("n_velocity", 2.5),
        ("seed", True),
        ("psd_beta", float("nan")),
    ],
)
def test_invalid_config_is_rejected(bad_key, bad_value):
    cfg = {**defaults(2), bad_key: bad_value}
    with pytest.raises(ValueError):
        validate_config(cfg)


def test_unknown_keys_and_fractional_budget_are_rejected(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"dimensoin": 2}))
    with pytest.raises(ValueError, match="未识别"):
        read_config(path)
    with pytest.raises(ValueError):
        resolved_solver(2, {"coordinate_cycles": 1.5})


@pytest.mark.parametrize(
    "corruption", ["nan", "negative_sigma", "time_order", "out_of_range", "wrong_axis", "no_observations"]
)
def test_bad_observation_arrays_are_rejected(corruption):
    obs, _ = simulate(defaults(2))
    if corruption == "nan":
        obs["c_obs"][0] = np.nan
    elif corruption == "negative_sigma":
        obs["l_sigma"][0, 0] = -1
    elif corruption == "time_order":
        obs["t_c"][1] = obs["t_c"][0]
    elif corruption == "out_of_range":
        obs["t_l"] += 100
    elif corruption == "wrong_axis":
        obs["l_obs"] = obs["l_obs"].T
    else:
        obs["time_mask"][:] = False
    with pytest.raises(ValueError):
        validate_observations(obs, 2)


@pytest.fixture
def noisy_case(tmp_path):
    return generate({**defaults(1), "noise_fraction": 0.05}, tmp_path / "dataset", plots=False)


def test_noiseless_fit_requires_explicit_weight_assumption(tmp_path):
    path = generate(defaults(1), tmp_path / "clean", plots=False)
    with pytest.raises(ValueError, match="error-floor"):
        optimize(path, tmp_path / "bad_fit")
    assert not (tmp_path / "bad_fit").exists()
    optimize(path, tmp_path / "explicit_fit", error_floor=(0.05, 0.03))
    assert read_json(tmp_path / "explicit_fit/result.json")["error_floor"] == [0.05, 0.03]


def test_optimizer_never_opens_truth(noisy_case, tmp_path, monkeypatch):
    original_load = np.load
    original_open = Path.open

    def protected_load(file, *args, **kwargs):
        assert "truth.npz" not in str(file), "优化器读取了真值"
        return original_load(file, *args, **kwargs)

    def protected_open(path, *args, **kwargs):
        assert path.name != "truth.npz", "优化器校验了真值"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(np, "load", protected_load)
    monkeypatch.setattr(Path, "open", protected_open)
    checked = optimize(noisy_case, tmp_path / "fit")
    assert checked["checks"]["forward_consistency"] == "PASS"
    assert "truth_metrics" not in checked


def test_scaled_1d_fit_converges_and_is_checked_independently(noisy_case, tmp_path):
    result = tmp_path / "fit"
    checked = optimize(noisy_case, result)
    assert checked["checks"]["numerical_convergence"] == "PASS"
    full = inspect_result(noisy_case, result)
    assert full["truth_metrics"]["shape_nmse"] < 0.1
    assert abs(full["truth_metrics"]["lag_centroid_error_days"]) < 0.3
    diag = read_json(result / "diagnostics.json")
    assert full["independent_numerics"]["objective_F"] == pytest.approx(diag["objective_F"], rel=1e-11)


def test_early_stop_is_not_reported_as_numerical_success(noisy_case, tmp_path):
    checked = optimize(noisy_case, tmp_path / "fit", {**legacy_solver_defaults(1), "max_iterations": 1})
    assert checked["checks"]["numerical_convergence"] == "FAIL"
    assert not checked["optimizer_success"]


def test_observation_tamper_is_detected(noisy_case):
    with (noisy_case / "observations.npz").open("ab") as stream:
        stream.write(b"unexpected bytes")
    with pytest.raises(ValueError, match="哈希"):
        load_observations(noisy_case)


def test_wrong_result_identity_is_rejected(noisy_case, tmp_path):
    result = tmp_path / "fit"
    optimize(noisy_case, result)
    other = generate({**defaults(1), "seed": 999, "noise_fraction": 0.05}, tmp_path / "other", plots=False)
    with pytest.raises(ValueError, match="不匹配"):
        inspect_result(other, result)


def test_forged_predictions_fail_even_with_updated_file_hash(noisy_case, tmp_path):
    result = tmp_path / "fit"
    optimize(noisy_case, result)
    solution = load_arrays(result / "solution.npz")
    solution["l_pred"] += 0.5
    with (result / "solution.npz").open("wb") as stream:
        np.savez_compressed(stream, **solution)
    manifest = read_json(result / "result.json")
    manifest["files"]["solution.npz"] = sha256(result / "solution.npz")
    (result / "result.json").write_text(json.dumps(manifest))
    checked = inspect_result(noisy_case, result)
    assert checked["checks"]["integrity"] == "PASS"
    assert checked["checks"]["forward_consistency"] == "FAIL"


def test_batch_resume_preserves_identity_and_rejects_changed_protocol(tmp_path):
    cfg = defaults(2)
    result = batch_generate(cfg, 3, tmp_path / "batch")
    resumed = batch_generate(cfg, 3, tmp_path / "batch", resume=True)
    assert result == resumed
    assert len({row["observation_id"] for row in result["cases"]}) == 3
    with pytest.raises(ValueError):
        batch_generate({**cfg, "seed": 999}, 3, tmp_path / "batch", resume=True)


def test_scan_is_exhaustive_has_no_truth_and_never_selects_best(noisy_case, tmp_path):
    grid = {"alpha_map": [0.1, 0.2], "alpha_c": [600.0, 1200.0]}
    report = scan(noisy_case, tmp_path / "scan", grid)
    assert report["count"] == 4
    assert report["selection"] == "NONE_PURE_SCAN"
    assert all("truth_metrics" not in row["check"] for row in report["points"])
    assert scan(noisy_case, tmp_path / "scan", grid, resume=True) == report
    with pytest.raises(ValueError):
        scan(noisy_case, tmp_path / "bad_scan", {"stationarity_tolerance": [1e9]})


def _small_problem(dimension):
    cfg = {
        **defaults(dimension),
        "duration_days": 8.0,
        "delay_max_days": 3.0,
        "n_velocity": 1 if dimension == 1 else 3,
        "noise_fraction": 0.05,
    }
    obs, _ = simulate(cfg)
    obs["time_mask"][3] = False
    meta = {"dimension": dimension, "c0": 10.0}
    nmap = (len(obs["velocities"]), len(obs["delays"]))
    solution = {
        "psi": np.full(nmap, 1 / np.prod(nmap)),
        "continuum": obs["c_obs"] * 1.005,
        "l_bg": np.full(nmap[0], 5.03),
        "default_map": np.full(nmap, 1 / np.prod(nmap)),
        "default_continuum": obs["c_obs"].copy(),
        "default_background": np.full(nmap[0], 5.0),
        "c_error_used": obs["c_sigma"],
        "l_error_used": obs["l_sigma"],
    }
    return meta, obs, solution


@pytest.mark.parametrize("dimension", [1, 2])
def test_independent_gradient_matches_finite_difference_all_parameter_blocks(dimension):
    meta, obs, state = _small_problem(dimension)
    cfg = solver_defaults(dimension)
    numerical, gradient = independent_objective_gradient(obs, state, cfg, meta["c0"], dimension)
    assert np.isfinite(numerical["objective_F"])
    point = np.r_[state["psi"].ravel(), state["continuum"], state["l_bg"]]

    def objective(x):
        trial = copy.deepcopy(state)
        nmap, nc = state["psi"].size, state["continuum"].size
        trial["psi"] = x[:nmap].reshape(state["psi"].shape)
        trial["continuum"] = x[nmap : nmap + nc]
        trial["l_bg"] = x[nmap + nc :]
        return independent_objective_gradient(obs, trial, cfg, meta["c0"], dimension)[0]["objective_F"]

    reference = np.empty_like(point)
    for index in range(len(point)):
        step = 1e-6 * max(1, abs(point[index]))
        plus, minus = point.copy(), point.copy()
        plus[index] += step
        minus[index] -= step
        reference[index] = (objective(plus) - objective(minus)) / (2 * step)
    np.testing.assert_allclose(gradient, reference, rtol=2e-6, atol=2e-5)


def test_scaled_coordinates_preserve_legacy_objective_and_chain_rule():
    from blr_rm._vendor.memecho import build_joint_echo_problem, joint_objective_and_gradient
    from blr_rm.scaled_1d import scaled_coordinates

    _, obs, _ = _small_problem(1)
    mask = obs["time_mask"]
    problem = build_joint_echo_problem(
        obs["t_c"],
        obs["delays"],
        obs["t_c"],
        obs["c_obs"],
        obs["c_sigma"],
        obs["t_l"][mask],
        obs["l_obs"][0, mask],
        obs["l_sigma"][0, mask],
        10.0,
    )
    c, p, bg = obs["c_obs"], np.full(len(obs["delays"]), 0.25), 5.0
    origin, scale, function = scaled_coordinates(problem, c, p, bg, 0.2, 1.0)
    z = np.random.default_rng(7).normal(size=len(origin)) * 0.1
    value, gradient = function(z)
    source_value, source_gradient = joint_objective_and_gradient(origin + scale * z, problem, c, p, 0.2, 1.0)
    assert value == source_value
    np.testing.assert_allclose(gradient, source_gradient * scale)
    direction = np.random.default_rng(8).normal(size=len(z))
    direction /= np.linalg.norm(direction)
    numerical = (function(z + 1e-5 * direction)[0] - function(z - 1e-5 * direction)[0]) / 2e-5
    assert gradient @ direction == pytest.approx(numerical, rel=1e-6, abs=1e-6)


def test_independent_2d_gradient_agrees_with_existing_production_objective():
    from blr_rm._vendor.mem2d import MEM2DProblem, entropy_positive

    meta, obs, state = _small_problem(2)
    cfg = legacy_solver_defaults(2)
    problem = MEM2DProblem(
        obs["t_c"],
        obs["c_obs"],
        obs["c_sigma"],
        obs["t_l"],
        obs["l_obs"],
        obs["l_sigma"],
        obs["velocities"],
        obs["delays"],
        obs["time_mask"],
        meta["c0"],
    )
    point = np.r_[state["psi"].ravel(), state["continuum"], state["l_bg"]]
    cc, cl, data_grads, _ = problem.chi2_grad(point)
    penalties, regularization_grads = [], []
    for value, default, alpha in (
        (state["psi"].ravel(), state["default_map"].ravel(), cfg["alpha_map"]),
        (state["continuum"], state["default_continuum"], cfg["alpha_c"]),
        (state["l_bg"], state["default_background"], cfg["alpha_lbg"]),
    ):
        entropy, gradient = entropy_positive(value, default)
        penalties.append(alpha * entropy)
        regularization_grads.append(-alpha * gradient)
    expected = np.concatenate([g + r for g, r in zip(data_grads, regularization_grads)])
    independent, gradient = independent_objective_gradient(obs, state, cfg, meta["c0"], 2)
    assert independent["objective_F"] == pytest.approx(cc + cl - sum(penalties), rel=1e-13)
    np.testing.assert_allclose(gradient, expected, rtol=1e-11, atol=1e-8)


def test_cli_propagates_numerical_scan_failure(noisy_case, tmp_path, capsys):
    from blr_rm.cli import main

    config = tmp_path / "short.json"
    config.write_text(json.dumps({**legacy_solver_defaults(1), "max_iterations": 1}))
    grid = tmp_path / "grid.json"
    grid.write_text(json.dumps({"alpha": [0.2]}))
    status = main(
        [
            "scan",
            "--data",
            str(noisy_case),
            "--config",
            str(config),
            "--grid",
            str(grid),
            "--out",
            str(tmp_path / "scan"),
        ]
    )
    assert status == 2
    assert "FAIL" in capsys.readouterr().out


def test_status_preserves_warning_without_turning_it_into_success():
    from blr_rm.status import has_failures, has_warnings

    report = {"checks": {"numerical_convergence": "PASS", "floating_default_stability": "WARN"}}
    assert not has_failures(report)
    assert has_warnings(report)
