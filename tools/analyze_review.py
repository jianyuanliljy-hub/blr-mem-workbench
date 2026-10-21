"""只读复核已有 144 例，解释默认图像变化；不重新求解、不改变验收标准。"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from blr_rm.config import defaults, solver_defaults
from blr_rm.detector import inspect_dataset, inspect_result
from blr_rm.report import default_map_diagnostic
from blr_rm.storage import load_arrays, read_json, save_json, sha256


def analyze(output):
    root = Path(__file__).resolve().parents[1]
    output.mkdir(parents=True, exist_ok=False)
    save_json(
        output / "protocol.json",
        {
            "kind": "POST_HOC_READ_ONLY_DIAGNOSTIC",
            "case_selection": "All existing 144 cases; all 72 2D maps",
            "low_response_threshold": "Psi < 0.01 * max(Psi)",
            "acceptance_changes": "NONE",
            "reoptimization": "NONE",
        },
    )
    before = read_json(root / "evidence/improvement_review_20261021/source_before.json")["source_sha256"]
    core = [
        name
        for name in before
        if name.endswith(("solver.py", "scaled_1d.py", "detector.py", "data.py")) or "/_vendor/" in name
    ]
    assert all(sha256(root / name) == before[name] for name in core)
    for dimension in (1, 2):
        assert defaults(dimension) == read_json(root / f"{dimension}D/generate_clean.json")
        assert solver_defaults(dimension) == read_json(root / f"{dimension}D/mem_defaults.json")
    suite = root / "evidence/validation_20261021_v1"
    rows = []
    for index in range(144):
        data, result = suite / f"data/case_{index:04d}", suite / f"results/case_{index:04d}"
        original = read_json(suite / f"case_{index:04d}.json")
        checked = inspect_result(data, result)
        generated = inspect_dataset(data)
        assert generated["generator_forward"] == original["generator_forward"]
        assert checked["checks"]["numerical_convergence"] == original["numerical"]
        assert checked["checks"]["floating_default_stability"] == original["floating_default"]
        for key, value in checked["truth_metrics"].items():
            assert np.isclose(value, original[key], rtol=1e-12, atol=1e-12)
        if original["dimension"] == 2:
            config = read_json(result / "result.json")["solver_config"]
            diagnostic = default_map_diagnostic(load_arrays(result / "solution.npz"), config)
            rows.append(
                {
                    "index": index,
                    **{
                        key: value
                        for key, value in diagnostic.items()
                        if key not in ("purpose", "low_response_definition")
                    },
                }
            )
    with (output / "low_response_per_case.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "existing_144_cases_rechecked": "PASS",
        "saved_metrics_and_statuses_unchanged": "PASS",
        "scientific_core_source_sha256": {name: before[name] for name in core},
        "generator_and_solver_defaults": "UNCHANGED",
        "2d_cases": len(rows),
        "post_hoc_medians": {
            key: float(np.median([row[key] for row in rows if row[key] is not None]))
            for key in rows[0]
            if key != "index"
        },
        "acceptance_thresholds": "UNCHANGED",
        "floating_default_warnings": 72,
        "scientific_acceptance": "NOT_ASSESSED",
    }
    save_json(output / "summary.json", summary)
    print(summary["post_hoc_medians"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    analyze(parser.parse_args().out)
