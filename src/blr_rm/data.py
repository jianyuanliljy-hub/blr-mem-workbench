"""合成数据和版本化观测接口；优化器无需读取真值文件。"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .config import regular_grid, validate_config
from .storage import array_identity, environment, save_arrays, save_json, seal, verify

OBSERVATION_KEYS = {"t_c", "t_l", "delays", "velocities", "c_obs", "c_sigma", "l_obs", "l_sigma", "time_mask"}


def validate_observations(data: dict, dimension: int) -> None:
    if set(data) != OBSERVATION_KEYS:
        raise ValueError(f"观测字段不匹配: {sorted(set(data) ^ OBSERVATION_KEYS)}")
    for name, values in data.items():
        if not np.all(np.isfinite(values)):
            raise ValueError(f"{name} 包含 NaN 或 Inf")
    for name in ("t_c", "t_l", "delays"):
        values = data[name]
        if values.ndim != 1 or len(values) < 2 or np.any(np.diff(values) <= 0):
            raise ValueError(f"{name} 必须为严格递增的一维数组")
    for name in ("t_c", "delays"):
        spacing = np.diff(data[name])
        if not np.allclose(spacing, spacing[0], rtol=1e-9, atol=1e-12):
            raise ValueError(f"首版要求 {name} 等间隔；不允许静默重采样")
    nv, nt = len(data["velocities"]), len(data["t_l"])
    if dimension not in (1, 2) or (nv != 1 if dimension == 1 else nv < 2):
        raise ValueError("速度通道数量与维度不对应")
    if data["velocities"].ndim != 1 or (nv > 1 and np.any(np.diff(data["velocities"]) <= 0)):
        raise ValueError("速度坐标必须严格递增")
    for name in ("c_obs", "c_sigma"):
        if data[name].shape != data["t_c"].shape:
            raise ValueError(f"{name} 形状与连续谱时间不一致")
    for name in ("l_obs", "l_sigma"):
        if data[name].shape != (nv, nt):
            raise ValueError(f"{name} 必须为 [velocity,time]")
    if data["time_mask"].dtype.kind != "b" or data["time_mask"].shape != (nt,) or data["time_mask"].sum() < 3:
        raise ValueError("time_mask 必须为布尔 [time] 数组，且至少三个时刻有效")
    if np.any(data["c_sigma"] < 0) or np.any(data["l_sigma"] < 0):
        raise ValueError("测量标准差不得为负")
    if data["delays"][0] < 0:
        raise ValueError("因果模型不支持负时延")
    lo = data["t_l"][0] - data["delays"][-1]
    hi = data["t_l"][-1] - data["delays"][0]
    if lo < data["t_c"][0] - 1e-10 or hi > data["t_c"][-1] + 1e-10:
        raise ValueError("连续谱未覆盖全部 t_L-tau；禁止外推")


def forward_matrix(t_c, continuum, t_l, delays, c0):
    queries = np.asarray(t_l)[:, None] - np.asarray(delays)[None, :]
    if queries.min() < t_c[0] - 1e-10 or queries.max() > t_c[-1] + 1e-10:
        raise ValueError("连续谱不覆盖卷积查询")
    return np.interp(queries.ravel(), t_c, continuum).reshape(queries.shape) - c0


def _powerlaw_driver(n, dt, beta, rng):
    # 同时随机化傅里叶振幅和相位；这是有限长数值过程，未模拟红噪声泄漏。
    frequency = np.fft.rfftfreq(n, dt)
    power = np.zeros_like(frequency)
    power[1:] = frequency[1:] ** (-beta)
    coefficients = (rng.normal(size=len(frequency)) + 1j * rng.normal(size=len(frequency))) * np.sqrt(
        power / 2
    )
    coefficients[0] = 0
    if n % 2 == 0:
        coefficients[-1] = coefficients[-1].real
    values = np.fft.irfft(coefficients, n=n)
    if values.std() == 0:
        raise ValueError("连续谱方差为零")
    return (values - values.mean()) / values.std()


def _truth_map(cfg, delays, velocities, rng):
    tau = delays / cfg["delay_max_days"]
    center = rng.uniform(0.35, 0.65)
    width = rng.uniform(0.10, 0.18)
    if cfg["family"] == "top_hat":
        image = ((tau >= 0.3) & (tau <= 0.7)).astype(float)[None, :]
    elif cfg["family"] == "double_gaussian":
        image = (
            0.55 * np.exp(-0.5 * ((tau - 0.3) / 0.09) ** 2) + 0.45 * np.exp(-0.5 * ((tau - 0.7) / 0.12) ** 2)
        )[None, :]
    else:
        image = np.exp(-0.5 * ((tau - center) / width) ** 2)[None, :]
    if cfg["dimension"] == 2:
        v = velocities / cfg["velocity_max_kms"]
        if cfg["family"] == "tilted_gaussian":
            slope = rng.uniform(-0.20, 0.20)
            image = np.exp(
                -0.5 * ((tau[None, :] - center - slope * v[:, None]) / width) ** 2
                - 0.5 * (v[:, None] / 0.55) ** 2
            )
        elif cfg["family"] == "two_blobs":
            image = np.exp(
                -0.5 * ((tau[None, :] - 0.3) / 0.10) ** 2 - 0.5 * ((v[:, None] + 0.4) / 0.20) ** 2
            ) + 0.7 * np.exp(
                -0.5 * ((tau[None, :] - 0.7) / 0.12) ** 2 - 0.5 * ((v[:, None] - 0.4) / 0.25) ** 2
            )
        else:
            image = image * np.exp(-0.5 * (v[:, None] / 0.55) ** 2)
    return image / (image.sum() * cfg["delay_step_days"])


def simulate(cfg: dict) -> tuple[dict, dict]:
    validate_config(cfg)
    t_c = regular_grid(-cfg["delay_max_days"], cfg["duration_days"], cfg["cadence_days"])
    t_l = regular_grid(0, cfg["duration_days"], cfg["cadence_days"])
    delays = regular_grid(0, cfg["delay_max_days"], cfg["delay_step_days"])
    velocities = (
        np.zeros(1)
        if cfg["dimension"] == 1
        else np.linspace(-cfg["velocity_max_kms"], cfg["velocity_max_kms"], cfg["n_velocity"])
    )
    if len(t_c) * len(t_l) * len(delays) * 8 > 512 * 1024**2:
        raise ValueError("既有联合求解器的密集插值算子预计超过 512 MiB；请显式调整配置或使用专门的大网格实现")
    streams = [
        np.random.default_rng(np.random.SeedSequence([cfg["seed"], key])) for key in (101, 201, 202, 301, 401)
    ]
    c0 = cfg["continuum_background"]
    c_true = c0 + _powerlaw_driver(len(t_c), cfg["cadence_days"], cfg["psd_beta"], streams[0])
    if c_true.min() <= 0:
        raise ValueError("该模拟产生非正连续谱；请显式提高背景，程序不会裁剪真值")
    psi = _truth_map(cfg, delays, velocities, streams[4])
    l_bg = np.full(len(velocities), cfg["line_background"])
    response = forward_matrix(t_c, c_true, t_l, delays, c0)
    l_true = psi @ response.T * cfg["delay_step_days"] + l_bg[:, None]
    noise = cfg["noise_fraction"]
    c_sigma = np.full_like(c_true, noise * np.std(c_true - c0))
    l_sigma = np.full_like(l_true, noise * max(np.sqrt(np.mean((l_true - l_bg[:, None]) ** 2)), 1e-12))
    c_obs = c_true + streams[1].normal(size=c_true.shape) * c_sigma
    l_obs = l_true + streams[2].normal(size=l_true.shape) * l_sigma
    mask = np.ones(len(t_l), dtype=bool)
    missing = round(cfg["missing_fraction"] * len(mask))
    if missing:
        mask[streams[3].choice(len(mask), missing, replace=False)] = False
    obs = {
        "t_c": t_c,
        "t_l": t_l,
        "delays": delays,
        "velocities": velocities,
        "c_obs": c_obs,
        "c_sigma": c_sigma,
        "l_obs": l_obs,
        "l_sigma": l_sigma,
        "time_mask": mask,
    }
    truth = {"c_true": c_true, "l_true": l_true, "psi_true": psi, "l_bg_true": l_bg}
    validate_observations(obs, cfg["dimension"])
    return obs, truth


def generate(cfg: dict, output: str | Path, plots: bool = True) -> Path:
    obs, truth = simulate(cfg)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    save_arrays(output / "observations.npz", obs)
    save_arrays(output / "truth.npz", truth)
    if plots:
        from .report import plot_dataset

        plot_dataset(obs, truth, output / "truth.png")
    seal(
        output,
        "dataset.json",
        {
            "schema_version": 1,
            "kind": "simulation",
            "dimension": cfg["dimension"],
            "config": cfg,
            "c0": cfg["continuum_background"],
            "observation_id": array_identity(obs),
            "truth_id": array_identity(truth),
            "units": {
                "time": "day",
                "velocity": "km/s",
                "psi": "day^-1 per velocity bin",
                "flux": "arbitrary",
            },
            "map_representation": "velocity-bin-integrated response; sum(Psi)*d_tau=1 for generated truth",
            "array_axes": {"psi": ["velocity", "delay"], "line": ["velocity", "time"]},
            "noise_definition": "sigma_C=f*std(C_true-C0); sigma_L=f*RMS(L_true-L_bg); independent Gaussian",
            "environment": environment(),
        },
    )
    return output


def batch_generate(cfg: dict, count: int, output: str | Path, resume: bool = False) -> dict:
    validate_config(cfg)
    if not isinstance(count, int) or not 1 <= count <= 100000:
        raise ValueError("count 必须为 1..100000 的整数")
    output = Path(output)
    generator_environment = environment()
    if resume:
        previous = verify(output, "batch.json")
        if previous["config"] != cfg or previous["count"] != count:
            raise ValueError("续跑配置或数量与原批次不一致")
        if previous["environment"]["source_sha256"] != generator_environment["source_sha256"]:
            raise ValueError("代码已变化；不能混入原批次")
    else:
        output.mkdir(parents=True, exist_ok=False)
        save_json(
            output / "batch.json",
            {
                "schema_version": 1,
                "config": cfg,
                "count": count,
                "environment": generator_environment,
                "files": {},
            },
        )
    rows = []
    for index in range(count):
        case_cfg = {**cfg, "seed": cfg["seed"] + index}
        case = output / f"case_{index:06d}"
        if case.exists():
            meta = verify(case, "dataset.json")
            if not resume or meta["config"] != case_cfg:
                raise ValueError(f"已有输出与当前批次不一致: {case.name}")
        else:
            generate(case_cfg, case, plots=False)
            meta = verify(case, "dataset.json")
        rows.append({"case": case.name, "seed": case_cfg["seed"], "observation_id": meta["observation_id"]})
    receipt = {"schema_version": 1, "count": count, "cases": rows}
    # 完成收据采用独立新文件，避免覆盖原批次或已有结果。
    if not (output / "complete.json").exists():
        save_json(output / "complete.json", receipt)
    return receipt
