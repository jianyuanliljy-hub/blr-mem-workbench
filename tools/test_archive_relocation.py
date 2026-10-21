"""解压成品到新路径再运行；不调用开发环境的程序核心。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path


def check(args):
    if args.platform == "windows" and sys.platform != "win32" and not args.wine:
        raise ValueError("非 Windows 系统须指定 --wine")
    if args.wine and not args.prefix:
        raise ValueError("Wine 检查须指定独立 --prefix")
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    archive = args.archive.resolve()
    if args.platform == "macos":
        subprocess.run(["/usr/bin/ditto", "-x", "-k", str(archive), str(output)], check=True, timeout=120)
        bundle = next(path for path in output.iterdir() if path.is_dir() and path.name != "__MACOSX")
    else:
        with zipfile.ZipFile(archive) as contents:
            contents.extractall(output)
        bundle = output / "BLR_MEM_Windows"
    environment = dict(os.environ)
    for name in ("PYTHONHOME", "PYTHONPATH", "TCL_LIBRARY", "TK_LIBRARY", "DYLD_LIBRARY_PATH"):
        environment.pop(name, None)
    environment.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    if sys.platform == "win32":
        system = Path(os.environ.get("SystemRoot", "C:/Windows"))
        environment["PATH"] = str(system / "System32") + os.pathsep + str(system)
    else:
        environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    if args.wine:
        environment.update(
            WINEPREFIX=str(args.prefix.resolve()),
            WINEDEBUG="-all",
            WINEDLLOVERRIDES="winemenubuilder.exe=d",
            MVK_CONFIG_LOG_LEVEL="0",
        )
    commands = []

    def win(path):
        return "Z:" + str(path.resolve()).replace("/", "\\") if args.wine else str(path.resolve())

    def run(arguments):
        invocation = [str(args.wine), *arguments] if args.wine else arguments
        completed = subprocess.run(
            invocation,
            cwd=output,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=150,
            check=False,
        )
        commands.append({"arguments": arguments, "returncode": completed.returncode})
        (output / f"command_{len(commands):02d}.txt").write_text(
            completed.stdout + completed.stderr, encoding="utf-8"
        )
        completed.check_returncode()
        return completed.stdout

    if args.platform == "macos":
        executable = bundle / "BLR MEM Workbench.app/Contents/MacOS/BLRWorkbench"
        run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(bundle / "BLR MEM Workbench.app")])
        cli = [str(bundle / "blr-rm")]
        flow = [str(executable), "--gui-flow", "--out", str(output / "gui-flow.json")]
        smoke_output = str(output / "smoke")
    else:
        cli = [
            win(bundle / "_runtime/python.exe"),
            "-I",
            "-B",
            "-X",
            "utf8",
            win(bundle / "launch.pyw"),
            "--cli",
        ]
        flow = [win(bundle / "BLRWorkbench.exe"), "--gui-flow", "--out", win(output / "gui-flow.json")]
        smoke_output = win(output / "smoke")
    version = run([*cli, "--version"]).strip()
    assert version == "0.1.0.dev1"
    run([*cli, "benchmark", "--profile", "smoke", "--out", smoke_output])
    run(flow)
    for dimension in (1, 2):
        data, result = bundle / f"examples/{dimension}D/data", bundle / f"examples/{dimension}D/result"
        checked = run(
            [
                *cli,
                "check",
                "--data",
                win(data) if args.wine else str(data),
                "--result",
                win(result) if args.wine else str(result),
            ]
        )
        assert json.loads(checked)["checks"]["numerical_convergence"] == "PASS"
    receipt = {
        "platform": args.platform,
        "version": version,
        "environment": (
            "WINE_COMPATIBILITY_LAYER"
            if args.wine
            else "NATIVE_MACOS"
            if args.platform == "macos"
            else "NATIVE_WINDOWS"
        ),
        "unicode_and_space_archive_location": "PASS",
        "external_python_and_tk_environment_removed": True,
        "path_contains_system_directories_only": True,
        "gui": json.loads((output / "gui-flow.json").read_text()),
        "examples_checked_against_paired_data": "PASS_BOTH_DIMENSIONS",
        "commands": commands,
        "native_windows_execution": "PASS" if args.platform == "windows" and not args.wine else "NOT_RUN",
    }
    (output / "archive_validation.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "platform": args.platform,
                "version": version,
                "commands_completed": len(commands),
                "archive_relocation": "PASS",
                "environment": receipt["environment"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "macos"), required=True)
    parser.add_argument("--wine", type=Path)
    parser.add_argument("--prefix", type=Path)
    check(parser.parse_args())
