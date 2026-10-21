"""保留本地可定位的 Python、数值依赖和 conda 二进制许可证。"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import shutil
import sys
import sysconfig
from pathlib import Path


def collect_notices(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    copied = {}

    def copy(source, relative):
        target = destination / relative
        if not source.is_file() or target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied[str(relative)] = hashlib.sha256(source.read_bytes()).hexdigest()

    copy(Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", Path("Python/LICENSE.txt"))
    for name in (
        "numpy",
        "scipy",
        "pandas",
        "matplotlib",
        "pillow",
        "python-dateutil",
        "pytz",
        "tzdata",
        "six",
        "contourpy",
        "cycler",
        "fonttools",
        "kiwisolver",
        "pyparsing",
        "packaging",
        "setuptools",
    ):
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        for file in distribution.files or ():
            if (
                Path(file).name.lower().startswith(("license", "licence", "copying", "copyright", "notice"))
                and ".." not in file.parts
            ):
                copy(Path(distribution.locate_file(file)), Path(name) / file)
    prefix = Path(sys.base_prefix)
    for path in (prefix / "conda-meta").glob("*.json"):
        record = json.loads(path.read_text())
        if record.get("name") not in ("python", "tk", "libopenblas", "libgfortran5", "libcxx"):
            continue
        source = record.get("link", {}).get("source")
        if source:
            licenses = Path(source) / "info/licenses"
            for file in licenses.rglob("*"):
                if file.is_file():
                    copy(file, Path(record["name"]) / file.relative_to(licenses))
    receipt = {
        "scope": "Located notices preserved; final redistribution license audit remains required",
        "sha256": copied,
    }
    (destination / "manifest.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return len(copied)
