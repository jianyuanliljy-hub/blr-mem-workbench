"""复核已有 macOS 应用；使用新输出目录，不覆盖构建或科研结果。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True, help="包含 .app 和 blr-rm 的分发目录")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--skip-gui-check", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("此检查需要 macOS。")
    bundle, output = args.bundle.resolve(), args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    app = bundle / "BLR MEM Workbench.app"
    binary = app / "Contents/MacOS/BLRWorkbench"
    cli = bundle / "blr-rm"
    commands = []
    environment = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    for key in ("PYTHONHOME", "PYTHONPATH", "TCL_LIBRARY", "TK_LIBRARY", "DYLD_LIBRARY_PATH"):
        environment.pop(key, None)

    def run(command, timeout=45):
        completed = subprocess.run(
            command, cwd=output, env=environment, capture_output=True, text=True, timeout=timeout, check=False
        )
        commands.append({"command": [str(value) for value in command], "returncode": completed.returncode})
        log = output / f"command_{len(commands):02d}.txt"
        log.write_text(completed.stdout + completed.stderr, encoding="utf-8")
        completed.check_returncode()
        return completed.stdout

    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)])
    architecture = run(["/usr/bin/lipo", "-archs", str(binary)]).strip()
    if architecture != platform.machine():
        raise RuntimeError(f"产物架构与当前执行架构不同: {architecture}")
    version = run([str(cli), "--version"]).strip()
    expected = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())["project"][
        "version"
    ]
    if version != expected:
        raise RuntimeError(f"无法取得版本: {version!r}")
    run([str(cli), "benchmark", "--profile", "smoke", "--out", str(output / "cli-smoke")])
    run(
        [
            str(cli),
            "batch",
            "--config",
            str(bundle / "1D/generate_clean.json"),
            "--count",
            "2",
            "--out",
            str(output / "clean-batch"),
        ]
    )
    grid = output / "scan-grid.json"
    grid.write_text(json.dumps({"alpha": [0.1, 0.2]}), encoding="utf-8")
    data = output / "cli-smoke/data/case_0000"
    result = output / "cli-smoke/results/case_0000"
    run([str(cli), "scan", "--data", str(data), "--grid", str(grid), "--out", str(output / "scan")])
    run(
        [
            str(cli),
            "report",
            "--data",
            str(data),
            "--result",
            str(result),
            "--out",
            str(output / "cli-report"),
        ]
    )
    gui = "NOT_RUN_NO_DESKTOP_SESSION"
    if not args.skip_gui_check:
        for dimension in (1, 2):
            run([str(binary), "--gui-smoke", "--dimension", str(dimension)], timeout=15)
        run([str(binary), "--gui-flow", "--out", str(output / "gui-flow.json")], timeout=55)
        gui = "PASS_BOTH_DIMENSIONS_GENERATE_FIT_CHECK_REPORT_ERROR_RECOVERY"
    magic = {bytes.fromhex(value) for value in ("cffaedfe", "feedfacf", "cafebabe", "bebafeca")}
    binaries = []
    for path in app.rglob("*"):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                if stream.read(4) in magic:
                    binaries.append(path)

    def dependencies(path):
        text = subprocess.check_output(["/usr/bin/otool", "-L", str(path)], text=True)
        names = [line.strip().split(" (", 1)[0] for line in text.splitlines()[1:] if line.startswith("\t")]
        external = [
            name
            for name in names
            if name.startswith("/") and not name.startswith(("/System/Library/", "/usr/lib/"))
        ]
        return path.relative_to(app).as_posix(), external

    with ThreadPoolExecutor(max_workers=6) as pool:
        external = {name: values for name, values in pool.map(dependencies, binaries) if values}
    if external:
        raise RuntimeError(f"应用仍依赖外部动态库: {external}")
    smoke = json.loads((output / "cli-smoke/summary.json").read_text())
    identity = json.loads((bundle / "build_identity.json").read_text())
    receipt = {
        "schema_version": 1,
        "utc": datetime.now(UTC).isoformat(),
        "architecture": architecture,
        "platform": platform.platform(),
        "version": version,
        "codesign_verification": "PASS_AD_HOC",
        "executable_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "source_sha256": identity["source_sha256"],
        "cli_smoke_completed": smoke["completed"],
        "cli_smoke_numerical_pass": sum(group["numerical_pass"] for group in smoke["groups"]),
        "floating_default_warnings_retained": sum(
            group["floating_default_warn"] for group in smoke["groups"]
        ),
        "clean_batch": "PASS_TWO_CASES",
        "pure_scan": "PASS_TWO_POINTS",
        "offline_report": "PASS",
        "native_gui_flow": gui,
        "non_system_external_dynamic_dependencies": external,
        "mach_o_files_checked": len(binaries),
        "python_environment_variables_removed": True,
        "fresh_mac_without_python": "NOT_RUN",
        "developer_id_and_notarization": "NOT_DONE",
        "manual_visual_review": "NOT_ASSESSED",
        "commands": commands,
    }
    (output / "validation.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in receipt.items() if key not in ("commands", "source_sha256")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
