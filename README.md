<div align="center">

<p>
  <a href="README.md"><img src="https://img.shields.io/badge/English-current-172B43?style=for-the-badge" height="28" alt="English — current language"></a>
  <a href="README_ZH.md"><img src="https://img.shields.io/badge/简体中文-点击阅读-0F766E?style=for-the-badge" height="28" alt="简体中文 — 点击阅读完整中文版"></a>
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
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

</div>

BLR MEM Workbench brings synthetic-data generation, joint maximum-entropy inversion and independent checks into one local workflow for broad-line-region reverberation mapping. The Windows and Mac bundles include their runtimes. The graphical interface and command line share the same computation core.

<p align="center">
  <img src="docs/assets/overview.png" width="1000" alt="Original program report figure: true and recovered velocity–delay maps above, delay and velocity marginal responses below">
</p>

<p align="center"><sub>Original figure from the bundled 2D synthetic report. The maps share a color scale; lower panels show delay and velocity marginals. 9 × 16 grid, 5% variability noise. <a href="docs/assets/preview.json">Source and checks</a>.</sub></p>

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

## Contributing and citation

Contributions to installation, documentation, tests and small reproducible examples are welcome. Changes to numerical algorithms, scientific defaults and evaluation metrics need independent evidence; see [CONTRIBUTING.md](CONTRIBUTING.md).

Historical authorship, redistribution rights and the formal release license remain pending. Public visibility does not grant an open-source license; see [NOTICE.md](NOTICE.md). The author entry in [CITATION.cff](CITATION.cff) is provisional and must be confirmed before formal academic citation.

<p align="center"><sub>BLR MEM Workbench · Reproducible inputs. Inspectable results.</sub></p>
