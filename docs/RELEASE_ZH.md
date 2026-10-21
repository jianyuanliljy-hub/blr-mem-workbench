# Windows / macOS 构建与 GitHub 分发

当前交付为 `0.1.0.dev1` 检查预览，包含 Windows x64 便携程序、macOS Apple Silicon 应用和源码。Windows 二进制已在 Wine 11.18 中通过完整操作链，真实 Windows 验收尚未完成。macOS 使用说明、架构和签名边界见 [MACOS_ZH.md](MACOS_ZH.md)。

代码保存在 [私有仓库](https://github.com/jianyuanliljy-hub/blr-mem-workbench)，成品在 [v0.1.0-dev1 预览版](https://github.com/jianyuanliljy-hub/blr-mem-workbench/releases/tag/v0.1.0-dev1)。访问需要仓库权限。Release 的 Windows / Mac ZIP 保持交付时的内容和 SHA-256；源码 ZIP 对应 Release 标签的 Git 提交，包含更新后的分发说明和复核收据。下载后可用同页的 `SHA256SUMS.txt` 核对。

## 本次 Windows 便携包

`BLRWorkbench.exe` 是约 20 KB 的 Unicode 启动器，共享 `_runtime/` 中的 CPython 3.13.5 与科学计算依赖，`app/` 保存同一套程序源码。`blr-rm.cmd` 使用隔离模式调用该运行时；`1D/`、`2D/` 仅保存参数和启动入口。完整包无需安装 Python，也不在首次运行时联网下载。

`tools/build_windows_portable.py` 接受已下载的固定运行时、Windows CPython 3.13 wheels 与 Zig 编译器路径。运行时 SHA-256 在构建工具中固定；依赖版本由 `requirements-runtime.txt` 固定。Zig 仅用于生成小型启动器，不进入运行依赖。`build_identity.json` 记录运行时来源、wheels 和源码 SHA。

`tools/validate_windows_portable.py` 必须实际调用 Windows 二进制，可在原生 Windows 运行，也可显式指定独立 Wine 前缀。收据区分 `NATIVE_WINDOWS` 与 `WINE_COMPATIBILITY_LAYER`，不把兼容层运行记为原生验收。本次已有 20 个操作检查通过。

## 源码与复核

## 已准备的目录

```text
README.md / NOTICE.md / CITATION.cff
pyproject.toml / MANIFEST.in / provenance.json
1D/ / 2D/
src/blr_rm/
tests/
docs/
tools/
.github/workflows/
```

源码仓库包含程序、配置、测试、构建入口和文档；[docs/receipts](receipts/README.md) 保存选定的平台测试、合成协议和复核收据。`evidence/` 工作目录、原始大数据、模型权重、缓存、环境、凭据和原始参考 EXE 不进入 Git。程序成品以 Release 附件提供，避免把运行时放进源码历史。

Python wheel 已完成隔离目录安装与命令行两例检查；源码分发包（sdist）使用显式 `MANIFEST.in` 包含配置、文档和 Windows 构建文件，并已检查从 sdist 离线重建 wheel。wheel 提供程序核心；默认配置和使用文档随完整源码预览一起交付。上述结果不替代 Windows EXE 验收。

`CITATION.cff` 中作者信息明确标为待确认，不能直接作为正式作者清单。`NOTICE.md` 说明本地来源授权尚待确认，当前未添加未经确认的开放许可证。

## 本地 Windows 构建

另一个可选方案是在新的 Windows 工作目录使用 64 位 Python 3.13 / PyInstaller：

```powershell
py -3.13 -m venv ".venv"
& ".venv/Scripts/python.exe" -m pip install -r "requirements-runtime.txt"
& ".venv/Scripts/python.exe" -m pip install ".[test,build]"
& ".venv/Scripts/python.exe" -m pytest -q
& ".venv/Scripts/python.exe" "tools/build_windows.py"
```

构建脚本先写源代码身份，再调用 PyInstaller；拒绝覆盖已有 `dist/BLR-RM/`。产物拟为：

```text
dist/BLR-RM/
  BLRWorkbench.exe
  blr-rm.exe
  _internal/
  1D/
  2D/
  docs/
  build_identity.json
```

界面与命令行共享一个运行时；单例、批量、优化、检测、分析均进入同一程序核心。GUI 入口不弹控制台，专用 `blr-rm.exe` 提供命令行和返回码。此为原生 Windows 构建方案，不与本次便携包的目录结构混用。

构建后执行版本查询、冻结程序的两例基准、1D/2D 图形初始化检查。之后仍需实际人工/原生 UI 操作检查：中文及空格路径、无 Python 的干净系统、两维生成/反演/报告、错误提示、窗口缩放以及打包后的图像/HTML。构建通过不足以替代这些验收。

## GitHub 工作流

`ci.yml` 在 Linux、Windows、macOS 的 Python 3.12 环境运行源码测试和两例检查。`windows-build.yml` 使用 Python 3.13 与固定运行时依赖，仅支持手动触发 Windows 预览构建，并执行两维 GUI 流程；文件保存为构建产物，不自动发布 Release。

`macos-build.yml` 使用 `macos-15`（arm64）和 `macos-15-intel`（x86_64）分别构建、检查并归档 `.app`。runner 标签核对自 GitHub 官方 `actions/runner-images`；当前没有触发云端构建。无桌面会话的界面检查显式跳过并记录。

推送 `main` 会触发源码测试，两个平台构建工作流通过手动入口触发；实际状态以 [Actions 运行记录](https://github.com/jianyuanliljy-hub/blr-mem-workbench/actions) 为准。源码测试通过不等于 Release 成品或真实桌面操作已经验收。正式使用前还应根据仓库安全策略核对 Action 版本和固定提交 SHA。

## 正式公开发布尚缺的事项

- 历史代码作者、贡献归属、允许再分发的范围、正式 `LICENSE`。
- Windows 本机构建、无 Python 的干净环境和实际界面验收。
- Intel Mac 实际构建运行；macOS 干净系统验证，以及面向外部分发的 Developer ID 签名与公证。
- 二维浮动默认图像的预算/默认模型敏感性；当前六轮之后的稳定性警告必须保留。
- 更广科学协议：更大/更细网格、不同采样和连续谱、异方差与系统误差、真实观测、第三方程序比较。
- 版本与数据引用、最终依赖和第三方许可文件检查。

前两项是软件公开分发准备；后两项中的科学范围影响能宣称的适用性。程序运行通过、文件完整、局部一阶收敛均不能代替这些证据。
