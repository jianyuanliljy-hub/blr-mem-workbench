# 使用文档

## 安装与启动

Windows 检查包先**完整解压**，再双击 `BLRWorkbench.exe`，无需安装 Python。`1D/start.cmd` / `2D/start.cmd` 分别打开两种维度；`blr-rm.cmd` 提供命令行。保留 `_runtime/`、`app/`、`launch.pyw` 与 EXE 的相对位置。`START_HERE.txt` 是最短使用说明，`examples/` 提供可直接打开的示例报告。实际验证范围见 [DELIVERY_ZH.md](DELIVERY_ZH.md)。

macOS 应用包可双击 `BLR MEM Workbench.app`，无需另装 Python；`1D/start.command` / `2D/start.command` 对应两种维度，`./blr-rm` 为命令行。架构、签名与构建说明见 [MACOS_ZH.md](MACOS_ZH.md)。下面的虚拟环境步骤用于源码版。

源码版要求 Python 3.11+、NumPy、SciPy、pandas、Matplotlib 和 Tcl/Tk。推荐独立虚拟环境，不修改系统 Python。示例命令均在程序包根目录执行。

Windows PowerShell：

```powershell
py -3.12 -m venv ".venv"
& ".venv/Scripts/python.exe" -m pip install ".[test]"
& ".venv/Scripts/python.exe" -m blr_rm gui
```

macOS/Linux：

```bash
python3 -m venv ".venv"
".venv/bin/python" -m pip install ".[test]"
".venv/bin/python" -m blr_rm gui
```

已安装依赖的本地环境也可在本目录将 `PYTHONPATH` 指向 `src` 运行。依赖版本与源文件 SHA 会写入每次运行记录。

另有原生 Windows PyInstaller 构建方案，使用 `_internal/` 目录和 `blr-rm.exe`。这与本次 `_runtime/` 便携检查包是两种分发方式，命令行业务相同。

## 界面工作流程

1. 选择一维或二维，以及输出位置。“1 · 生成数据”用表单显示时长、采样间隔、网格、种子和形态；默认噪声为 0，生成无噪声真值和图。
2. 需要模拟观测误差时，将“噪声比例”改为例如 `0.05`。它相对于变异信号幅度定义，不是总通量百分比。高级参数可展开 JSON；载入和保存预设均使用同一份配置。
3. 在“2 · MEM 反演”核对自动填入的数据目录和熵权重。带噪声数据可直接使用记录的标准差；无噪声数据必须填写 C、L 两个误差下限。默认参数不代表普遍最优值。
4. 运行 MEM 后，查看数值状态与日志。“计算结束”不等于科学验收。浮动默认图像未稳定和优化历史失败会保留在检测结果中。
5. 在“3 · 检测与报告”查看中文检测摘要，生成并打开离线报告。二维真值与恢复图共用色标，并显示边缘响应、残差随时间/速度的分布和迭代历史。完整 JSON 收在可展开的详情中。

批量生成输出 `case_000000/` 等独立数据目录。首版的界面 MEM 入口处理一个对象；整套自动生成、批量反演、检测和汇总由“批量验证”或 `benchmark` 命令提供。任意用户批次可逐例调用命令行，避免界面默认一次启动大量求解。

## 命令行

以下 `python -m blr_rm` 在本次 Windows 便携包中对应 PowerShell 的 `& ".\blr-rm.cmd"`；macOS 包对应 `./blr-rm`。

### 生成无噪声真值

```bash
python -m blr_rm generate --config "1D/generate_clean.json" --out "clean_1d"
python -m blr_rm generate --config "2D/generate_clean.json" --out "clean_2d"
python -m blr_rm check --data "clean_2d" --out "clean_2d_check.json"
```

`truth.npz` 包含真实连续谱、真实响应、背景和无噪声发射线。`truth.png` 只画这些真实量与单独的观测量，不向真值添加误差。

### 从含噪观测反演

```bash
python -m blr_rm generate --config "2D/generate_noisy.json" --seed 731 --out "noisy_2d"
python -m blr_rm optimize --data "noisy_2d" --config "2D/mem_defaults.json" --out "mem_2d"
python -m blr_rm check --data "noisy_2d" --result "mem_2d" --out "mem_2d_check.json"
python -m blr_rm report --data "noisy_2d" --result "mem_2d" --out "report_2d"
```

### 对无噪声数据做数值恢复诊断

```bash
python -m blr_rm optimize --data "clean_1d" --error-floor 0.05 0.03 --out "clean_1d_mem"
```

两个值分别为连续谱、发射线通量单位的标准差下限。它们没有向数据添加噪声，只定义本次数值拟合的权重。不同值可能改变正则化与数据项的相对作用，属于必须公开的数值假设；不要将其解释为真实测量误差。它们被明确保存到 `result.json`。

### 批量生成与续跑

```bash
python -m blr_rm batch --config "2D/generate_noisy.json" --count 100 --out "batch_2d"
python -m blr_rm batch --config "2D/generate_noisy.json" --count 100 --out "batch_2d" --resume
```

随机种子依次为配置 seed、seed+1 等。连续谱、形态、两侧噪声与缺测使用不同随机数流。续跑核对协议、源代码和已有数据身份；配置或代码变化时应新建输出目录。部分损坏/未封口的目录会被拒绝，不自动清除。

### 默认参数与纯扫描

```bash
python -m blr_rm scan --data "noisy_2d" --config "2D/mem_defaults.json" --grid "2D/scan_grid.json" --out "scan_2d"
python -m blr_rm scan --data "noisy_2d" --config "2D/mem_defaults.json" --grid "2D/scan_grid.json" --out "scan_2d" --resume
```

示例二维网格完整计算 3×2=6 个参数组合。每个点有独立配置、历史、解和观测检测；`selection=NONE_PURE_SCAN`。这里不读取真值、不自动挑选最优，不允许扫描数值验收阈值来放宽检测。

### 自带验证矩阵

```bash
python -m blr_rm benchmark --profile smoke --out "smoke"
python -m blr_rm benchmark --profile validation --out "validation"
```

`smoke` 为每个维度一个对象。`validation` 为每个维度 3 种形态×3 个噪声幅度×2 个缺测比例×4 个独立种子，共 144 个对象。首例运行前冻结 `protocol.json`；输出逐对象数据、解、检测、CSV 和 HTML，保留失败。它是软件和有限合成模型验证，不是正式程序间公平比较，也不代表真实 AGN 科学验收。

## 输出和错误处理

所有命令要求新的输出目录，避免覆盖原实验。需要重做时显式选新目录；只有 `batch`、`scan`、`benchmark` 支持协议核对后的续跑。文件清单在全部相应文件写完后封口；没有最终清单的目录视为未完成。

命令行返回码：`0` 表示操作完成且被评估的数值/前向检查未失败；`1` 为输入、路径或执行异常；`2` 表示已有结果，但检测、批处理或数值验证存在失败项。浮动默认图像 `WARN` 会保留，单独的警告不改变返回码；必须查看报告中的对应状态。

常见原因：

| 提示 | 含义与处理 |
|---|---|
| 标准差为零 | 无噪声数据；显式提供拟合权重假设 |
| 连续谱未覆盖 t_L−tau | 需要真实的前置连续谱支撑；程序禁止外推 |
| 通量非正 | 当前正联合模型要求正通量；先检查背景和标定，程序不自动平移 |
| 哈希/身份不匹配 | 文件被修改或输入结果配错；先核查来源 |
| 数值未通过 | 查看梯度、优化消息和预算；保留失败，再使用新目录做数值诊断 |
| 默认图像 WARN | 规定的浮动默认迭代后仍有较大变化；需做默认图像/预算敏感性，不能当作完全稳定 |
| 内存预计超过限制 | 当前使用密集算子；不隐式降低科学网格，需要专门的大网格实现 |

更多数据定义见 `DATA_FORMAT_ZH.md`，当前实际测得的结果与未完成项见 `VALIDATION_ZH.md`。
