"""本机架构的 macOS .app 构建、签名校验与冻结程序检查。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from collect_macos_notices import collect_notices


def run(command, cwd, **kwargs):
    return subprocess.run(command, cwd=cwd, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--skip-gui-check", action="store_true", help="无桌面会话时跳过，并明确记录未运行")
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("macOS .app 必须在 macOS 构建。Windows 构建请使用 build_windows.py。")
    arch = platform.machine()
    if arch not in ("arm64", "x86_64"):
        raise SystemExit(f"不支持的 macOS 架构: {arch}")
    root = Path(__file__).resolve().parents[1]
    output = (args.out or root / f"dist/BLR-MEM-macOS-{arch}").resolve()
    work = (args.work or root / f"build/macos-{arch}").resolve()
    if output.exists() or work.exists():
        raise SystemExit("输出或构建目录已存在；请使用新目录，保留原产物与检查记录。")
    output.mkdir(parents=True)
    work.mkdir(parents=True)
    source = root / "src/blr_rm"
    identity = {
        "schema_version": 1,
        "utc": datetime.now(UTC).isoformat(),
        "architecture": arch,
        "source_sha256": {
            path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(source.rglob("*.py"))
        },
    }
    identity_path = work / "build_identity.json"
    identity_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    environment = {
        **os.environ,
        "BLR_MACOS_BUILD_IDENTITY": str(identity_path),
        "PYINSTALLER_CONFIG_DIR": str(work / "cache"),
    }
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(root / "blr_rm_macos.spec"),
            "--distpath",
            str(work / "frozen"),
            "--workpath",
            str(work / "pyinstaller"),
        ],
        root,
        env=environment,
    )
    app = output / "BLR MEM Workbench.app"
    shutil.copytree(work / "frozen/BLR MEM Workbench.app", app, symlinks=True)
    binary = app / "Contents/MacOS/BLRWorkbench"
    for directory in ("1D", "2D", "docs"):
        shutil.copytree(root / directory, output / directory)
    for name in ("README.md", "NOTICE.md", "CITATION.cff", "provenance.json"):
        shutil.copy2(root / name, output / name)
    shutil.copy2(identity_path, output / "build_identity.json")
    collect_notices(output / "THIRD_PARTY_NOTICES")
    cli = output / "blr-rm"
    cli.write_text(
        '#!/bin/sh\nset -eu\npackage_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\n'
        'exec "$package_dir/BLR MEM Workbench.app/Contents/MacOS/BLRWorkbench" --cli "$@"\n',
        encoding="utf-8",
    )
    cli.chmod(0o755)
    for directory in ("1D", "2D"):
        (output / directory / "start.command").chmod(0o755)
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)], output, timeout=45)
    version = run([str(cli), "--version"], output, capture_output=True, text=True, timeout=30).stdout.strip()
    expected = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if version != expected:
        raise RuntimeError(f"冻结程序未返回预期版本: {version!r}")
    run(
        [str(cli), "benchmark", "--profile", "smoke", "--out", str(work / "binary-smoke")], output, timeout=90
    )
    gui = "NOT_RUN_NO_DESKTOP_SESSION"
    if not args.skip_gui_check:
        for dimension in (1, 2):
            run([str(binary), "--gui-smoke", "--dimension", str(dimension)], output, timeout=30)
        gui = "PASS_INITIALIZATION_BOTH_DIMENSIONS"
    receipt = {
        "schema_version": 1,
        "utc": datetime.now(UTC).isoformat(),
        "architecture": arch,
        "build_platform": platform.platform(),
        "python": sys.version,
        "version": version,
        "codesign_verification": "PASS_AD_HOC",
        "developer_id_and_notarization": "NOT_DONE",
        "frozen_cli_smoke": "PASS_BOTH_DIMENSIONS",
        "native_gui": gui,
        "manual_visual_review": "NOT_ASSESSED",
        "clean_mac_without_python": "NOT_ASSESSED",
        "license": "PENDING_AUTHOR_CONFIRMATION",
        "executable_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    }
    (output / "build_validation.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    print(output)


if __name__ == "__main__":
    main()
