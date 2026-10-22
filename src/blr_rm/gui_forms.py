"""常用参数表单；高级参数与文件预设共用同一份配置。"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .config import resolved_generator, resolved_solver
from .storage import canonical

FAMILIES = {
    "gaussian": "单峰高斯 · Gaussian",
    "double_gaussian": "双峰高斯 · Double Gaussian",
    "top_hat": "平顶 · Top hat",
    "tilted_gaussian": "倾斜高斯 · Tilted Gaussian",
    "two_blobs": "双团块 · Two blobs",
}


class ConfigForm(ttk.Frame):
    def __init__(self, parent, kind, dimension):
        super().__init__(parent)
        self.kind = kind
        self.dimension = dimension
        self.values = {}
        self.variables = {}
        self.pack(fill="x", pady=8)

    def set_value(self, value):
        dimension = value.get("dimension", self.dimension)
        if self.kind == "data":
            value = resolved_generator(value, dimension)
        else:
            value = resolved_solver(dimension, value)
        self.dimension, self.values = dimension, value.copy()
        self.variables.clear()
        for child in self.winfo_children():
            child.destroy()
        if self.kind == "data":
            fields = [
                ("family", "响应形态", str),
                ("seed", "随机种子 · Seed", int),
                ("duration_days", "观测时长 / day", float),
                ("cadence_days", "采样间隔 / day", float),
                ("delay_max_days", "最大时延 / day", float),
                ("delay_step_days", "时延步长 / day", float),
                ("noise_fraction", "噪声比例 · 0 = 无噪声", float),
                ("missing_fraction", "发射线缺测比例 · 0–1", float),
            ]
            if dimension == 2:
                fields += [
                    ("n_velocity", "速度通道数", int),
                    ("velocity_max_kms", "最大速度 / km s⁻¹", float),
                ]
        else:
            fields = (
                [
                    ("alpha", "熵权重 α", float),
                    ("stiffness_weight", "响应相对权重 W", float),
                    ("max_iterations", "最大迭代次数", int),
                ]
                if dimension == 1 and value['engine'] != 'autumn_normalized_joint_mem'
                else [
                    ("alpha_map", "响应熵权重 α map", float),
                    ("alpha_c", "连续谱熵权重 α C", float),
                    ("alpha_lbg", "背景熵权重 α bg", float),
                    ("smoothness_ratio", "时延/速度平滑比", float),
                ]
            )
        if self.kind != 'data' and value['engine'] == 'autumn_normalized_joint_mem':
            fields += [('gradient_backend', '梯度 manual / jax', str),
                       ('jax_device', '设备 cpu / gpu / auto', str),
                       ('jax_jit', 'JIT: true / false', lambda s: json.loads(s.lower())),
                       ('use_numba', 'Numba: true / false', lambda s: json.loads(s.lower()))]
        for index, (key, label, convert) in enumerate(fields):
            row, column = divmod(index, 2)
            cell = ttk.Frame(self)
            cell.grid(row=row, column=column, sticky="ew", padx=(0, 20), pady=4)
            ttk.Label(cell, text=label, width=25).pack(side="left")
            variable = tk.StringVar(value=FAMILIES[value[key]] if key == "family" else str(value[key]))
            if key == "family":
                allowed = list(FAMILIES) if dimension == 2 else ["gaussian", "double_gaussian", "top_hat"]
                ttk.Combobox(
                    cell,
                    textvariable=variable,
                    values=[FAMILIES[k] for k in allowed],
                    state="readonly",
                    width=23,
                ).pack(side="left", fill="x", expand=True)
            else:
                ttk.Entry(cell, textvariable=variable, width=16).pack(side="left", fill="x", expand=True)
            self.variables[key] = (variable, convert, label)
        self.columnconfigure((0, 1), weight=1)
        bar = ttk.Frame(self)
        bar.grid(row=(len(fields) + 1) // 2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        for label, command in (
            ("高级参数…", self._advanced),
            ("载入预设…", self._load),
            ("保存预设…", self._save),
        ):
            ttk.Button(bar, text=label, command=command).pack(side="left", padx=(0, 8))

    def value(self):
        value = self.values.copy()
        for key, (variable, convert, label) in self.variables.items():
            try:
                value[key] = (
                    next(k for k, v in FAMILIES.items() if v == variable.get())
                    if key == "family"
                    else convert(variable.get().strip())
                )
            except (ValueError, StopIteration):
                raise ValueError(f"{label}：请填写{'整数' if convert is int else '有效数字'}") from None
        return (
            resolved_generator(value, self.dimension)
            if self.kind == "data"
            else resolved_solver(self.dimension, value)
        )

    def _apply(self, value):
        if self.kind == "data" and value.get("dimension", self.dimension) != self.dimension:
            raise ValueError("预设维度与界面不同，请先切换顶部的一维 / 二维选项")
        self.set_value(value)

    def _load(self):
        path = filedialog.askopenfilename(parent=self, title="载入参数预设", filetypes=[("JSON", "*.json")])
        if path:
            try:
                value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
                if not isinstance(value, dict):
                    raise ValueError("预设必须是 JSON 对象")  # noqa: TRY004
                self._apply(value)
            except (ValueError, OSError) as error:
                messagebox.showerror("无法载入预设", str(error), parent=self)

    def _save(self):
        try:
            value = self.value()
        except ValueError as error:
            messagebox.showerror("参数错误", str(error), parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="保存参数预设",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            confirmoverwrite=True,
        )
        if path:
            try:
                Path(path).write_text(canonical(value), encoding="utf-8")
            except OSError as error:
                messagebox.showerror("无法保存预设", str(error), parent=self)

    def _advanced(self):
        try:
            current = self.value()
        except ValueError as error:
            messagebox.showerror("参数错误", str(error), parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("完整参数 · 修改后应用到表单")
        dialog.geometry("640x570")
        dialog.transient(self.winfo_toplevel())
        editor = scrolledtext.ScrolledText(dialog, wrap="none", font=("Courier", 11))
        editor.pack(fill="both", expand=True, padx=14, pady=14)
        editor.insert("1.0", canonical(current))

        def apply():
            try:
                value = json.loads(editor.get("1.0", "end"))
                if not isinstance(value, dict):
                    raise ValueError("参数必须是 JSON 对象")  # noqa: TRY004
                self._apply(value)
            except ValueError as error:
                messagebox.showerror("参数错误", str(error), parent=dialog)
                return
            dialog.destroy()

        ttk.Button(dialog, text="应用参数", command=apply).pack(pady=(0, 14))
        dialog.grab_set()
