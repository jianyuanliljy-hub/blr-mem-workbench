# macOS 使用与构建

macOS 版与 Windows 版共用生成器、MEM、独立检测器和数据格式。Apple Silicon（M 系列，arm64）与 Intel（x86_64）分别构建，不能将 arm64 包当作 Intel 通用包。

## 使用应用包

解压对应架构的 macOS ZIP，双击 `BLR MEM Workbench.app`。应用内包含 Python、NumPy、SciPy、pandas、Matplotlib 和 Tcl/Tk，运行应用无需自行安装 Python。保留外层目录可同时使用一维/二维配置、文档和命令行。

`1D/start.command` 和 `2D/start.command` 分别打开对应维度。应用版默认输出位置是用户主目录下的 `BLR_MEM_outputs/`，也可在界面选择其他目录；不向 `.app` 内写入科研结果。

当前使用本地临时签名（ad-hoc signing），没有 Apple Developer ID 签名或 Apple 公证（notarization）。本机运行与签名完整性检查不保证下载后通过 Gatekeeper 的开发者信任检查。若系统拦截，先核对压缩包 SHA-256，再在“系统设置 → 隐私与安全性”中检查此次打开的提示；不要关闭系统安全检查。若本机策略不允许打开，可使用下方源码安装方式。

## 命令行

在解压后的目录打开终端：

```bash
"./blr-rm" --version
"./blr-rm" generate --config "1D/generate_noisy.json" --out "$HOME/BLR_MEM_outputs/demo_1d_data"
"./blr-rm" optimize --data "$HOME/BLR_MEM_outputs/demo_1d_data" --config "1D/mem_defaults.json" --out "$HOME/BLR_MEM_outputs/demo_1d_mem"
"./blr-rm" check --data "$HOME/BLR_MEM_outputs/demo_1d_data" --result "$HOME/BLR_MEM_outputs/demo_1d_mem"
"./blr-rm" report --data "$HOME/BLR_MEM_outputs/demo_1d_data" --result "$HOME/BLR_MEM_outputs/demo_1d_mem" --out "$HOME/BLR_MEM_outputs/demo_1d_report"
```

输出目录需要尚不存在。其他参数与 `USAGE_ZH.md` 相同，将 `python -m blr_rm` 替换为 `"./blr-rm"` 即可。

## 从源码运行

使用带 Tcl/Tk 的 Python 3.11+，在源码根目录创建独立环境：

```bash
python3 -m venv ".venv"
".venv/bin/python" -m pip install ".[test]"
".venv/bin/python" -m blr_rm gui
```

源码目录的 `start.command` 会优先使用相邻应用；没有应用时使用 `.venv/bin/python`。终端运行可用 `sh "1D/start.command"` 或 `sh "2D/start.command"`。遇到 Tk 不能启动时应检查 Python/Tcl/Tk 和桌面会话；`import tkinter` 成功不证明窗口事件循环可运行。

## 构建对应架构

在目标架构的 macOS 上使用独立环境：

```bash
".venv/bin/python" -m pip install ".[test,build]"
".venv/bin/python" -m pytest -q
".venv/bin/python" "tools/build_macos.py"
".venv/bin/python" "tools/validate_macos.py" --bundle "dist/BLR-MEM-macOS-arm64" --out "build/native-validation"
```

Intel 将路径末尾 `arm64` 改为 `x86_64`。构建脚本拒绝覆盖已有目录。无桌面 CI 可以显式加入 `--skip-gui-check`，收据会标为界面未运行。GitHub 的 `macos-build.yml` 已配置两个架构的手动构建；尚未上传或触发，不能视为 Intel 验收通过。

应使用 `ditto -c -k --keepParent` 打包 macOS 分发目录，保留应用内符号链接与启动器的可执行权限。传输后重新检查解压产物的签名和命令行，再做实际界面操作。

## 适用性边界

应用打包与数值方法分别验收。二维浮动默认图像的稳定性警告继续保留；没有改变科研参数、评价指标或原有实验数据。完整验证范围见 `VALIDATION_ZH.md`，作者和再分发授权仍以 `NOTICE.md` 为准。
