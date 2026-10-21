"""复核既有解，不重跑数值求解；生成汇总图和可公开的派生统计。"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from blr_rm.detector import inspect_dataset, inspect_result
from blr_rm.storage import sha256


def main():
    root = Path(__file__).resolve().parents[1]
    benchmark = root / "evidence/validation_20261021_v1"
    protocol = json.loads((benchmark / "protocol.json").read_text())
    summary = json.loads((benchmark / "summary.json").read_text())
    critical = [
        "config.py",
        "data.py",
        "detector.py",
        "solver.py",
        "scaled_1d.py",
        "benchmark.py",
        "_vendor/mem2d.py",
        "_vendor/memecho.py",
        "_vendor/interpolation.py",
    ]
    hashes = {}
    for name in critical:
        actual = sha256(root / "src/blr_rm" / name)
        hashes[name] = {
            "matches_benchmark": actual == protocol["environment"]["source_sha256"][name],
            "sha256": actual,
        }
    assert all(row["matches_benchmark"] for row in hashes.values()), "数值实现已变化，需要独立的新验证协议"
    source = root / "src/blr_rm"
    changed = [
        name for name, old in protocol["environment"]["source_sha256"].items() if sha256(source / name) != old
    ]
    checks = []
    for item in protocol["cases"]:
        name = f"case_{item['index']:04d}"
        data, result = benchmark / "data" / name, benchmark / "results" / name
        checked_data, checked = inspect_dataset(data), inspect_result(data, result)
        saved = json.loads((benchmark / f"{name}.json").read_text())
        for metric, value in checked["truth_metrics"].items():
            assert np.isclose(saved[metric], value, rtol=1e-12, atol=1e-12), (name, metric)
        assert checked_data["generator_forward"] == "PASS"
        assert checked["checks"]["forward_consistency"] == saved["forward"]
        assert checked["checks"]["numerical_convergence"] == saved["numerical"]
        checks.append(
            {
                "index": item["index"],
                "generator_forward_error": checked_data["generator_forward_relative_error"],
                "result_forward_error": checked["forward_relative_error"],
                **checked["checks"],
            }
        )
    receipt = {
        "schema_version": 1,
        "recomputed_objects": len(checks),
        "solve_reruns": 0,
        "critical_numeric_source_sha256": hashes,
        "all_critical_sources_match": True,
        "other_source_files_changed_after_run": changed,
        "post_run_changes": "GUI/CLI status propagation and packaged-executable provenance metadata only; no model, data, objective, metrics or numeric solver change",
        "max_generator_forward_error": max(row["generator_forward_error"] for row in checks),
        "max_result_forward_error": max(row["result_forward_error"] for row in checks),
        "all_saved_metrics_reproduced": True,
        "cases": checks,
    }
    with (root / "evidence/validation_reaudit.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
    for original, name in (
        (benchmark / "summary.json", "validation_summary.json"),
        (benchmark / "per_case.csv", "validation_per_case.csv"),
    ):
        assert not (root / "docs" / name).exists()
        shutil.copy2(original, root / "docs" / name)
    rows = list(csv.DictReader((benchmark / "per_case.csv").open(encoding="utf-8-sig")))
    fig = Figure(figsize=(12, 8), constrained_layout=True)
    axes = fig.subplots(2, 2)
    colors = {"1": "#377eb8", "2": "#169b86"}
    for dim in ("1", "2"):
        group = [row for row in rows if row["dimension"] == dim]
        errors = np.array([float(row["shape_nmse"]) for row in group])
        ordered = np.sort(errors)
        axes[0, 0].plot(
            ordered, np.arange(1, len(ordered) + 1) / len(ordered), label=dim + "D", color=colors[dim]
        )
        for noise, marker in ((0.02, "o"), (0.05, "s"), (0.10, "^")):
            subset = [row for row in group if float(row["noise_fraction"]) == noise]
            axes[0, 1].scatter(
                [noise + (int(dim) - 1.5) * 0.002] * len(subset),
                [float(row["shape_nmse"]) for row in subset],
                alpha=0.55,
                s=25,
                marker=marker,
                color=colors[dim],
            )
        lag = np.array([abs(float(row["lag_centroid_error_days"])) for row in group])
        axes[1, 0].plot(
            np.sort(lag), np.arange(1, len(lag) + 1) / len(lag), label=dim + "D", color=colors[dim]
        )
        index = int(dim) - 1
        axes[1, 1].bar(
            index - 0.18,
            sum(row["numerical"] == "PASS" for row in group),
            width=0.35,
            color=colors[dim],
            label="Final stationarity" if dim == "1" else None,
        )
        axes[1, 1].bar(
            index + 0.18,
            sum(row["floating_default"] == "WARN" for row in group),
            width=0.35,
            color="#d99b37",
            label="Floating-default warning" if dim == "1" else None,
        )
    axes[0, 0].set(
        xlabel="Shape NMSE", ylabel="Empirical cumulative fraction", title="Recovery distribution (all cases)"
    )
    axes[0, 0].legend()
    axes[0, 1].set(
        xlabel="Noise fraction of variable signal",
        ylabel="Shape NMSE",
        title="Each point is one independent driver",
    )
    axes[1, 0].set(
        xlabel="Absolute lag-centroid error [day]",
        ylabel="Empirical cumulative fraction",
        title="Lag recovery",
    )
    axes[1, 0].legend()
    axes[1, 1].set(
        xticks=[0, 1],
        xticklabels=["1D (N=72)", "2D (N=72)"],
        ylabel="Number of objects",
        title="Numerical checks and remaining warnings",
    )
    axes[1, 1].legend(fontsize=9)
    for axis in axes.ravel():
        axis.grid(alpha=0.18)
    fig.suptitle("BLR MEM development validation: 144 synthetic cases; no real-AGN claim", fontsize=13)
    fig.savefig(root / "docs/validation_panels.png", dpi=160)
    fig.clear()
    print(
        json.dumps(
            {
                "objects_reaudited": len(checks),
                "numeric_sources_match": True,
                "max_generator_forward_error": receipt["max_generator_forward_error"],
                "max_result_forward_error": receipt["max_result_forward_error"],
                "groups": summary["groups"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
