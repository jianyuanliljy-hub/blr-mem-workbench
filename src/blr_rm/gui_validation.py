"""在真实 Tk 主事件循环中检查两维操作链；不替代人工视觉检查。"""

from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path

from .config import defaults
from .gui import Workbench
from .storage import save_json


def _run_dimension(dimension, artifacts):
    root = tk.Tk()
    application = Workbench(root, dimension)
    if getattr(sys, "frozen", False) or os.environ.get("BLR_MEM_PORTABLE_ROOT"):
        assert Path(application.output_root.get()) == Path.home() / "BLR_MEM_outputs"
    application.output_root.set(str(artifacts / f"{dimension}D"))
    cfg = {**defaults(dimension), "noise_fraction": 0.05}
    application.data_config.set_value(cfg)
    application.data_config.variables["noise_fraction"][0].set("0.05")
    assert application.data_config.value() == cfg
    application.data_config.variables["seed"][0].set("invalid seed")
    try:
        application.data_config.value()
    except ValueError as error:
        assert "整数" in str(error)
    else:
        raise AssertionError("无效表单值未被拒绝")
    application.data_config.variables["seed"][0].set(str(cfg["seed"]))
    application.data_config._apply(cfg)
    assert application.data_config.value() == cfg
    errors = []
    stage = 0

    def generated():
        assert (Path(application.dataset.get()) / "dataset.json").exists()

    def optimized():
        assert (Path(application.result.get()) / "result.json").exists()

    def checked():
        assert "运行失败" not in application.status.get()
        assert '"forward_consistency": "PASS"' in application.log.get("1.0", "end")
        assert '"truth_metrics": {' in application.log.get("1.0", "end")
        assert "最终一阶条件" in application.check_summary.get()

    def reported():
        assert application.last_report and Path(application.last_report).is_file()

    def invalid_input():
        application.dataset.set(str(artifacts / "不存在的数据"))
        application._check_data()

    def recovered():
        assert "运行失败" in application.status.get()
        assert not application.busy

    tasks = [
        ("generation", application._generate, generated),
        ("inversion", application._fit, optimized),
        ("check", application._check_fit, checked),
        ("report", application._report, reported),
        ("error_returns_to_idle", invalid_input, recovered),
    ]
    statuses = {"dimension": dimension, "forms_roundtrip_and_invalid_input": "PASS"}

    def advance():
        nonlocal stage
        try:
            if application.busy:
                root.after(30, advance)
                return
            if stage:
                name, _, check = tasks[stage - 1]
                check()
                statuses[name] = "PASS"
                print(f"GUI {dimension}D {name}: PASS", flush=True)
            if stage == len(tasks):
                root.destroy()
                return
            _, action, _ = tasks[stage]
            stage += 1
            action()
            root.after(30, advance)
        except Exception as error:  # noqa: BLE001 -- Tk 回调异常需传回主调用方。
            errors.append(error)
            root.destroy()

    def timed_out():
        errors.append(TimeoutError(f"GUI {dimension}D 主事件循环检查超时"))
        root.destroy()

    root.after(60_000, timed_out)
    root.after(250, advance)
    root.mainloop()
    if errors:
        raise errors[0]
    if len(statuses) != len(tasks) + 2:
        raise RuntimeError(f"GUI {dimension}D 检查在全部步骤完成前结束")
    return statuses


def run_gui_flow(receipt):
    receipt = Path(receipt)
    if receipt.exists():
        raise FileExistsError(str(receipt))
    artifacts = Path(tempfile.mkdtemp(prefix="BLR GUI 中文路径 "))
    completed = [_run_dimension(dimension, artifacts) for dimension in (1, 2)]
    receipt.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 1,
        "tests": completed,
        "artifacts": str(artifacts),
        "event_loop": "NATIVE_TK_MAINLOOP",
        "unicode_and_space_output_path": "PASS",
        "visual_review": "NOT_ASSESSED_BY_AUTOMATION",
    }
    save_json(receipt, result)
    return result
