# BLR MEM Workbench

Version **0.1.0.dev2** — autumn MEM integration preview.

[简体中文](#简体中文) · [English](#english) · [References](docs/REFERENCES.md)

## 简体中文

一维时延响应和二维速度–时延图的最大熵工作台。保留原仓库命名和 `1D/`、`2D/` 配置目录；默认优化器已替换为作者 **MEMECHO_2026秋季试用版** 的目标函数与求解流程，不再默认调用原 GitHub 反演器。详细变更见 [秋季版接入说明](docs/AUTUMN_INTEGRATION_ZH.md)。

### Windows 程序

在 [Windows 构建记录](https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions/workflows/windows-build.yml) 中选择 `chris-update` 最新的**成功**运行，下载 `BLR-RM-Windows-preview` artifact，完整解压内部 ZIP。旧 `dev1` Release 不是此版程序。

双击 `BLRWorkbench.exe`，或使用以下独立入口。所有 EXE 共用同目录 `_internal/`，**不能只复制单个 EXE**。无需另装 Python、JAX 或 Numba。首次启用 JIT/Numba 会编译，小数据不保证更快。

| 入口 | 功能 |
|---|---|
| `GenerateData.exe` | 单组模拟数据、独立保存无噪声真值和真实时延图 |
| `BatchGenerate.exe` | 批量独立样本、配置和数据身份检查、续跑 |
| `MEMOptimizer.exe` | 秋季版 MEM，手写梯度/可选 Numba，或 JAX/可选 JIT |
| `Detector.exe` | 独立前向模型、梯度/收敛检查、默认参数或纯扫描 |
| `Analysis.exe` | 拟合、残差、真值误差和 HTML/CSV 报告 |

`1D/`、`2D/` 内的同名 `.cmd` 预选维度。`blr-rm.exe` 是命令行入口。

GPU 选项为 `cpu` / `auto` / `gpu`。当前原生 Windows 包提供 **CPU JAX**；`gpu` 不可用时明确报错，不伪称 GPU 加速。`auto` 可回退 CPU。兼容的 Linux/WSL JAX CUDA 环境可从源码使用 GPU；此发布尚无 GPU 实测。macOS 构建也未作为本轮 Windows 验收结果。

### 源码运行

建议独立 Python 3.13 环境（需 Tk）。在仓库根目录：

```bash
python -m pip install ".[test,jax,numba]"
python -m blr_rm gui
python -m pytest -q
python -m blr_rm benchmark --profile smoke --out run_smoke
```

示例（将 `1D` 换为 `2D` 即二维）：

```bash
python -m blr_rm generate --config 1D/generate_noisy.json --out run_data
python -m blr_rm optimize --data run_data --config 1D/mem_defaults.json --out run_mem
python -m blr_rm check --data run_data --result run_mem
python -m blr_rm report --data run_data --result run_mem --out run_report
python -m blr_rm scan --data run_data --grid 1D/scan_grid.json --out run_scan
```

扫描不按不同 alpha 的 Q 自动挑“最优”；`alpha_map` 改变时目标函数本身也在改变。默认 `alpha_map=0.2, alpha_c=1200, alpha_lbg=0.02` 是示例起点，不是普适标定。默认每次固定 default 的迭代上限 2400；达到上限不等于收敛。失败会报错并留在批量统计中。

100×100 速度–时延像素配置：`2D/generate_100x100.json`，其中 `n_velocity=100`，`delay_step_days=40/99`、最大延迟 40 天（端点包括在内，共 100 个延迟点）。普通示例使用较小网格，以便快速试运行。

无噪声 `generate_clean.json` 不捏造误差；若要拟合其零误差样本，需要显式设置误差下限。真值不作为优化器输入。数据格式、CSV 导入和误差下限见 [使用文档](docs/USAGE_ZH.md) 与 [数据格式](docs/DATA_FORMAT_ZH.md)。这些历史文档中的旧求解器默认参数以本页和当前 JSON 为准。

### 构建和验证

```bash
python -m pip install ".[test,build,jax,numba]"
python tools/build_windows.py
```

输出 `dist/BLR-RM/` 和 `dist/BLR-MEM-Windows-x64.zip`。构建脚本会执行真实 EXE 的生成、优化、检测、报告、扫描、续跑、Numba、JAX CPU JIT 和 GUI 操作检查；任一必需步骤失败即终止，不产生通过收据。`validation.json` 记录实际命令与 EXE 校验值。

144 组固定协议的数值实验：`python tools/run_scientific_validation.py --out new_validation`。失败对象、分母和环境均保留。模拟数据验证不是实测 AGN 的科学有效性证明；也不保证任意数据、任意 alpha 都能收敛。旧版历史报告不能充当此版验收。

## English

Version `0.1.0.dev2` uses the author's autumn MEM implementation by default in both dimensions: separately reduced C/L chi-square, normalized relative entropy, Adam warm-up, jointly scaled L-BFGS-B with profiled background, and damped floating defaults. Original solvers remain explicit legacy options only.

Install with `python -m pip install ".[test,jax,numba]"`, then run `python -m blr_rm gui`. For Windows binaries, download the artifact from a **successful** [Windows build](https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions/workflows/windows-build.yml) on `chris-update`. Extract the complete archive and keep `_internal/` next to the executables. No separate Python installation is needed. Earlier dev1 releases are not this build.

CPU manual, optional Numba, and JAX with optional JIT are supported. The native Windows bundle includes CPU JAX, not CUDA. Explicit GPU requests fail clearly when unavailable; auto may fall back to CPU. GPU and macOS execution have not been validated for this release.

Five tools retain their names: `GenerateData`, `BatchGenerate`, `MEMOptimizer`, `Detector`, `Analysis`; `BLRWorkbench` combines them and `blr-rm` is the CLI. `1D/` and `2D/` contain configurations and launchers. See the commands above and [references](docs/REFERENCES.md).

Frozen distribution checks and scientific simulations are separate. A working executable does not establish universal scientific validity. Unsuccessful simulations remain in the denominator. Default alpha values are examples, not universal optima; comparing Q across different alpha values is not a valid selection criterion.
