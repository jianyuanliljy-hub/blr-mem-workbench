"""预先落盘协议的小型验证矩阵；失败对象和全部分母保留。"""

from __future__ import annotations

import csv
import html
import itertools
from pathlib import Path

import numpy as np

from .config import defaults, solver_defaults, resolved_solver
from .data import generate
from .detector import inspect_dataset, inspect_result, recovery_metrics
from .report import write_html
from .solver import load_observations, optimize
from .storage import array_identity, environment, load_arrays, read_json, save_json


def _cases(profile):
    if profile not in ("smoke", "validation"):
        raise ValueError("profile 必须为 smoke 或 validation")
    records = []
    for dimension in (1, 2):
        families = (
            ["gaussian", "double_gaussian", "top_hat"]
            if dimension == 1
            else ["gaussian", "tilted_gaussian", "two_blobs"]
        )
        if profile == "smoke":
            families = families[:1]
        noises = [0.05] if profile == "smoke" else [0.02, 0.05, 0.10]
        missing = [0.0] if profile == "smoke" else [0.0, 0.15]
        repeats = range(1 if profile == "smoke" else 4)
        for family, noise, fraction, repeat in itertools.product(families, noises, missing, repeats):
            index = len(records)
            records.append(
                {
                    "index": index,
                    "replicate": repeat,
                    "config": {
                        **defaults(dimension),
                        "family": family,
                        "noise_fraction": noise,
                        "missing_fraction": fraction,
                        "seed": 2026102100 + index,
                    },
                }
            )
    return records


def run_benchmark(output, profile="smoke", resume=False, progress=None, engine=None):
    output = Path(output)
    cases = _cases(profile)
    protocol = {
        "schema_version": 1,
        "profile": profile,
        "cases": cases,
        "solver_defaults": {str(dim): resolved_solver(dim, {'engine': engine}) if engine else solver_defaults(dim) for dim in (1, 2)},
        "selection": "Frozen example defaults; no truth tuning or case removal",
        "factorial_design": "Different independent driver seed in every cell; descriptive factor comparison",
        "environment": environment(),
    }
    if resume:
        original = read_json(output / "protocol.json")
        if any(original[key] != protocol[key] for key in ("profile", "cases", "solver_defaults")):
            raise ValueError("验证协议已变化")
        if original["environment"]["source_sha256"] != protocol["environment"]["source_sha256"]:
            raise ValueError("实现已变化；必须新建验证目录以保留原结果")
    else:
        output.mkdir(parents=True, exist_ok=False)
        save_json(output / "protocol.json", protocol)
    rows = []
    for item in cases:
        index, cfg = item["index"], item["config"]
        case_name = f"case_{index:04d}"
        dataset, result = output / "data" / case_name, output / "results" / case_name
        receipt = output / f"{case_name}.json"
        if receipt.exists():
            if not resume:
                raise FileExistsError(str(receipt))
            row = read_json(receipt)
            if row["state"] == "COMPLETED":
                inspect_dataset(dataset)
                inspect_result(dataset, result)
            rows.append(row)
            continue
        row = {
            "index": index,
            "dimension": cfg["dimension"],
            "family": cfg["family"],
            "noise_fraction": cfg["noise_fraction"],
            "missing_fraction": cfg["missing_fraction"],
            "seed": cfg["seed"],
        }
        try:
            if not dataset.exists():
                generate(cfg, dataset, plots=False)
            check_data = inspect_dataset(dataset)
            if result.exists():
                if not resume:
                    raise FileExistsError(str(result))
            else:
                optimize(dataset, result, protocol['solver_defaults'][str(cfg['dimension'])])
            checked = inspect_result(dataset, result)
            meta, obs = load_observations(dataset)
            truth = load_arrays(dataset / "truth.npz")
            baseline = np.ones_like(truth["psi_true"])
            baseline /= baseline.sum() * cfg["delay_step_days"]
            base_metrics = recovery_metrics(baseline, truth["psi_true"], obs["delays"], obs["velocities"])
            row.update(
                state="COMPLETED",
                observation_id=meta["observation_id"],
                driver_id=array_identity({"c_true": truth["c_true"]}),
                map_id=array_identity({"psi_true": truth["psi_true"]}),
                generator_forward=check_data["generator_forward"],
                numerical=checked["checks"]["numerical_convergence"],
                forward=checked["checks"]["forward_consistency"],
                floating_default=checked["checks"]["floating_default_stability"],
                optimizer_success=checked["optimizer_success"],
                compute_seconds=checked["compute_seconds"],
                flat_shape_nmse=base_metrics["shape_nmse"],
                **checked["truth_metrics"],
            )
        except (ValueError, OSError, RuntimeError) as error:
            row.update(state="FAILED", error=str(error))
        save_json(receipt, row)
        rows.append(row)
        if progress:
            progress(
                f"验证 {index + 1}/{len(cases)}：{cfg['dimension']}D {cfg['family']}，数值状态 {row.get('numerical', row['state'])}"
            )
    summary = summarize(rows, profile)
    if not (output / "summary.json").exists():
        save_json(output / "summary.json", summary)
        columns = sorted(set().union(*(set(row) for row in rows)))
        with (output / "per_case.csv").open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        write_benchmark_report(output, summary)
    return summary


def summarize(rows, profile):
    completed = [row for row in rows if row["state"] == "COMPLETED"]
    groups = []
    for dimension in (1, 2):
        group = [row for row in completed if row["dimension"] == dimension]
        planned = sum(row["dimension"] == dimension for row in rows)
        if not group:
            groups.append({"dimension": dimension, "planned": planned, "completed": 0})
            continue
        errors = np.array([row["shape_nmse"] for row in group])
        differences = errors - np.array([row["flat_shape_nmse"] for row in group])
        rng = np.random.default_rng(20261021 + dimension)
        draws = rng.choice(differences, size=(2000, len(differences)), replace=True).mean(axis=1)
        groups.append(
            {
                "dimension": dimension,
                "planned": planned,
                "completed": len(group),
                "numerical_pass": sum(row["numerical"] == "PASS" for row in group),
                "forward_pass": sum(row["forward"] == "PASS" for row in group),
                "floating_default_warn": sum(row["floating_default"] == "WARN" for row in group),
                "optimizer_history_warning": sum(not row["optimizer_success"] for row in group),
                "shape_nmse_mean": float(errors.mean()),
                "shape_nmse_median": float(np.median(errors)),
                "shape_nmse_p90": float(np.quantile(errors, 0.9)),
                "mean_paired_delta_vs_flat": float(differences.mean()),
                "paired_bootstrap_mean_delta_95ci": np.quantile(draws, [0.025, 0.975]).tolist(),
                "lag_mae_days": float(np.mean([abs(row["lag_centroid_error_days"]) for row in group])),
                "runtime_median_seconds": float(np.median([row["compute_seconds"] for row in group])),
            }
        )
    return {
        "schema_version": 1,
        "profile": profile,
        "planned": len(rows),
        "completed": len(completed),
        "execution_failures": len(rows) - len(completed),
        "unique_observations": len({row["observation_id"] for row in completed}),
        "unique_drivers": len({row["driver_id"] for row in completed}),
        "unique_maps": len({row["map_id"] for row in completed}),
        "groups": groups,
        "metrics_include_numerically_flagged_cases": True,
        "confidence_interval_scope": "Object bootstrap within this finite synthetic suite; no real-data or model-family coverage guarantee",
        "worst_ten_cases": sorted(completed, key=lambda row: row["shape_nmse"], reverse=True)[:10],
        "failed_cases": [row for row in rows if row["state"] != "COMPLETED"],
        "scientific_acceptance": "NOT_ASSESSED",
        "real_agn_validation": "NOT_RUN",
    }


def write_benchmark_report(output, summary):
    table = "<table><tr><th>维度</th><th>完成/计划</th><th>数值通过</th><th>形状 NMSE 中位数</th><th>形状 NMSE P90</th><th>时延 MAE/day</th><th>求解时间中位数/s</th></tr>"
    for row in summary["groups"]:
        if not row["completed"]:
            table += f'<tr><td>{row["dimension"]}D</td><td>0/{row["planned"]}</td><td colspan="5">无可分析输出</td></tr>'
            continue
        table += (
            f"<tr><td>{row['dimension']}D</td><td>{row['completed']}/{row['planned']}</td>"
            f"<td>{row['numerical_pass']}/{row['planned']}</td><td>{row['shape_nmse_median']:.5f}</td>"
            f"<td>{row['shape_nmse_p90']:.5f}</td><td>{row['lag_mae_days']:.5f}</td>"
            f"<td>{row['runtime_median_seconds']:.4f}</td></tr>"
        )
    table += "</table>"
    body = "<p>协议在首个对象计算前写入 protocol.json。每个对象使用独立连续谱种子；所有有限输出均进入统计，包括数值检测失败的对象。平坦图仅是信息量较低的对照，不能替代其他成熟反演程序的比较。</p>"
    body += (
        f"<p>独立观测 {summary['unique_observations']}，独立 driver {summary['unique_drivers']}，不同传递图 {summary['unique_maps']}。</p>"
        + table
    )
    body += (
        "<h2>完整统计与不利对象</h2><pre>"
        + html.escape(__import__("json").dumps(summary, ensure_ascii=False, indent=2))
        + "</pre>"
    )
    write_html(Path(output) / "report.html", "BLR MEM 软件验证报告", body)
