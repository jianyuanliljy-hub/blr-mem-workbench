"""仅在 Windows 本机/Windows CI 构建并验证可执行文件。"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    if sys.platform != "win32":
        raise SystemExit(
            "Windows EXE 需要 Windows 构建环境。当前平台只能验证源码，不能宣称已生成 Windows 可执行文件。"
        )
    root = Path(__file__).resolve().parents[1]
    dist = root / "dist/BLR-RM"
    if dist.exists():
        raise SystemExit("dist/BLR-RM 已存在；请选用全新的构建工作区，避免覆盖原构建。")
    identity_path = root / "build/build_identity.json"
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    sources = root / "src/blr_rm"
    hashes = {
        str(path.relative_to(sources)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(sources.rglob("*.py"))
    }
    with identity_path.open("x", encoding="utf-8") as stream:
        json.dump({"source_sha256": hashes}, stream, indent=2)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(root / "blr_rm_windows.spec"),
            "--distpath",
            str(root / "dist"),
            "--workpath",
            str(root / "build/pyinstaller"),
        ],
        cwd=root,
        check=True,
    )
    for name in ("1D", "2D", "docs"):
        shutil.copytree(root / name, dist / name)
    for name in ("README.md", "NOTICE.md", "provenance.json"):
        shutil.copy2(root / name, dist / name)
    for dimension in (1, 2):
        for name in ('GenerateData', 'BatchGenerate', 'MEMOptimizer', 'Detector', 'Analysis'):
            (dist/f'{dimension}D/{name}.cmd').write_bytes(
                (f'@echo off\r\n"%~dp0..\\{name}.exe" --dimension {dimension}\r\n').encode('ascii'))
    shutil.copy2(identity_path, dist / "build_identity.json")
    from validate_distribution import validate
    validate(dist, root/'build/frozen-validation')
    shutil.copy2(root/'build/frozen-validation/validation.json', dist/'validation.json')
    shutil.make_archive(str(root/'dist/BLR-MEM-Windows-x64'), 'zip', root/'dist', 'BLR-RM')
    print(dist)


if __name__ == "__main__":
    main()
