"""运行实际 Windows 二进制；原生 Windows 与 Wine 结果分别标注。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def validate(args):
    bundle, output = args.bundle.resolve(), args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if sys.platform != "win32" and not args.wine:
        raise ValueError("当前平台需要显式提供 --wine；不能以本机 Python 代替 Windows 二进制")
    if args.wine and not args.prefix:
        raise ValueError("Wine 测试必须指定独立 --prefix")
    environment = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "TCL_LIBRARY", "TK_LIBRARY"):
        environment.pop(key, None)
    environment.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MPLBACKEND="Agg")
    if args.wine:
        environment.update(
            WINEPREFIX=str(args.prefix.resolve()),
            WINEDEBUG="-all",
            WINEDLLOVERRIDES="winemenubuilder.exe=d",
            MVK_CONFIG_LOG_LEVEL="0",
        )
    commands = []

    def windows_path(path):
        return "Z:" + str(path.resolve()).replace("/", "\\") if args.wine else str(path.resolve())

    def run(command, accepted=(0,), timeout=90):
        invocation = [str(args.wine), *map(str, command)] if args.wine else list(map(str, command))
        completed = subprocess.run(
            invocation,
            cwd=output,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        record = {"arguments": list(map(str, command)), "returncode": completed.returncode}
        commands.append(record)
        (output / f"command_{len(commands):02d}.txt").write_text(
            completed.stdout + completed.stderr, encoding="utf-8"
        )
        if completed.returncode not in accepted:
            raise RuntimeError(f"Windows 操作失败：{record}；详情见 command_{len(commands):02d}.txt")
        return completed.stdout

    python = windows_path(bundle / "_runtime/python.exe")
    entry = windows_path(bundle / "launch.pyw")
    cli = [python, "-I", "-B", "-X", "utf8", entry, "--cli"]
    versions = run(
        [
            python,
            "-I",
            "-c",
            (
                "import sys,numpy,scipy,pandas,matplotlib,tkinter; "
                "print(sys.version); print(numpy.__version__,scipy.__version__,pandas.__version__,matplotlib.__version__); "
                "print(tkinter.Tcl().eval('info patchlevel'))"
            ),
        ]
    )
    version = run([*cli, "--version"]).strip()
    run(["cmd.exe", "/d", "/c", "call", windows_path(bundle / "blr-rm.cmd"), "--version"])
    run([*cli, "benchmark", "--profile", "smoke", "--out", windows_path(output / "smoke")])
    checks = []
    for dimension in (1, 2):
        data = output / f"smoke/data/case_{dimension - 1:04d}"
        result = output / f"smoke/results/case_{dimension - 1:04d}"
        for resume in (False, True):
            run(
                [
                    *cli,
                    "batch",
                    "--dimension",
                    str(dimension),
                    "--count",
                    "2",
                    "--out",
                    windows_path(output / f"batch_{dimension}D"),
                    *(["--resume"] if resume else []),
                ]
            )
        grid = output / f"grid_{dimension}D.json"
        grid.write_text(json.dumps({"alpha": [0.1, 0.2]} if dimension == 1 else {"alpha_map": [1000, 2000]}))
        for resume in (False, True):
            run(
                [
                    *cli,
                    "scan",
                    "--data",
                    windows_path(data),
                    "--grid",
                    windows_path(grid),
                    "--out",
                    windows_path(output / f"scan_{dimension}D"),
                    *(["--resume"] if resume else []),
                ],
                accepted=(0, 2),
            )
        checked = json.loads(
            run([*cli, "check", "--data", windows_path(data), "--result", windows_path(result)])
        )
        assert checked["checks"]["forward_consistency"] == "PASS"
        assert checked["checks"]["numerical_convergence"] == "PASS"
        checks.append(checked)
        run(
            [
                *cli,
                "report",
                "--data",
                windows_path(data),
                "--result",
                windows_path(result),
                "--out",
                windows_path(output / f"report_{dimension}D"),
            ]
        )
        run(["cmd.exe", "/d", "/c", "call", windows_path(bundle / f"{dimension}D/start.cmd"), "--gui-smoke"])
    invalid = output / "invalid.json"
    invalid.write_text("[]")
    run(
        [*cli, "generate", "--config", windows_path(invalid), "--out", windows_path(output / "unused")],
        accepted=(1,),
    )
    run(
        [
            windows_path(bundle / "BLRWorkbench.exe"),
            "--gui-flow",
            "--out",
            windows_path(output / "gui-flow.json"),
        ],
        timeout=120,
    )
    gui = json.loads((output / "gui-flow.json").read_text())
    assert len(gui["tests"]) == 2
    kind = "WINE_COMPATIBILITY_LAYER" if args.wine else "NATIVE_WINDOWS"
    receipt = {
        "schema_version": 1,
        "utc": datetime.now(UTC).isoformat(),
        "execution_environment": kind,
        "version": version,
        "runtime_versions": versions.strip(),
        "commands": commands,
        "native_windows_execution": "NOT_RUN" if args.wine else "PASS",
        "cli_generate_fit_check_report": "PASS_BOTH_DIMENSIONS",
        "batch_and_resume": "PASS_BOTH_DIMENSIONS",
        "pure_scan_and_resume": "PASS_BOTH_DIMENSIONS",
        "native_launcher_and_dimension_shortcuts": "PASS",
        "gui_flow": gui["tests"],
        "checks": checks,
        "scientific_acceptance": "NOT_ASSESSED",
    }
    (output / "validation.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "environment": kind,
                "version": version,
                "commands_completed": len(commands),
                "cli": "PASS_BOTH_DIMENSIONS",
                "gui": "PASS_BOTH_DIMENSIONS",
                "native_windows_execution": receipt["native_windows_execution"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--wine", type=Path)
    parser.add_argument("--prefix", type=Path)
    validate(parser.parse_args())
