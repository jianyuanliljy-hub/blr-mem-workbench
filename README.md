<a name="english"></a>

<div align="center">

<p>
  <a href="#english"><img src="https://img.shields.io/badge/English-current-172B43?style=for-the-badge" height="28" alt="English — read in English on this page"></a>
  <a href="#简体中文"><img src="https://img.shields.io/badge/简体中文-点击阅读-0F766E?style=for-the-badge" height="28" alt="简体中文 — 在本页阅读完整版"></a>
</p>

<img src="docs/assets/mark.svg" width="80" height="80" alt="BLR MEM Workbench logo">

<h1>BLR · MEM Workbench</h1>

<h3>Maximum-entropy response reconstruction.</h3>

<p>A maximum-entropy workbench for 1D delay responses and 2D velocity–delay maps.<br>Generate · Reconstruct · Check · Analyze</p>

<p>
  <a href="https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions/workflows/ci.yml"><img src="https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions/workflows/ci.yml/badge.svg?branch=main" alt="Source tests on three platforms"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/Python-3.11%2B-3572A5?logo=python&amp;logoColor=white" alt="Python 3.11 or newer"></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/Apps-Windows%20%7C%20macOS-0F766E" alt="Windows and macOS apps"></a>
  <a href="#command-line"><img src="https://img.shields.io/badge/Interface-GUI%20%2B%20CLI-4F46E5" alt="GUI and CLI"></a>
  <a href="https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/tag/v0.1.0-dev1-r1"><img src="https://img.shields.io/badge/Release-0.1.0.dev1%20preview-64748B" alt="0.1.0.dev1 development preview"></a>
</p>

<p>
  <a href="#quick-start">Quick start</a> ·
  <a href="https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/download/v0.1.0-dev1-r1/BLR_MEM_Workbench_0.1.0-dev1_Windows_x64.zip">Windows</a> ·
  <a href="https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/download/v0.1.0-dev1-r1/BLR_MEM_Workbench_0.1.0-dev1_macOS_AppleSilicon.zip">macOS</a> ·
  <a href="docs/USAGE_ZH.md">User guide (中文)</a> ·
  <a href="#command-line">Command line</a> ·
  <a href="#validation">Validation</a> ·
  <a href="#references">References</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

</div>

BLR MEM Workbench brings synthetic-data generation, joint maximum-entropy inversion and independent checks into one local workflow for broad-line-region reverberation mapping. The Windows and Mac bundles include their runtimes. The graphical interface and command line share the same computation core.

<p align="center">
  <img src="docs/assets/overview.png" width="1000" alt="Original program report figure: true and recovered velocity–delay maps above, delay and velocity marginal responses below">
</p>

<p align="center"><sub>Original figure from the bundled 2D synthetic report. The maps share a color scale; lower panels show delay and velocity marginals. 9 × 16 grid, 5% variability noise. <a href="docs/assets/overview.png">Full-size figure</a> · <a href="docs/assets/preview.json">Source and checks</a>.</sub></p>

## Why use it

- **One connected workflow.** Generate inputs, run MEM, inspect checks and open an offline report. Common settings use forms with units; advanced JSON and CLI access remain available.
- **One implementation, two dimensions.** `1D/` and `2D/` hold dimension-specific configurations and scan grids while sharing the generator, checks and interface.
- **Results you can inspect.** Noiseless truth stays separate from observations. Reports include independent forward checks, truth comparisons, residuals and iteration history.

| Task | Available functionality |
|---|---|
| Generate | True continuum, line emission and response maps; no added noise by default |
| Batch | Independent random streams, per-case identity and configuration-checked resume |
| Reconstruct | Joint MEM for continuum, background and response; defaults and exhaustive parameter scans |
| Check | File hashes, array conventions, forward consistency, final stationarity and default stability |
| Analyze | Shared-scale response comparisons, marginals, residuals, HTML reports and CSV summaries |

## Quick start

Download from the [preview release](https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/tag/v0.1.0-dev1-r1), **extract the complete archive**, then launch:

| Platform | Download | Launch |
|---|---|---|
| Windows x64 | [Windows bundle · ~110 MB](https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/download/v0.1.0-dev1-r1/BLR_MEM_Workbench_0.1.0-dev1_Windows_x64.zip) | `BLRWorkbench.exe` |
| macOS Apple Silicon | [Mac bundle · ~68 MB](https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/download/v0.1.0-dev1-r1/BLR_MEM_Workbench_0.1.0-dev1_macOS_AppleSilicon.zip) | `BLR MEM Workbench.app` |
| Source · Python 3.11+ | [Source and configurations](https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/download/v0.1.0-dev1-r1/BLR_MEM_Workbench_0.1.0-dev1_source.zip) | Instructions below |

Start with `START_HERE.txt`. Open `examples/2D/report/report.html` for an existing example or `validation/report.html` for the 144-case analysis. The release includes `SHA256SUMS.txt` for download verification.

For a first run, select 1D or 2D, set noise to `0.05`, generate a sample, run default MEM, then check the result and open the report. Preserve the bundle's relative file layout.

<details>
<summary>Run from source</summary>

In an activated Python 3.11+ virtual environment:

```bash
git clone https://github.com/jianyuanliljy-hub/blr-mem-workbench.git
cd blr-mem-workbench
python -m pip install ".[test]"
python -m blr_rm gui
```

The GUI requires Tcl/Tk. Source tests cover Windows, macOS and Linux; Linux currently has no prebuilt desktop bundle. See the [installation guide (中文)](docs/USAGE_ZH.md#安装与启动).

</details>

## Command line

A complete noisy 1D example:

```bash
python -m blr_rm generate --config "1D/generate_noisy.json" --out "run_1d_data"
python -m blr_rm optimize --data "run_1d_data" --config "1D/mem_defaults.json" --out "run_1d_mem"
python -m blr_rm check --data "run_1d_data" --result "run_1d_mem"
python -m blr_rm report --data "run_1d_data" --result "run_1d_mem" --out "run_1d_report"
```

In the portable bundles, replace `python -m blr_rm` with `blr-rm.cmd` on Windows or `./blr-rm` on Mac. Use a new output directory for each run. Batch generation, complete scans and resume are documented in the [CLI guide (中文)](docs/USAGE_ZH.md#命令行).

## Validation

| Check | Recorded result | Evidence |
|---|---|---|
| Source | 60 tests and two CLI cases on each of Windows, macOS and Linux | [Completed CI](https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions/runs/39633009287) · [Current CI](https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions/workflows/ci.yml) |
| Actual Windows release ZIP | 20 operations on a native Windows Server 2025 runner; 20 more under Wine | [Native run](https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions/runs/39632183302) · [Receipt](docs/receipts/windows_native_validation.json) |
| Mac arm64 bundle | Both GUI/CLI dimensions, signature integrity and dynamic-link checks | [Receipt](docs/receipts/macos_validation.json) |
| 144 synthetic cases | Forward consistency and final fixed-default stationarity passed; existing results independently rechecked | [Scope and metrics (中文)](docs/VALIDATION_ZH.md) · [Per-case CSV](docs/validation_per_case.csv) |

**This is a development preview.** All 72 two-dimensional cases retain floating-default stability `WARN`; 64/72 have an intermediate optimizer-history failure flag. These are reported separately from final stationarity. Real-AGN performance, finer grids and human acceptance on reviewers' Windows 10/11 machines remain unverified. The Mac bundle is arm64 with an ad hoc signature and has not been notarized.

## Documentation

The detailed technical guides are currently in Simplified Chinese.

| Topic | Guide |
|---|---|
| Installation and interface | [Usage](docs/USAGE_ZH.md) · [macOS](docs/MACOS_ZH.md) |
| Arrays, units and metrics | [Data format](docs/DATA_FORMAT_ZH.md) |
| Mathematics and architecture | [Design](docs/DESIGN_ZH.md) |
| Scope and reproducibility | [Validation](docs/VALIDATION_ZH.md) · [Receipts](docs/receipts/README.md) |
| Building executables | [Build and release](docs/RELEASE_ZH.md) |
| Provenance and references | [Source identity](provenance.json) · [References](docs/REFERENCES.md) |

## Frequently asked questions

<details>
<summary>Do I need Python or an internet connection to use the app?</summary>

The Windows and Mac bundles include Python, numerical dependencies and Tcl/Tk. Extract the complete archive and launch the app; it does not install dependencies online at startup. Running the source version requires a prepared environment.

</details>

<details>
<summary>Why do noiseless data require error floors for fitting?</summary>

Noiseless truth retains zero standard deviation. Inversion requires explicit continuum and line error floors to define the fitting weights. These assumptions are recorded with the result; they affect weighting without adding noise to the truth. See the [user guide (中文)](docs/USAGE_ZH.md).

</details>

<details>
<summary>Can I inspect a report when a check returns WARN?</summary>

Yes. A warning preserves a numerical state that needs interpretation, such as unsettled floating defaults. The report separates file integrity, forward consistency, final stationarity and optimizer history. Interpret these checks together. The example defaults are starting points; one- and two-dimensional `alpha` values are not interchangeable.

</details>

<details>
<summary>How can I report a problem or contribute?</summary>

Include the app version, operating system, dimension, minimal configuration and complete error output in an [Issue](https://github.com/jianyuanliljy-hub/blr-mem-workbench/issues/new/choose). See [CONTRIBUTING.md](CONTRIBUTING.md) for development and validation conventions.

</details>

## References

- Blandford, R. D. & McKee, C. F. (1982). [Reverberation mapping of the emission line regions of Seyfert galaxies and quasars](https://doi.org/10.1086/159843). *The Astrophysical Journal*, **255**, 419. — Response-function framework.
- Horne, K. (1994). [Echo Mapping Problems: Maximum Entropy Solutions](https://ui.adsabs.harvard.edu/abs/1994ASPC...69...23H/abstract). *ASP Conference Series*, **69**, 23. — Joint MEM and default images.
- Timmer, J. & König, M. (1995). [On generating power law noise](https://ui.adsabs.harvard.edu/abs/1995A%26A...300..707T/abstract). *Astronomy and Astrophysics*, **300**, 707–710. — Fourier-based synthetic light curves.
- Mangham, S. W. et al. (2019). [Do reverberation mapping analyses provide an accurate picture of the broad-line region?](https://doi.org/10.1093/mnras/stz1713). *MNRAS*, **488**, 2780–2799. — Controlled recovery tests and interpretation limits.

See the [full references and their roles in the code](docs/REFERENCES.md), including L-BFGS-B, SciPy and observational MEMEcho work. [Download BibTeX](docs/references.bib). These method references are separate from [citing this software](CITATION.cff).

## Contributing and citation

Contributions to installation, documentation, tests and small reproducible examples are welcome. Changes to numerical algorithms, scientific defaults and evaluation metrics need independent evidence; see [CONTRIBUTING.md](CONTRIBUTING.md).

Historical authorship, redistribution rights and the formal release license remain pending. Public visibility does not grant an open-source license; see [NOTICE.md](NOTICE.md). The author entry in [CITATION.cff](CITATION.cff) is provisional and must be confirmed before formal academic citation.

<p align="center"><sub>BLR MEM Workbench · Reproducible inputs. Inspectable results.</sub></p>

---

## 简体中文

<div align="center">

<p>
  <a href="#english"><img src="https://img.shields.io/badge/English-read_in_English-3572A5?style=for-the-badge" height="28" alt="English — read in English on this page"></a>
  <a href="#简体中文"><img src="https://img.shields.io/badge/简体中文-当前语言-172B43?style=for-the-badge" height="28" alt="简体中文 — 本页中文版"></a>
</p>

<img src="docs/assets/mark.svg" width="80" height="80" alt="BLR MEM Workbench 标志">

<h1>BLR · MEM Workbench</h1>

<h3>最大熵响应重建。</h3>

<p>一维时延响应 · 二维速度–时延图<br>生成数据 · 最大熵反演 · 独立检测 · 离线分析</p>

<p>
  <a href="https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions/workflows/ci.yml"><img src="https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions/workflows/ci.yml/badge.svg?branch=main" alt="三平台源码测试状态"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/Python-3.11%2B-3572A5?logo=python&amp;logoColor=white" alt="Python 3.11 或更新版本"></a>
  <a href="#快速开始"><img src="https://img.shields.io/badge/应用-Windows%20%7C%20macOS-0F766E" alt="Windows 和 macOS 应用"></a>
  <a href="docs/USAGE_ZH.md"><img src="https://img.shields.io/badge/操作-GUI%20%2B%20CLI-4F46E5" alt="图形界面和命令行"></a>
  <a href="https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/tag/v0.1.0-dev1-r1"><img src="https://img.shields.io/badge/版本-0.1.0.dev1%20preview-64748B" alt="0.1.0.dev1 开发预览版"></a>
</p>

<p>
  <a href="#快速开始">快速开始</a> ·
  <a href="https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/download/v0.1.0-dev1-r1/BLR_MEM_Workbench_0.1.0-dev1_Windows_x64.zip">Windows 下载</a> ·
  <a href="https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/download/v0.1.0-dev1-r1/BLR_MEM_Workbench_0.1.0-dev1_macOS_AppleSilicon.zip">macOS 下载</a> ·
  <a href="docs/USAGE_ZH.md">使用指南</a> ·
  <a href="#命令行">命令行</a> ·
  <a href="#验证结果">验证结果</a> ·
  <a href="#参考文献">参考文献</a> ·
  <a href="CONTRIBUTING.md">参与贡献</a>
</p>

</div>

BLR MEM Workbench 将活动星系核宽线区（broad-line region, BLR）的合成数据生成、最大熵法（maximum entropy method, MEM）反演和结果检查放在同一个本地工作台。Windows、Mac 成品自带运行环境，完整解压即可启动；界面和命令行共用一套计算核心。

<p align="center">
  <img src="docs/assets/overview.png" width="1000" alt="程序原始报告图：上排为真实与恢复的速度–时延图，下排为时延和速度边缘响应">
</p>

<p align="center"><sub>程序随包二维合成示例的原始报告图。上排共用色标，下排为时延与速度边缘响应；9 × 16 网格，5% 变异信号噪声。<a href="docs/assets/overview.png">查看原图</a> · <a href="docs/assets/preview.json">图像来源与检测记录</a>。</sub></p>

## 为什么用它

- **一个连贯的工作流程。** 生成、反演和报告自动衔接数据路径；常用参数使用带单位的表单，高级 JSON 和命令行同时保留。
- **一套实现，两种维度。** `1D/` 和 `2D/` 各自保存示例配置、MEM 默认参数与扫描网格，共用生成器、检测器和界面。
- **看得见结果，也查得到依据。** 无噪声真值与观测分开保存；独立前向检查、真值对照、残差和迭代历史一并进入离线报告。

| 你要做的事 | 程序提供什么 |
|---|---|
| 生成一例数据 | 真实连续谱、真实发射线、时延响应或速度–时延图；默认不加噪声 |
| 批量生成 | 独立随机数流、逐例身份记录、配置核对后的续跑 |
| MEM 反演 | 连续谱、背景和响应联合求解；默认配置与完整超参数扫描 |
| 独立检测 | 文件哈希、数组约定、前向一致性、最终一阶条件、默认图像稳定性 |
| 分析与分享 | 真值对照、边缘响应、残差、迭代历史、HTML 报告和逐例 CSV |

## 快速开始

从 [Release](https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/tag/v0.1.0-dev1-r1) 下载适合系统的压缩包，**完整解压**后启动。

| 系统 | 下载 | 打开方式 |
|---|---|---|
| Windows x64 | [Windows 程序包 · 约 110 MB](https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/download/v0.1.0-dev1-r1/BLR_MEM_Workbench_0.1.0-dev1_Windows_x64.zip) | 双击 `BLRWorkbench.exe` |
| macOS Apple Silicon | [Mac 程序包 · 约 68 MB](https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/download/v0.1.0-dev1-r1/BLR_MEM_Workbench_0.1.0-dev1_macOS_AppleSilicon.zip) | 打开 `BLR MEM Workbench.app` |
| 源码 · Python 3.11+ | [源码与配置](https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/download/v0.1.0-dev1-r1/BLR_MEM_Workbench_0.1.0-dev1_source.zip) | 见下方源码运行方式 |

两个程序包都包含 `START_HERE.txt`、`1D/` 与 `2D/` 入口、现成示例和使用文档。想先看效果，可直接打开 `examples/2D/report/report.html`；144 例汇总在 `validation/report.html`。校验文件见 Release 中的 `SHA256SUMS.txt`。

**第一次运行：** 选择一维或二维 → 将噪声比例设为 `0.05`，生成数据 → 运行默认 MEM → 检测并打开报告。保留程序目录内的运行时和文件相对位置。详细操作见 [使用指南](docs/USAGE_ZH.md) 与 [人工检查步骤](docs/DELIVERY_ZH.md)。

<details>
<summary>从源码启动</summary>

在已启用的 Python 3.11+ 虚拟环境中执行；图形界面需要 Tcl/Tk。各系统的环境创建步骤见 [安装与启动](docs/USAGE_ZH.md#安装与启动)。

```bash
git clone https://github.com/jianyuanliljy-hub/blr-mem-workbench.git
cd blr-mem-workbench
python -m pip install ".[test]"
python -m blr_rm gui
```

源码测试覆盖 Windows、macOS、Linux。Linux 当前提供源码运行方式，没有预构建的桌面程序包。

</details>

## 命令行

以一例带噪声的一维数据为例，依次完成生成、反演、独立检查和报告：

```bash
python -m blr_rm generate --config "1D/generate_noisy.json" --out "run_1d_data"
python -m blr_rm optimize --data "run_1d_data" --config "1D/mem_defaults.json" --out "run_1d_mem"
python -m blr_rm check --data "run_1d_data" --result "run_1d_mem"
python -m blr_rm report --data "run_1d_data" --result "run_1d_mem" --out "run_1d_report"
```

便携包中，Windows 用 `blr-rm.cmd`，Mac 用 `./blr-rm` 替换 `python -m blr_rm`。批量生成、纯扫描与续跑示例见 [完整命令行说明](docs/USAGE_ZH.md#命令行)。每次运行使用新的输出目录。

## 验证结果

| 检查 | 已有结果 | 依据 |
|---|---|---|
| 源码测试 | Windows / macOS / Linux 各 60 项通过，另有两维命令行检查 | [已完成的 CI](https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions/runs/39633009287) · [当前 CI](https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions/workflows/ci.yml) |
| Windows 实际分发包 | 原生 Windows Server 2025 runner 的 20 项操作检查通过；Wine 另有 20 项 | [原生检查](https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions/runs/39632183302) · [收据](docs/receipts/windows_native_validation.json) |
| macOS arm64 成品 | 两维 GUI/CLI、签名完整性及动态库检查通过 | [平台收据](docs/receipts/macos_validation.json) |
| 144 例合成验证 | 前向一致性与最终固定默认图像的一阶条件均通过；旧结果只读复核 | [协议与指标](docs/VALIDATION_ZH.md) · [逐例 CSV](docs/validation_per_case.csv) |

**当前仍是开发预览版。** 二维 72/72 例保留浮动默认图像稳定性 `WARN`，64/72 的优化历史包含中间失败标志；这些状态与最终一阶条件分别报告。真实 AGN、细网格适用性和检查者 Windows 10/11 电脑上的人工验收仍待完成。Mac 包为 arm64、临时签名，尚未经过 Apple 公证。完整范围见 [验证结果与限制](docs/VALIDATION_ZH.md)。

## 文档导航

| 我想了解 | 从这里开始 |
|---|---|
| 安装、界面和命令行 | [使用指南](docs/USAGE_ZH.md) · [Mac 使用说明](docs/MACOS_ZH.md) |
| 数据字段、单位和指标 | [数据格式](docs/DATA_FORMAT_ZH.md) |
| 数学约定和程序结构 | [设计说明](docs/DESIGN_ZH.md) |
| 测试证据和适用范围 | [验证说明](docs/VALIDATION_ZH.md) · [检查收据](docs/receipts/README.md) |
| 构建可执行程序 | [跨平台构建与分发](docs/RELEASE_ZH.md) |
| 代码来源与参考程序 | [来源记录](provenance.json) · [参考资料](docs/REFERENCES.md) · [参考 EXE 审查](docs/REFERENCE_EXE_REVIEW_ZH.md) |

## 常见问题

<details>
<summary>使用程序需要安装 Python 或联网吗？</summary>

Windows 和 Mac 成品自带 Python、数值依赖与 Tcl/Tk。完整解压后使用，不在首次启动时联网安装依赖。源码安装需要准备对应环境。

</details>

<details>
<summary>无噪声数据为什么还要填写误差下限？</summary>

无噪声真值的标准差为 0。反演需要显式声明拟合权重，使用 C、L 两个误差下限（error floor），该假设写入结果。它会影响拟合权重，不会向真值添加噪声。操作示例见 [使用指南](docs/USAGE_ZH.md)。

</details>

<details>
<summary>检测出现 WARN，还能查看报告吗？</summary>

可以。`WARN` 保留需要解释的数值状态，例如浮动默认图像尚未稳定。报告分别展示文件完整性、前向一致性、最终一阶条件和优化历史；应结合这些项目判断结果。当前示例默认参数仅是起点，一维和二维的 `alpha` 不可直接互换。

</details>

<details>
<summary>怎样报告问题或改进项目？</summary>

请提供程序版本、操作系统、维度、最小配置和完整错误信息。通过 [问题反馈](https://github.com/jianyuanliljy-hub/blr-mem-workbench/issues/new/choose) 提交，开发与验证约定见 [贡献指南](CONTRIBUTING.md)。

</details>

## 参考文献

- Blandford, R. D. & McKee, C. F. (1982). [Reverberation mapping of the emission line regions of Seyfert galaxies and quasars](https://doi.org/10.1086/159843). *The Astrophysical Journal*, **255**, 419。对应响应函数的回声映射框架。
- Horne, K. (1994). [Echo Mapping Problems: Maximum Entropy Solutions](https://ui.adsabs.harvard.edu/abs/1994ASPC...69...23H/abstract). *ASP Conference Series*, **69**, 23。对应联合最大熵建模与默认图像。
- Timmer, J. & König, M. (1995). [On generating power law noise](https://ui.adsabs.harvard.edu/abs/1995A%26A...300..707T/abstract). *Astronomy and Astrophysics*, **300**, 707–710。对应傅里叶方法生成的合成光变。
- Mangham, S. W. et al. (2019). [Do reverberation mapping analyses provide an accurate picture of the broad-line region?](https://doi.org/10.1093/mnras/stz1713). *MNRAS*, **488**, 2780–2799。对应已知真值的恢复检验与物理解读限制。

[完整文献与代码对应关系](docs/REFERENCES.md) 另含 L-BFGS-B、SciPy 和观测 MEMEcho 研究；可下载 [BibTeX](docs/references.bib)。方法文献与 [本软件的引用信息](CITATION.cff) 分别记录。

## 贡献与引用

欢迎改进安装体验、文档、测试和小规模可复现示例。数值算法、默认科学参数和评价指标的变更需要给出独立证据，详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

历史代码的完整署名、再分发范围和正式许可证仍待作者确认；公开可见不等于已授予开源许可，见 [NOTICE.md](NOTICE.md)。[CITATION.cff](CITATION.cff) 当前保留待确认的作者信息，正式学术引用前请核实作者、版本和提交。

<p align="center"><sub>BLR MEM Workbench · Reproducible inputs. Inspectable results.</sub></p>
