"""便携 Windows 的唯一 Python 入口；独立于外部 Python 和当前目录。"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / "app"))
    os.environ["BLR_MEM_PORTABLE_ROOT"] = str(root)
    os.environ["TCL_LIBRARY"] = str(root / "_runtime/tcl/tcl8.6")
    os.environ["TK_LIBRARY"] = str(root / "_runtime/tcl/tk8.6")
    os.environ["MPLBACKEND"] = "Agg"
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.SetProcessDPIAware()
    from frozen_entry import main as start

    return start()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 -- pythonw 无控制台，启动失败必须能让使用者看到。
        detail = traceback.format_exc()
        if sys.stderr is not None:
            sys.stderr.write(detail)
        else:
            import tkinter.messagebox

            directory = Path.home() / "BLR_MEM_outputs"
            directory.mkdir(parents=True, exist_ok=True)
            log = directory / "startup_error.txt"
            log.write_text(detail, encoding="utf-8")
            tkinter.messagebox.showerror("BLR MEM 启动失败", f"{detail.splitlines()[-1]}\n\n详细信息：{log}")
        raise SystemExit(1) from None
