"""从已下载、固定版本的 Windows 运行时和 wheels 组装离线包；不声称完成 Windows 实测。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

RUNTIME_SHA256 = "bf9d014f24aa15f2ae37814e748773e395cbec111e368a91cdbcb4372bdff7c5"
RUNTIME_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/20250712/"
    "cpython-3.13.5%2B20250712-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(args):
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    if out.exists():
        raise FileExistsError(f"请使用新的输出目录：{out}")
    if digest(args.runtime) != RUNTIME_SHA256:
        raise ValueError("Windows 运行时 SHA-256 不匹配")
    wheels = sorted(args.wheels.glob("*.whl"))
    required = [
        line
        for line in (root / "requirements-runtime.txt").read_text().splitlines()
        if line and not line.startswith("#")
    ]
    names = {path.name.split("-")[0].lower().replace("_", "-"): path for path in wheels}
    for requirement in required:
        name, version = requirement.split("==")
        path = names.get(name.lower())
        if not path or path.name.split("-")[1] != version:
            raise ValueError(f"缺少固定版本 wheel：{requirement}")
        if not path.name.endswith(("cp313-cp313-win_amd64.whl", "none-any.whl")):
            raise ValueError(f"wheel 平台不对应 Windows CPython 3.13 x64：{path.name}")
    out.mkdir(parents=True)
    with tarfile.open(args.runtime) as archive:
        for member in archive:
            if member.name == "python":
                continue
            if not member.name.startswith("python/"):
                raise ValueError("运行时归档包含意外路径")
            member.name = member.name[len("python/") :]
            archive.extract(member, out / "_runtime", filter="data")
    library = out / "_runtime/Lib/site-packages"
    library.mkdir(exist_ok=True)
    for path in names.values():
        with zipfile.ZipFile(path) as archive:
            # 固定 wheel 集合仅包含库；所有根目录文件保留，包括许可证和 dist-info。
            archive.extractall(library)
    shutil.copytree(
        root / "src/blr_rm", out / "app/blr_rm", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    shutil.copy2(root / "tools/frozen_entry.py", out / "app/frozen_entry.py")
    shutil.copy2(root / "tools/portable_entry.py", out / "launch.pyw")
    for folder in ("1D", "2D", "docs"):
        shutil.copytree(root / folder, out / folder)
    for name in ("README.md", "NOTICE.md", "CITATION.cff", "provenance.json", "requirements-runtime.txt"):
        shutil.copy2(root / name, out / name)
    for dimension in (1, 2):
        (out / f"{dimension}D/start.cmd").write_bytes(
            (f'@echo off\r\n"%~dp0..\\BLRWorkbench.exe" --dimension {dimension} %*\r\n').encode("ascii")
        )
    (out / "blr-rm.cmd").write_bytes(
        b'@echo off\r\n"%~dp0_runtime\\python.exe" -I -B -X utf8 "%~dp0launch.pyw" --cli %*\r\nexit /b %errorlevel%\r\n'
    )
    (out / "Diagnose.cmd").write_bytes(
        b'@echo off\r\nchcp 65001 >nul\r\n"%~dp0_runtime\\python.exe" -I -B -X utf8 "%~dp0launch.pyw" --gui-flow --out "%TEMP%\\BLR_GUI_CHECK_%RANDOM%.json"\r\necho.\r\necho Result code: %errorlevel%\r\npause\r\n'
    )
    subprocess.run(
        [
            str(args.zig),
            "cc",
            "-target",
            "x86_64-windows-gnu",
            "-municode",
            "-Wl,--subsystem,windows",
            "-Os",
            "-s",
            str(root / "tools/windows_launcher.c"),
            "-o",
            str(out / "BLRWorkbench.exe"),
            "-luser32",
        ],
        check=True,
        timeout=180,
    )
    required_files = [
        "python.exe",
        "pythonw.exe",
        "DLLs/_tkinter.pyd",
        "tcl/tcl8.6/init.tcl",
        "tcl/tk8.6/tk.tcl",
    ]
    if any(not (out / "_runtime" / name).is_file() for name in required_files):
        raise ValueError("运行时缺少 Python 或 Tcl/Tk 必需文件")
    identity = {
        "schema_version": 1,
        "utc": datetime.now(UTC).isoformat(),
        "architecture": "Windows x86-64",
        "format": "PORTABLE_CPYTHON_WITH_NATIVE_LAUNCHER",
        "python": "3.13.5",
        "runtime_url": RUNTIME_URL,
        "runtime_sha256": RUNTIME_SHA256,
        "wheel_sha256": {path.name: digest(path) for path in wheels},
        "source_sha256": {
            path.relative_to(root / "src/blr_rm").as_posix(): digest(path)
            for path in sorted((root / "src/blr_rm").rglob("*.py"))
        },
        "native_windows_execution": "NOT_RUN",
        "compatibility_layer_execution": "NOT_RUN",
    }
    write(out / "build_identity.json", identity)
    write(
        out / "assembly_validation.json",
        {
            "runtime_and_wheel_versions": "PASS",
            "python_and_tk_files_present": "PASS",
            "native_launcher_built": "PASS",
            "scientific_acceptance": "NOT_ASSESSED",
            "native_windows_execution": "NOT_RUN",
        },
    )
    print(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--zig", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    build(parser.parse_args())
