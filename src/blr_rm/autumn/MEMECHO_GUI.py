"""MEMECHO 2-D desktop front end. Run this source file before packaging."""

from __future__ import annotations

import csv
import importlib.util
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
if getattr(sys, 'frozen', False):
    RESOURCE_DIR = RESOURCE_DIR / 'autumn'
SOLVER_PATH = RESOURCE_DIR / "023_0821.py"

EXPECTED_FORMATS = {
    "C": "time_days,continuum_flux\n0.0,1.234\n1.0,1.198",
    "C error": "time_days,continuum_error\n0.0,0.025\n1.0,0.025",
    "L": "time_days,flux_-3000_kms,...,flux_3000_kms\n0.0,0.51,...,0.52",
    "L error": "time_days,error_-3000_kms,...,error_3000_kms\n0.0,0.01,...,0.01",
}

FILE_DISPLAY_NAMES = {
    "C": "C data",
    "C error": "C error data",
    "L": "L data",
    "L error": "L error data",
}


class MemechoGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MEMECHO 2026 Autumn - Normalized objective trial")
        self.geometry("1080x820")
        self.minsize(960, 700)
        self.files = {key: tk.StringVar() for key in EXPECTED_FORMATS}
        self.basic = {
            "C cadence (days)": tk.StringVar(value="2.0"),
            "C duration (days)": tk.StringVar(value="224.0"),
            "C S/N": tk.StringVar(value="40.0"),
            "L cadence (days)": tk.StringVar(value="2.0"),
            "L duration (days)": tk.StringVar(value="180.0"),
            "L S/N": tk.StringVar(value="20.0"),
            "Season gap (days)": tk.StringVar(value="0.0"),
            "Max delay (days)": tk.StringVar(value="40.0"),
            "Instrument sigma (days)": tk.StringVar(value="2.0"),
            "Delay pixels": tk.StringVar(value="40"),
        }
        self.advanced = {
            "MEM_ALPHA_MAP": tk.StringVar(value="0.2"),
            "MEM_ALPHA_C": tk.StringVar(value="1200.0"),
            "MEM_ALPHA_LBG": tk.StringVar(value="0.02"),
            "MEM_MAX_INNER_ITER": tk.StringVar(value="800"),
            "MEM_MAX_DEFAULT_ITER": tk.StringVar(value="1000"),
            "MEM_DEFAULT_TOLERANCE": tk.StringVar(value="1e-2"),
            "MEM_DEFAULT_DAMPING": tk.StringVar(value="0.5"),
            "MEM_TEST_THRESHOLD": tk.StringVar(value="1e-5"),
            "MEM_Q_GRADIENT_THRESHOLD": tk.StringVar(value="3e-3"),
            "MEM_SMOOTHNESS_RATIO": tk.StringVar(value="1.0"),
            "MEM_ADAMS_STEPS": tk.StringVar(value="40"),
            "MEM_ADAMS_STEP_SIZE": tk.StringVar(value="0.03"),
            "MEM_GAP_GP_TIMESCALE_DAYS": tk.StringVar(value="auto"),
            "MEM_GAP_CURVATURE_WEIGHT": tk.StringVar(value="10.0"),
        }
        self.font_family = tk.StringVar(value="DejaVu Sans")
        self.backend = tk.StringVar(value="manual")
        # 两个后端各自保存加速选择，切换梯度时不会互相覆盖。
        self.manual_numba = tk.BooleanVar(value=False)
        self.jax_jit = tk.BooleanVar(value=False)
        self.jax_device = tk.StringVar(value='cpu')
        self.jax_persistent_cache = tk.BooleanVar(value=False)
        self.square_pixels = tk.BooleanVar(value=False)
        self.use_adam = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Ready")
        self.process = None
        self.stop_requested = False
        self._basic_defaults = {key: value.get() for key, value in self.basic.items()}
        self._advanced_defaults = {key: value.get() for key, value in self.advanced.items()}
        self._build()
        self._auto_fill_data_files()

    def reset_defaults(self):
        if self.process is not None or self.status.get() == 'Running':
            return
        for key,value in self._basic_defaults.items():
            self.basic[key].set(value)
        for key,value in self._advanced_defaults.items():
            self.advanced[key].set(value)
        self.backend.set('manual')
        self.manual_numba.set(False)
        self.jax_jit.set(False)
        self.jax_device.set('cpu')
        self.jax_persistent_cache.set(False)
        self.use_adam.set(True)
        self.square_pixels.set(False)
        self._backend_changed()
        self._toggle_pixels()
        self.status.set('Defaults restored; input files retained')

    def _auto_fill_data_files(self):
        """用程序同目录 data 中的标准文件预填输入框，不锁定用户选择。"""
        data_dir = APP_DIR / "data"
        preferred_names = {
            "C": "C_data.csv",
            "C error": "C_err.csv",
            "L": "L_data.csv",
            "L error": "L_err.csv",
        }
        if not data_dir.is_dir():
            return

        # Windows 文件名通常不区分大小写；这里显式兼容不同大小写。
        csv_by_lower_name = {
            path.name.lower(): path.resolve()
            for path in data_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".csv"
        }
        detected = []
        for key, filename in preferred_names.items():
            path = csv_by_lower_name.get(filename.lower())
            if path is not None:
                self.files[key].set(str(path))
                detected.append(filename)
        if detected:
            self.status.set("Default data files detected")
            self.log.insert(
                "end",
                "Automatically selected from the data folder: "
                + ", ".join(detected) + "\n"
                + "You can still edit each path or use Browse.\n",
            )

    def _build(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        appearance = ttk.LabelFrame(outer, text="Appearance", padding=8)
        appearance.pack(fill="x")
        ttk.Button(appearance, text="Restore defaults", command=self.reset_defaults).pack(side="right")
        ttk.Label(appearance, text="Global font family").pack(side="left")
        fonts = ("DejaVu Sans", "Arial", "Times New Roman", "Microsoft YaHei",
                 "SimHei", "Noto Sans CJK SC")
        ttk.Combobox(appearance, textvariable=self.font_family, values=fonts,
                     width=25).pack(side="left", padx=8)
        ttk.Label(appearance, text="Use the exact installed font-family name.").pack(side="left")

        files_box = ttk.LabelFrame(outer, text="Observation CSV files", padding=8)
        files_box.pack(fill="x", pady=(10, 0))
        for row, key in enumerate(EXPECTED_FORMATS):
            ttk.Label(files_box, text=FILE_DISPLAY_NAMES[key], width=14).grid(
                row=row, column=0, sticky="w"
            )
            ttk.Entry(files_box, textvariable=self.files[key]).grid(
                row=row, column=1, sticky="ew", padx=5, pady=2
            )
            ttk.Button(files_box, text="Browse", command=lambda k=key: self.pick_file(k)).grid(
                row=row, column=2, padx=3
            )
            ttk.Button(files_box, text="Details / preview",
                       command=lambda k=key: self.preview(k)).grid(row=row, column=3, padx=3)
        files_box.columnconfigure(1, weight=1)

        base_box = ttk.LabelFrame(outer, text="Data and delay settings", padding=8)
        base_box.pack(fill="x", pady=(10, 0))
        for index, (label, variable) in enumerate(self.basic.items()):
            row, pair = divmod(index, 2)
            column = pair * 2
            ttk.Label(base_box, text=label).grid(row=row, column=column, sticky="w", padx=5, pady=3)
            ttk.Entry(base_box, textvariable=variable, width=16).grid(
                row=row, column=column + 1, sticky="w", padx=5, pady=3
            )
        ttk.Checkbutton(
            base_box, text="Square map: delay pixels = number of velocity channels",
            variable=self.square_pixels, command=self._toggle_pixels
        ).grid(row=5, column=0, columnspan=4, sticky="w", padx=5, pady=3)
        ttk.Label(
            base_box,
            text="Cadence/duration/S/N/gap/sigma describe and validate input data; errors in CSV set chi-square weights."
        ).grid(row=6, column=0, columnspan=4, sticky="w", padx=5, pady=3)

        method = ttk.LabelFrame(outer, text="Optimization", padding=8)
        method.pack(fill="x", pady=(10, 0))
        ttk.Radiobutton(method, text="Manual gradient", variable=self.backend,
                        value="manual", command=self._backend_changed).pack(side="left")
        ttk.Radiobutton(method, text="JAX automatic differentiation", variable=self.backend,
                        value="jax", command=self._backend_changed).pack(side="left", padx=15)
        self.numba_button = ttk.Checkbutton(
            method, text="Use Numba", variable=self.manual_numba
        )
        self.numba_button.pack(side="left", padx=(15, 5))
        self.jit_button = ttk.Checkbutton(
            method, text="Use JAX JIT", variable=self.jax_jit,
            command=self._backend_changed
        )
        self.jit_button.pack(side="left", padx=5)
        self.jax_cache_button = ttk.Checkbutton(
            method, text="Reuse JIT disk cache", variable=self.jax_persistent_cache
        )
        self.jax_cache_button.pack(side="left", padx=5)
        ttk.Combobox(method, textvariable=self.jax_device, values=('cpu', 'gpu', 'auto'),
                     state='readonly', width=6).pack(side='left', padx=4)
        ttk.Checkbutton(method, text="Adam warm-up", variable=self.use_adam).pack(side="left")
        ttk.Button(method, text="Advanced settings...", command=self.open_advanced).pack(side="right")

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=10)
        self.run_button = ttk.Button(actions, text="Validate and run", command=self.run)
        self.run_button.pack(side="left")
        self.stop_button = ttk.Button(
            actions, text="Stop optimization", command=self.stop, state="disabled"
        )
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(actions, text="Open example format", command=self.show_all_formats).pack(
            side="left"
        )
        ttk.Label(actions, textvariable=self.status).pack(side="right")

        self.log = tk.Text(outer, height=18, wrap="word")
        self.log.pack(fill="both", expand=True)
        self._toggle_pixels()
        self._backend_changed()

    def _toggle_pixels(self):
        pass

    def _backend_changed(self):
        manual = self.backend.get() == "manual"
        self.numba_button.configure(state="normal" if manual else "disabled")
        self.jit_button.configure(state="disabled" if manual else "normal")
        self.jax_cache_button.configure(
            state="disabled" if manual or not self.jax_jit.get() else "normal"
        )

    def pick_file(self, key):
        path = filedialog.askopenfilename(
            title=f"Select {key} CSV", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if path:
            self.files[key].set(path)

    def preview(self, key):
        path_text = self.files[key].get().strip()
        actual = "No file selected."
        if path_text and Path(path_text).is_file():
            with open(path_text, "r", encoding="utf-8-sig", errors="replace") as stream:
                actual = "".join(stream.readline() for _ in range(6)).strip()
        messagebox.showinfo(
            f"{key} format",
            f"Expected example:\n\n{EXPECTED_FORMATS[key]}\n\nSelected-file preview:\n\n{actual}"
        )

    def show_all_formats(self):
        messagebox.showinfo(
            "CSV examples", "\n\n".join(f"[{key}]\n{value}" for key, value in EXPECTED_FORMATS.items())
        )

    def open_advanced(self):
        window = tk.Toplevel(self)
        window.title("Advanced MEM settings")
        window.transient(self)
        window.grab_set()
        labels = {
            "MEM_ALPHA_MAP": "alpha map", "MEM_ALPHA_C": "alpha C",
            "MEM_ALPHA_LBG": "alpha L_bg", "MEM_MAX_INNER_ITER": "inner iterations",
            "MEM_MAX_DEFAULT_ITER": "outer/default iterations",
            "MEM_DEFAULT_TOLERANCE": "default relative tolerance",
            "MEM_DEFAULT_DAMPING": "default damping", "MEM_TEST_THRESHOLD": "Horne TEST threshold",
            "MEM_Q_GRADIENT_THRESHOLD": "relative Q-gradient threshold",
            "MEM_SMOOTHNESS_RATIO": "2-D default smoothness ratio",
            "MEM_ADAMS_STEPS": "Adam steps", "MEM_ADAMS_STEP_SIZE": "Adam step size",
            "MEM_GAP_GP_TIMESCALE_DAYS": "GP timescale days (or auto)",
            "MEM_GAP_CURVATURE_WEIGHT": "gap curvature weight",
        }
        for row, (key, variable) in enumerate(self.advanced.items()):
            ttk.Label(window, text=labels[key]).grid(row=row, column=0, sticky="w", padx=10, pady=3)
            ttk.Entry(window, textvariable=variable, width=22).grid(row=row, column=1, padx=10, pady=3)
        ttk.Button(window, text="Done", command=window.destroy).grid(
            row=len(self.advanced), column=0, columnspan=2, pady=10
        )

    def _validate_files(self):
        paths = {key: Path(variable.get().strip()) for key, variable in self.files.items()}
        missing = [key for key, path in paths.items() if not path.is_file()]
        if missing:
            raise ValueError("Missing files: " + ", ".join(missing))
        with open(paths["C"], "r", encoding="utf-8-sig", newline="") as stream:
            c_header = next(csv.reader(stream))
        with open(paths["C error"], "r", encoding="utf-8-sig", newline="") as stream:
            ce_header = next(csv.reader(stream))
        with open(paths["L"], "r", encoding="utf-8-sig", newline="") as stream:
            l_header = next(csv.reader(stream))
        with open(paths["L error"], "r", encoding="utf-8-sig", newline="") as stream:
            le_header = next(csv.reader(stream))
        if c_header != ["time_days", "continuum_flux"]:
            raise ValueError("C header must be: time_days,continuum_flux")
        if ce_header != ["time_days", "continuum_error"]:
            raise ValueError("C error header must be: time_days,continuum_error")
        flux_columns = [name for name in l_header[1:] if "flux" in name.lower()]
        error_columns = [name for name in le_header[1:] if "error" in name.lower()]
        if not l_header or l_header[0] != "time_days" or not flux_columns:
            raise ValueError("L first column must be time_days followed by flux_<velocity> columns")
        if not le_header or le_header[0] != "time_days" or len(error_columns) != len(flux_columns):
            raise ValueError("L error columns must match the number of L flux columns")
        return paths, len(flux_columns)

    def _validated_numbers(self):
        values = {}
        for label, variable in self.basic.items():
            value = float(variable.get())
            if value < 0 or (label not in ("Season gap (days)", "Instrument sigma (days)") and value == 0):
                raise ValueError(f"{label} must be positive (season gap may be zero)")
            values[label] = value
        if values["Season gap (days)"] >= values["C duration (days)"]:
            raise ValueError("Season gap must be shorter than C duration")
        return values

    def _save_input_overview(self, paths, values, output_dir):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        font_name = self.font_family.get().strip()
        if font_name:
            plt.rcParams["font.family"] = font_name
        plt.rcParams["axes.unicode_minus"] = False
        C = np.loadtxt(paths["C"], delimiter=",", skiprows=1, ndmin=2)
        C_err = np.loadtxt(paths["C error"], delimiter=",", skiprows=1, ndmin=2)
        L = np.loadtxt(paths["L"], delimiter=",", skiprows=1, ndmin=2)
        L_err = np.loadtxt(paths["L error"], delimiter=",", skiprows=1, ndmin=2)
        if not np.allclose(C[:, 0], C_err[:, 0]):
            raise ValueError("C and C-error time columns do not match")
        if not np.allclose(L[:, 0], L_err[:, 0]):
            raise ValueError("L and L-error time columns do not match")
        c_dt = float(np.min(np.diff(C[:, 0])))
        l_dt = float(np.min(np.diff(L[:, 0])))
        c_sn = float(np.std(C[:, 1]) / np.median(C_err[:, 1]))
        l_sn = float(np.std(L[:, 1:]) / np.median(L_err[:, 1:]))
        self.log.insert(
            "end",
            f"Input check: inferred C cadence={c_dt:.6g} d, requested={values['C cadence (days)']:.6g} d; "
            f"estimated variability/error={c_sn:.6g}, entered S/N={values['C S/N']:.6g}\n"
        )
        self.log.insert(
            "end",
            f"Input check: inferred L cadence={l_dt:.6g} d, requested={values['L cadence (days)']:.6g} d; "
            f"estimated variability/error={l_sn:.6g}, entered S/N={values['L S/N']:.6g}\n"
        )
        fig, axes = plt.subplots(2, 1, figsize=(14, 8), constrained_layout=True)
        axes[0].errorbar(C[:, 0], C[:, 1], yerr=C_err[:, 1], fmt="x",
                         linestyle="none", markersize=3, color="navy")
        axes[0].set(title="Input continuum C(t)", xlabel="Time (days)", ylabel="Continuum flux")
        axes[0].grid(alpha=0.25)
        total_l = np.sum(L[:, 1:], axis=1)
        total_l_err = np.sqrt(np.sum(L_err[:, 1:] ** 2, axis=1))
        axes[1].errorbar(L[:, 0], total_l, yerr=total_l_err, fmt="x",
                         linestyle="none", markersize=3, color="navy")
        axes[1].set(title="Input integrated line L(t)", xlabel="Time (days)", ylabel="Integrated line flux")
        axes[1].grid(alpha=0.25)
        fig.savefig(output_dir / "input_C_L_with_errorbars.png", dpi=220, bbox_inches="tight")
        plt.close(fig)

    def run(self):
        try:
            paths, velocity_channels = self._validate_files()
            values = self._validated_numbers()
            if self.backend.get() == "jax" and importlib.util.find_spec("jax") is None:
                raise ValueError("JAX mode selected, but the jax package is not installed in this Python environment")
            tau_pixels = velocity_channels if self.square_pixels.get() else int(values["Delay pixels"])
            if tau_pixels < 2:
                raise ValueError("Delay pixels must be at least 2")
            output_dir = paths["C"].parent / (
                "MEM_output_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            )
            output_dir.mkdir(parents=False, exist_ok=False)
            configuration_rows = [
                ("backend", self.backend.get()),
                ("manual_numba", self.manual_numba.get()),
                ("jax_jit", self.jax_jit.get()),
                ("jax_persistent_cache", self.jax_persistent_cache.get()),
                ("font_family", self.font_family.get().strip()),
                ("velocity_channels", velocity_channels),
                ("delay_pixels", tau_pixels),
            ]
            configuration_rows.extend((f"file_{key}", path) for key, path in paths.items())
            configuration_rows.extend((label, value) for label, value in values.items())
            configuration_rows.extend((key, variable.get().strip()) for key, variable in self.advanced.items())
            with open(output_dir / "run_configuration.csv", "w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["parameter", "value"])
                writer.writerows(configuration_rows)
            env = os.environ.copy()
            env.update({
                "MEM_CONTINUUM_CSV": str(paths["C"]),
                "MEM_CONTINUUM_ERR_CSV": str(paths["C error"]),
                "MEM_LINE_CSV": str(paths["L"]),
                "MEM_LINE_ERR_CSV": str(paths["L error"]),
                "MEM_OUTPUT_DIR": str(output_dir),
                "MEM_FONT_FAMILY": self.font_family.get().strip(),
                "MEM_DELAY_MAX_DAYS": str(values["Max delay (days)"]),
                "MEM_TAU_PIXELS": str(tau_pixels),
                "MEM_GRADIENT_BACKEND": self.backend.get(),
                "MEM_JAX_DEVICE": self.jax_device.get(),
                "MEM_USE_NUMBA": "1" if self.backend.get() == "manual" and self.manual_numba.get() else "0",
                "MEM_USE_JAX_JIT": "1" if self.backend.get() == "jax" and self.jax_jit.get() else "0",
                "MEM_JAX_CACHE_DIR": str(APP_DIR / ".jax_compilation_cache")
                if (self.backend.get() == "jax" and self.jax_jit.get()
                    and self.jax_persistent_cache.get()) else "",
                # 正式求解已有严格的手写/JAX 检查；不再额外运行旧 Autograd
                # 的整轮对照，否则会明显增加大图问题的结束等待时间。
                "MEM_AUTODIFF_COMPARE": "0",
                "MEM_DO_ADAMS_WARMUP": "1" if self.use_adam.get() else "0",
                "MPLBACKEND": "Agg",
                "MEM_LOG_FILE": str(output_dir / 'solver.log'),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
            })
            env.update({key: variable.get().strip() for key, variable in self.advanced.items()})
            self.log.delete("1.0", "end")
            self.log.insert("end", f"Output directory: {output_dir}\n")
            self.log.insert("end", f"Map pixels: {velocity_channels} velocity x {tau_pixels} delay\n")
            self.log.insert("end", f"Instrument broadening sigma (metadata): {values['Instrument sigma (days)']} d\n")
            self._save_input_overview(paths, values, output_dir)
            self.status.set("Running")
            self.stop_requested = False
            self.run_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            threading.Thread(target=self._run_process, args=(env,), daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Cannot run", str(exc))

    def _run_process(self, env):
        try:
            command = [sys.executable, '--autumn-solver'] if getattr(sys, 'frozen', False) else [sys.executable, str(SOLVER_PATH)]
            log_path = Path(env['MEM_LOG_FILE'])
            with log_path.open('a',encoding='utf-8') as capture:
                self.process = subprocess.Popen(
                    command, cwd=str(APP_DIR), env=env,
                    stdout=capture, stderr=capture,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
                if self.stop_requested:
                    self.process.terminate()
                with log_path.open('r',encoding='utf-8',errors='replace') as reader:
                    while True:
                        line=reader.readline()
                        if line:
                            self.after(0,self._append_log,line)
                        elif self.process.poll() is not None:
                            break
                        else:
                            time.sleep(0.1)
                code = self.process.wait()
            self.after(0, self._finished, code)
        except Exception as exc:
            self.after(0, self._append_log, f"\nLauncher error: {exc}\n")
            self.after(0, self._finished, -1)

    def _append_log(self, text):
        self.log.insert("end", text)
        self.log.see("end")

    def stop(self):
        process = self.process
        if process is None:
            if self.status.get() == "Running":
                self.stop_requested = True
                self.status.set("Stopping")
                self.stop_button.configure(state="disabled")
            return
        if process.poll() is not None:
            return
        self.stop_requested = True
        self.status.set("Stopping")
        self.stop_button.configure(state="disabled")
        self._append_log("\nStop requested. Terminating the current optimization...\n")
        threading.Thread(target=self._terminate_process, args=(process,), daemon=True).start()

    def _terminate_process(self, process):
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        except Exception as exc:
            self.after(0, self._append_log, f"Stop error: {exc}\n")

    def _finished(self, code):
        was_stopped = self.stop_requested
        self.process = None
        self.run_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        if was_stopped:
            self.status.set("Stopped — ready to run again")
            self._append_log("Optimization stopped. Parameters can be changed and run again.\n")
        else:
            self.status.set("Completed" if code == 0 else f"Failed (exit {code})")
        if code == 0 and not was_stopped:
            messagebox.showinfo("MEMECHO", "Reconstruction completed. Results were saved beside the C input file.")


def main():
    MemechoGUI().mainloop()


if __name__ == "__main__":
    main()
