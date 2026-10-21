# -*- mode: python ; coding: utf-8 -*-
"""原生架构 .app；图形和命令行入口共用一个运行时。"""
import os
import platform
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH)
identity = Path(os.environ["BLR_MACOS_BUILD_IDENTITY"])
metadata = [(str(identity), ".")]
for distribution in ["numpy", "scipy", "pandas", "matplotlib"]:
    metadata += copy_metadata(distribution)

a = Analysis(
    [str(root / "tools/frozen_entry.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=metadata,
    hiddenimports=["tkinter", "matplotlib.backends.backend_agg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython", "jupyter", "notebook", "pytest", "sphinx", "torch", "tensorflow",
        "sklearn", "numba", "llvmlite", "cv2", "PyQt5", "PyQt6", "PySide2", "PySide6",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="BLRWorkbench",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, argv_emulation=False, target_arch=platform.machine(),
    codesign_identity=None, entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="BLR-MEM-runtime")
app = BUNDLE(
    coll, name="BLR MEM Workbench.app", bundle_identifier="org.blrmem.workbench.preview",
    version="0.1.0",
    info_plist={
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        "LSMinimumSystemVersion": "14.0",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleGetInfoString": "BLR MEM Workbench development preview",
    },
)
