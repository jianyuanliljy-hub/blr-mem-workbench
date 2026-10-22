# BLR MEM Workbench

> 2026-10-22 更新：优化主程序已接入秋季试用版源码。请先读 [本轮交付状态与使用说明](上传前必读_20261022.md)。这是待继续验证的源码更新，不是已验收的新版 EXE Release；下文旧版发布及验证记录不能视为本轮验收。

本地审查更新与提交范围见 [2026-10-22 更新说明](docs/UPDATE_20261022_ZH.md)。历史验证收据不代表修改后的实现已通过相同验证。

面向一维时延响应和二维速度–时延图的联合最大熵法（maximum entropy method, MEM）工作台。当前为 `0.1.0.dev1` 检查预览版：提供自带运行环境的 Windows x64 程序包和 macOS Apple Silicon 应用，两平台共用界面、命令行和算法。先阅读 [交付与人工检查](docs/DELIVERY_ZH.md)。实际 Windows 分发包已通过原生 Windows CI 和 Wine 操作链；检查者电脑上的人工验收与 Intel Mac 检查仍待完成。

[下载 Windows / Mac 程序和源码](https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/tag/v0.1.0-dev1-r1)。Windows 完整解压后双击 `BLRWorkbench.exe`；M 系列 Mac 打开 `BLR MEM Workbench.app`。仓库当前为私有，访问和下载需要仓库权限。

从这里开始阅读：

- [使用文档](docs/USAGE_ZH.md)：安装、界面、命令行和常见问题。
- [设计与本地代码审查](docs/DESIGN_ZH.md)：哪些旧代码可复用、索引错误、数学约定和程序结构。
- [数据格式与单位](docs/DATA_FORMAT_ZH.md)：观测、无噪声真值、恢复结果和文件校验。
- [验证结果与限制](docs/VALIDATION_ZH.md)：本次实际执行的数据、指标、失败对象与发布边界。
- [正式程序和论文参考](docs/REFERENCES.md)：MEMECHO、PyROA、BRAINS 与打包规范。
- [用户提供的 EXE 审查](docs/REFERENCE_EXE_REVIEW_ZH.md)：实际界面、数据约定、缺失依赖与可借鉴的设计。
- [macOS 使用](docs/MACOS_ZH.md)：`.app`、M 系列/Intel 架构、命令行和本机打包。
- [跨平台构建与 GitHub 准备](docs/RELEASE_ZH.md)：构建入口、自动检查、署名与许可证。

## 五个工作环节

| 环节 | 实际能力 | 工作台入口 |
|---|---|---|
| 生成数据 | 无噪声真值、时延响应/速度–时延图、连续谱和发射线；可显式加入噪声 | 1 · 生成数据 |
| 批量生成 | 独立随机数流、逐例身份、配置一致才允许续跑 | 生成页的批量按钮 |
| 优化 | 连续谱、背景、传递函数联合 MEM；默认配置和纯扫描 | 2 · MEM 反演 |
| 检测 | 数据格式、SHA-256、独立卷积、一阶收敛、默认图像稳定性、真值恢复误差 | 3 · 检测与报告 |
| 分析 | 真值对照、残差、迭代历史、CSV 和固定协议验证矩阵 | 检测与报告 / 批量验证 |

Windows 压缩包完整解压后，双击 `BLRWorkbench.exe` 打开界面，`blr-rm.cmd` 提供命令行。一个启动器、一份共享运行时承载所有功能，无需安装 Python 或联网下载依赖。保持 `_runtime/`、`app/` 和启动器在同一目录。`Diagnose.cmd` 可在检查者电脑上运行两维 GUI 操作检查。源码归档单独提供；它不包含运行时。

macOS 使用 `BLR MEM Workbench.app` 和 `blr-rm` 命令行启动器，应用内提供同样五个工作环节。`1D/` 和 `2D/` 分别保存无噪声配置、带噪声配置、MEM 默认参数、纯扫描网格，以及 Windows `.cmd` / macOS `.command` 启动脚本。两种维度共用同一实现，避免两个文件夹里的算法逐渐不一致。

## 源码快速开始

要求 Python 3.11 或更新版本及 Tcl/Tk。进入本目录，在独立环境安装：

```bash
python -m pip install ".[test]"
python -m blr_rm gui
```

先运行两例软件检查：

```bash
python -m blr_rm benchmark --profile smoke --out "run_smoke"
```

完成一例有噪声一维数据的生成、反演和独立检测：

```bash
python -m blr_rm generate --config "1D/generate_noisy.json" --out "run_1d_data"
python -m blr_rm optimize --data "run_1d_data" --config "1D/mem_defaults.json" --out "run_1d_mem"
python -m blr_rm check --data "run_1d_data" --result "run_1d_mem"
python -m blr_rm report --data "run_1d_data" --result "run_1d_mem" --out "run_1d_report"
```

默认 `generate_clean.json` 不添加噪声。无噪声样本保留标准差 0，反演时需显式指定拟合误差下限；该权重假设写入结果，见使用文档。

## 科学边界

一维使用固定默认图像的联合 MEM，并增加数值坐标的对角尺度预处理。二维使用既有的联合 MEM 和浮动几何默认图像。两者目标函数的整体因子与熵离散方式不同，`alpha` 数值不可直接互换。完整默认参数只是当前示例的起点，不能称为所有观测条件下的最优值。

程序会分别显示文件完整性、前向一致性、数值收敛、默认图像变化和真值恢复误差。`optimizer_success` 与这些状态分别记录。模拟报告不宣称真实 AGN 科学验证完成；当前没有真实观测导入向导，也没有加入机器学习模型。

## 公开发布前

先阅读 [NOTICE.md](NOTICE.md)。历史源代码的完整作者和许可证尚需项目负责人确认。当前使用私有 GitHub 仓库协作，程序包放在预览版 Release，尚未授予开放源码许可。平台检查收据见 [docs/receipts](docs/receipts/README.md)，云端测试以 [GitHub Actions](https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions) 的实际运行结果为准。
