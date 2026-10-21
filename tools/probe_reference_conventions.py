"""用独立小算例检查参考程序涉及的数学约定，不运行参考程序。

这些算例不能替代 Windows 实测或求解器对照，也不修改生成器、优化器、
评价指标和已有实验输出。没有从参考 EXE 导入任何模块。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    package = Path(__file__).resolve().parents[1]
    generator = json.loads((args.audit / "generator.json").read_text(encoding="utf-8"))
    solver = json.loads((args.audit / "solver.json").read_text(encoding="utf-8"))
    reference = generator["reviewed_modules"]["MEMECHO_Data_Generator"]["generator_gui_defaults"]
    gui = solver["reviewed_modules"]["MEMECHO_GUI"]["solver_gui_defaults"]

    # 旧 sum(Psi)=1 在非单位时延步长下不会给出单位积分。
    d_tau = (reference["delay_max_days"] - reference["delay_min_days"]) / (reference["true_delay_pixels"] - 1)
    image = np.full((reference["velocity_channels"], reference["true_delay_pixels"]), 1.0)
    image /= image.sum()
    legacy_integral = float(image.sum() * d_tau)
    unit_integral = float((image / d_tau).sum() * d_tau)
    assert np.isclose(legacy_integral, 40 / 99)
    assert np.isclose(unit_integral, 1)

    # 界面 S/N 参数的实际定义来自已审查的字节码，算例仅演示含义。
    example_c = np.array([0.5, 2.0, 4.0])
    example_sigma = np.sqrt(example_c) / reference["c_peak_sn"]
    pointwise_snr = example_c / example_sigma
    assert not np.allclose(pointwise_snr, reference["c_peak_sn"])

    # 有限窗口的 nearest 延拓可能使 G_L H 与 H G_C 不同；这里用自建函数示例。
    dt, sigma_days = 2.0, 2.0
    t_c = np.arange(-8.0, 44.0, dt)
    t_l = np.arange(0.0, 42.0, dt)
    delays = np.arange(0.0, 10.0, dt)
    response = np.array([0.05, 0.10, 0.15, 0.10, 0.10])
    intrinsic = np.sin(t_c / 5.0) + 0.02 * t_c**2

    def echo(values):
        values_at_delays = np.interp((t_l[:, None] - delays).ravel(), t_c, values)
        return values_at_delays.reshape(len(t_l), len(delays)) @ response * dt + 1.7

    broadened_line = gaussian_filter1d(echo(intrinsic), sigma_days / dt, mode="nearest")
    echo_of_broadened_c = echo(gaussian_filter1d(intrinsic, sigma_days / dt, mode="nearest"))
    differences = np.abs(broadened_line - echo_of_broadened_c)
    interior = (t_l >= 4 * sigma_days) & (t_l <= t_l[-1] - 4 * sigma_days)
    assert differences.max() > 1e-3
    assert differences[interior].max() < 1e-12

    protocol_path = package / "evidence/validation_20261021_v1/protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    frozen = protocol["environment"]["source_sha256"]
    names = ["config.py", "data.py", "solver.py", "detector.py", "scaled_1d.py"]
    names.extend(name for name in frozen if name.startswith("_vendor/") and name.endswith(".py"))
    source_checks = [
        {"path": name, "sha256": sha256(package / "src/blr_rm" / name), "matches_main_matrix": sha256(package / "src/blr_rm" / name) == frozen[name]}
        for name in sorted(names)
    ]
    assert all(item["matches_main_matrix"] for item in source_checks)
    receipt_path = args.audit / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert all(sha256(args.audit / name) == value for name, value in receipt["outputs"].items())
    result = {
        "schema_version": 1,
        "kind": "independent_convention_examples_not_reference_exe_execution",
        "script_sha256": sha256(Path(__file__)),
        "static_audit_receipt_sha256": sha256(receipt_path),
        "reference_exe_executed": False,
        "reference_solver_numerically_compared": False,
        "normalization_example": {
            "delay_step_days": d_tau,
            "legacy_sum_one_delay_integral": legacy_integral,
            "workbench_unit_integral_example": unit_integral,
            "calibration_response_default": reference["calibration_response"],
            "calibrated_reference_grid_peak_delay_integral_target": reference["peak_response_integral"],
            "scope": "Legacy sum-one illustration; the reference default uses peak-response calibration, not this legacy mode.",
        },
        "continuum_noise_example": {
            "gui_parameter": reference["c_peak_sn"],
            "flux": example_c.tolist(),
            "sigma": example_sigma.tolist(),
            "pointwise_flux_over_sigma": pointwise_snr.tolist(),
            "formula": "sigma_C=sqrt(C_true)/c_peak_sn",
        },
        "visible_delay_grids": {
            "generator_true_delay_pixels": reference["true_delay_pixels"],
            "solver_gui_delay_pixels": int(gui["basic"]["Delay pixels"]),
            "scope": "Different truth and inversion grids are allowed, but must be recorded for comparison.",
        },
        "finite_window_broadening_example": {
            "time_c": t_c.tolist(),
            "time_l": t_l.tolist(),
            "delays": delays.tolist(),
            "response": response.tolist(),
            "intrinsic_c": intrinsic.tolist(),
            "cadence_days": dt,
            "sigma_days": sigma_days,
            "boundary_mode": "nearest",
            "max_absolute_composition_difference": float(differences.max()),
            "max_absolute_interior_difference": float(differences[interior].max()),
            "scope": "Toy demonstration of finite-window operators; not an observed EXE residual or a scientific acceptance test.",
        },
        "scientific_sources_vs_existing_144_case_matrix": source_checks,
        "checks": {
            "normalization_example": "PASS",
            "noise_definition_example": "PASS",
            "broadening_boundary_example": "PASS",
            "scientific_source_identity": "PASS",
            "static_audit_file_integrity": "PASS",
        },
    }
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"checks": result["checks"], "boundary_max_difference": float(differences.max()), "interior_max_difference": float(differences[interior].max())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
