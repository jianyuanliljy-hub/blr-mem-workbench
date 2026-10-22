"""轻量原生界面；后台计算通过队列更新主线程。"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .config import defaults, solver_defaults
from .gui_forms import ConfigForm
from .status import has_failures, has_warnings, result_lines
from .storage import canonical


class Workbench:
    def __init__(self, root, dimension=1, panel="generate"):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.buttons = []
        self.last_report = None
        self.last_output = None
        root.title("BLR MEM 工作台 · 秋季优化器 0.1.0.dev2")
        height = min(800, root.winfo_screenheight() - 90)
        root.geometry(f"1100x{height}")
        root.minsize(1000, min(700, height))
        style = ttk.Style(root)
        style.configure("Title.TLabel", font=("Arial", 22, "bold"))
        style.configure("Hint.TLabel", foreground="#53637a")
        shell = ttk.Frame(root, padding=16)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="BLR MEM 工作台", style="Title.TLabel").pack(anchor="w")
        ttk.Label(shell, text="1 生成数据　→　2 MEM 反演　→　3 检测与报告", style="Hint.TLabel").pack(
            anchor="w", pady=(4, 14)
        )
        controls = ttk.Frame(shell)
        controls.pack(fill="x")
        self.dimension = tk.IntVar(value=dimension)
        ttk.Label(controls, text="数据维度").pack(side="left", padx=(0, 12))
        for value, text in ((1, "一维 · 时延响应"), (2, "二维 · 速度–时延图")):
            radio = ttk.Radiobutton(
                controls, text=text, variable=self.dimension, value=value, command=self._presets
            )
            radio.pack(side="left", padx=(0, 18))
            self.buttons.append(radio)
        output = (
            Path.home() / "BLR_MEM_outputs"
            if getattr(sys, "frozen", False) or os.environ.get("BLR_MEM_PORTABLE_ROOT")
            else Path.cwd() / "blr_outputs"
        )
        self.output_root = tk.StringVar(value=str(output))
        self.dataset = tk.StringVar()
        self.result = tk.StringVar()
        self._path_field(shell, "输出位置", self.output_root)
        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill="both", expand=True, pady=(12, 8))
        data_tab = ttk.Frame(self.tabs, padding=12)
        fit_tab = ttk.Frame(self.tabs, padding=12)
        check_tab = ttk.Frame(self.tabs, padding=12)
        benchmark_tab = ttk.Frame(self.tabs, padding=12)
        for tab, text in (
            (data_tab, "1 · 生成数据"),
            (fit_tab, "2 · MEM 反演"),
            (check_tab, "3 · 检测与报告"),
            (benchmark_tab, "批量验证"),
        ):
            self.tabs.add(tab, text=text)
        ttk.Label(
            data_tab,
            text="默认保留无噪声真值。噪声比例 0.05 表示变异信号幅度的 5%，不是总通量的 5%。",
            style="Hint.TLabel",
        ).pack(anchor="w")
        self.data_config = ConfigForm(data_tab, "data", dimension)
        generation_bar = ttk.Frame(data_tab)
        generation_bar.pack(fill="x", pady=8)
        self._button(generation_bar, "生成数据与真值图", self._generate)
        ttk.Label(generation_bar, text="批量个数").pack(side="left", padx=(20, 6))
        self.count = tk.StringVar(value="10")
        ttk.Spinbox(generation_bar, from_=1, to=100000, width=7, textvariable=self.count).pack(
            side="left", padx=(0, 10)
        )
        self._button(generation_bar, "批量生成", self._batch)
        self._path_field(fit_tab, "输入数据", self.dataset, dataset=True)
        ttk.Label(
            fit_tab, text="生成的数据会自动填入这里。参数与实际误差权重会随结果保存。", style="Hint.TLabel"
        ).pack(anchor="w", pady=(4, 0))
        self.fit_config = ConfigForm(fit_tab, "fit", dimension)
        floor_bar = ttk.Frame(fit_tab)
        floor_bar.pack(fill="x", pady=5)
        ttk.Label(floor_bar, text="拟合误差下限（绝对通量）：C").pack(side="left")
        self.floor_c, self.floor_l = tk.StringVar(), tk.StringVar()
        ttk.Entry(floor_bar, textvariable=self.floor_c, width=9).pack(side="left", padx=5)
        ttk.Label(floor_bar, text="L").pack(side="left")
        ttk.Entry(floor_bar, textvariable=self.floor_l, width=9).pack(side="left", padx=5)
        self._button(floor_bar, "运行 MEM", self._fit)
        ttk.Label(
            fit_tab,
            text="有噪声数据可留空，使用观测误差。无噪声数据须填写 C、L 的正数权重；不修改数据。",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        scan_bar = ttk.Frame(fit_tab)
        scan_bar.pack(fill="x", pady=5)
        ttk.Label(scan_bar, text="可选 · 扫描网格 JSON").pack(side="left")
        self.grid = tk.StringVar()
        ttk.Entry(scan_bar, textvariable=self.grid).pack(side="left", fill="x", expand=True, padx=8)
        self._button(scan_bar, "完整扫描", self._scan)
        self._path_field(check_tab, "输入数据", self.dataset, dataset=True)
        self._path_field(check_tab, "反演结果", self.result)
        ttk.Label(
            check_tab,
            text="运行 MEM 后，结果路径会自动填入。报告包含真值对照、残差、优化历史和检测说明。\n纯扫描保留每组结果，不自动选出最优参数。",
            style="Hint.TLabel",
            wraplength=850,
        ).pack(anchor="w", pady=15)
        checks = ttk.Frame(check_tab)
        checks.pack(fill="x")
        self._button(checks, "检测生成数据", self._check_data)
        self._button(checks, "检测反演结果", self._check_fit)
        self._button(checks, "生成分析报告", self._report)
        self._button(checks, "打开最近报告", self._open_report)
        self.check_summary = tk.StringVar(value="还没有检测结果。")
        ttk.Label(check_tab, textvariable=self.check_summary, wraplength=900, justify="left").pack(
            anchor="w", pady=18
        )
        ttk.Label(
            benchmark_tab,
            text="快速检查：2 个对象，确认两种维度的完整软件流程。\n验证矩阵：144 个独立 driver 对象，覆盖形态、噪声和缺测；所有失败均保留。\n这项验证限定在合成数据范围；真实 AGN 适用性仍需独立观测验证。",
            style="Hint.TLabel",
            wraplength=850,
        ).pack(anchor="w", pady=12)
        self.profile = tk.StringVar(value="smoke")
        ttk.Radiobutton(benchmark_tab, text="快速检查（smoke）", value="smoke", variable=self.profile).pack(
            anchor="w", pady=4
        )
        ttk.Radiobutton(
            benchmark_tab, text="144 对象验证（validation）", value="validation", variable=self.profile
        ).pack(anchor="w", pady=4)
        self._button(benchmark_tab, "运行所选验证", self._benchmark)
        self._button(benchmark_tab, "查看随包验证报告", self._open_validation)
        self.status = tk.StringVar(value="就绪。生成真值与数值求解将分别验证。")
        ttk.Label(shell, textvariable=self.status).pack(anchor="w", pady=5)
        self.progress = ttk.Progressbar(shell, mode="indeterminate")
        self.progress.pack(fill="x")
        self.log = scrolledtext.ScrolledText(shell, height=5, wrap="word", font=("Courier", 10))
        self.log.pack(fill="x", pady=(8, 0))
        self._presets()
        self.tabs.select(
            {
                "generate": 0,
                "batch": 0,
                "optimize": 1,
                "scan": 1,
                "check": 2,
                "report": 2,
                "benchmark": 3,
            }.get(panel, 0)
        )
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.after(100, self._poll)

    def _button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=lambda: self._guard(command))
        button.pack(side="left", padx=(0, 7), pady=4)
        self.buttons.append(button)

    def _path_field(self, parent, text, variable, dataset=False):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text=text, width=10).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)

        def choose():
            chosen = filedialog.askdirectory(parent=self.root, title=text)
            if chosen:
                variable.set(chosen)
                if dataset:
                    self._select_dataset(chosen)

        chooser = ttk.Button(row, text="选择文件夹", command=choose)
        chooser.pack(side="left", padx=(7, 0))
        self.buttons.append(chooser)
        if variable is self.output_root:
            ttk.Button(row, text="打开文件夹", command=lambda: self._guard(self._open_output)).pack(
                side="left", padx=(7, 0)
            )

    def _select_dataset(self, path):
        from .storage import read_json

        try:
            dimension = read_json(Path(path) / "dataset.json")["dimension"]
            if dimension not in (1, 2):
                raise ValueError("数据维度必须是 1 或 2")
            if dimension != self.dimension.get():
                self.dimension.set(dimension)
                self._presets()
            self.result.set("")
            self.last_report = None
        except (ValueError, OSError, KeyError) as error:
            messagebox.showerror("无法读取数据目录", str(error), parent=self.root)

    def _presets(self):
        if self.busy:
            return
        dim = self.dimension.get()
        self.data_config.dimension = self.fit_config.dimension = dim
        self.data_config.set_value(defaults(dim))
        self.fit_config.set_value({'engine': 'autumn_normalized_joint_mem'})
        self.grid.set(
            json.dumps(
                {"alpha_map": [0.02, 0.2, 2.0]},
                ensure_ascii=False,
            )
        )

    def _guard(self, action):
        if self.busy:
            return
        try:
            action()
        except (ValueError, OSError, RuntimeError) as error:
            messagebox.showerror("参数或路径错误", str(error), parent=self.root)

    def _new_output(self, label):
        if not self.output_root.get().strip():
            raise ValueError("请先选择输出位置")
        return Path(self.output_root.get()) / (label + "_" + datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%fZ"))

    def _floor(self):
        first, second = self.floor_c.get().strip(), self.floor_l.get().strip()
        if not first and not second:
            return None
        if not first or not second:
            raise ValueError("请同时填写 C 和 L 的误差下限，或同时留空")
        return float(first), float(second)

    def _start(self, label, action):
        self.busy = True
        for button in self.buttons:
            button.state(["disabled"])
        self.status.set(label + "，计算中…")
        self.log.insert("end", label + "，开始运行。\n")
        self.progress.start(12)

        def run():
            try:
                self.events.put(("done", action()))
            except Exception:  # noqa: BLE001 -- 工作线程的意外异常也必须返回界面，防止界面永远停在计算中。
                self.events.put(("error", traceback.format_exc()))

        threading.Thread(target=run, daemon=False).start()

    def _generate(self):
        from .data import generate
        from .detector import inspect_dataset

        cfg = self.data_config.value()
        out = self._new_output(f"{cfg['dimension']}D_data")

        def action():
            generate(cfg, out)
            return {"dataset": str(out), **inspect_dataset(out)}

        self._start("生成数据", action)

    def _batch(self):
        from .data import batch_generate

        cfg = self.data_config.value()
        count, out = int(self.count.get()), self._new_output("batch")

        def action():
            result = batch_generate(cfg, count, out)
            return {"batch": str(out), "count": result["count"]}

        self._start("批量生成", action)

    def _fit(self):
        from .solver import optimize

        cfg = self.fit_config.value()
        dataset, out, floor = self.dataset.get(), self._new_output("mem"), self._floor()
        self._start("联合 MEM", lambda: {"result": str(out), **optimize(dataset, out, cfg, floor)})

    def _scan(self):
        from .scan import scan

        cfg = self.fit_config.value()
        grid, dataset, out, floor = (
            json.loads(self.grid.get()),
            self.dataset.get(),
            self._new_output("scan"),
            self._floor(),
        )

        def action():
            result = scan(dataset, out, grid, cfg, floor)
            return {
                "scan": str(out),
                "count": result["count"],
                "execution_failures": result["failures"],
                "numerical_failures": sum(has_failures(row.get("check")) for row in result["points"]),
                "warning_count": sum(has_warnings(row.get("check")) for row in result["points"]),
                "selection": result["selection"],
            }

        self._start("纯参数扫描", action)

    def _check_data(self):
        from .detector import inspect_dataset

        dataset = self.dataset.get()
        self._start("检测生成数据", lambda: inspect_dataset(dataset))

    def _check_fit(self):
        from .detector import inspect_result

        dataset, result = self.dataset.get(), self.result.get()
        self._start("检测反演结果", lambda: inspect_result(dataset, result))

    def _report(self):
        from .detector import inspect_result
        from .report import write_result_report

        dataset, result, out = self.dataset.get(), self.result.get(), self._new_output("report")
        self._start(
            "生成报告",
            lambda: {"report": write_result_report(dataset, result, out), **inspect_result(dataset, result)},
        )

    def _benchmark(self):
        from .benchmark import run_benchmark

        out, profile = self._new_output("benchmark"), self.profile.get()

        def action():
            summary = run_benchmark(out, profile, progress=lambda text: self.events.put(("progress", text)), engine='autumn_normalized_joint_mem')
            return {
                "benchmark": str(out),
                "report": str(out / "report.html"),
                "planned": summary["planned"],
                "groups": summary["groups"],
                "execution_failures": summary["execution_failures"],
            }

        self._start("软件验证矩阵", action)

    def _open_report(self):
        if self.last_report:
            webbrowser.open(Path(self.last_report).resolve().as_uri())
        else:
            messagebox.showinfo("报告", "先生成分析报告或运行软件验证。", parent=self.root)

    def _open_validation(self):
        root = (
            Path(sys.executable).parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[2]
        )
        if sys.platform == "darwin" and getattr(sys, "frozen", False):
            root = root.parents[2]
        if os.environ.get("BLR_MEM_PORTABLE_ROOT"):
            root = Path(os.environ["BLR_MEM_PORTABLE_ROOT"])
        path = root / "validation/report.html"
        if not path.exists():
            path = root / "evidence/validation_20261021_v1/report.html"
        if path.exists():
            webbrowser.open(path.resolve().as_uri())
        else:
            messagebox.showinfo("验证报告", "使用说明中的验证结果链接包含本次 144 例验证。", parent=self.root)

    def _open_output(self):
        path = Path(self.output_root.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])

    def _poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    self.status.set(value)
                    self.log.insert("end", value + "\n")
                    continue
                self.busy = False
                self.progress.stop()
                for button in self.buttons:
                    button.state(["!disabled"])
                if kind == "error":
                    reason = value.strip().splitlines()[-1]
                    self.status.set("运行失败：" + reason[:140])
                    self.log.insert("end", value + "\n")
                else:
                    if isinstance(value, dict):
                        if "dataset" in value:
                            self.dataset.set(value["dataset"])
                            self.result.set("")
                            self.last_report = None
                            self.last_output = value["dataset"]
                        if "result" in value:
                            self.result.set(value["result"])
                            self.last_report = None
                            self.last_output = value["result"]
                        if "report" in value:
                            self.last_report = value["report"]
                        lines = result_lines(value)
                        if lines:
                            self.check_summary.set("\n".join(lines))
                    warning = has_failures(value) or has_warnings(value)
                    self.status.set(
                        "运行结束，有未通过项或警告。检测摘要与报告已保留具体原因。"
                        if warning
                        else "运行结束。结果已保存，可以继续下一步。"
                    )
                    self.log.insert("end", canonical(value))
                self.log.see("end")
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _close(self):
        if self.busy:
            messagebox.showinfo(
                "计算仍在运行", "请等待当前任务结束后关闭，避免中断数值求解。", parent=self.root
            )
            return
        self.root.destroy()


def main(dimension=1, panel="generate"):
    root = tk.Tk()
    Workbench(root, dimension, panel)
    root.mainloop()
