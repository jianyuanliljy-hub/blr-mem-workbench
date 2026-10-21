"""只读复核本地来源、早期二维索引，以及当前封装的数学边界。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    package = Path(__file__).resolve().parents[1]
    workspace = package.parent
    path = workspace / "20260812-zzm 代码/create_2D.py"
    rng_before = np.random.get_state()
    spec = importlib.util.spec_from_file_location("legacy_create_2d_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    np.random.set_state(rng_before)
    times = np.arange(-100, 100, dtype=float)
    values = times**2 / 10000 + np.sin(times / 7)
    continuum = pd.Series(values, index=times)
    truth = pd.DataFrame(np.zeros((100, 100)), columns=np.arange(100), index=np.arange(100))
    truth.iloc[0, 0] = 1
    legacy = module.create_l_true(continuum, truth).to_numpy(dtype=float)
    centered = values - values.mean()
    reported_tau0 = np.interp(np.arange(100), times, centered) + 2
    actual_tau1 = np.interp(np.arange(100) - 1, times, centered) + 2
    original_meta = json.loads((package / "provenance.json").read_text())
    integrity = []
    for row in original_meta["files"]:
        current = hashlib.sha256((workspace / row["source"]).read_bytes()).hexdigest()
        integrity.append(
            {"source": row["source"], "unchanged": current == row["source_sha256"], "sha256": current}
        )
    receipt = {
        "legacy_generator": str(path.relative_to(workspace)),
        "legacy_source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "zero_delay_impulse": {
            "max_absolute_error_against_tau0": float(np.max(np.abs(legacy[0] - reported_tau0))),
            "max_absolute_error_against_tau1": float(np.max(np.abs(legacy[0] - actual_tau1))),
            "conclusion": "Legacy generator column labeled tau=0 actually uses C(t-1); optimizer uses C(t).",
        },
        "source_integrity": integrity,
        "one_dimensional_reference": "Joint MEM fixed-default objective; this package adds diagonal scaling, not the Week-1 fixed-driver FGLS pipeline.",
        "two_dimensional_reference": "Existing joint MEM; final frozen defaults are exposed for independent gradient checks. No external MEMECHO code copied.",
    }
    output = package / "evidence/local_source_audit.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
