# 随仓库保存的检查收据

这些文件复制自已完成的本地检查，不重跑或覆盖旧实验。原始命令中的本机路径用于追溯当时环境，下载程序无需具备这些路径。完整示例、HTML 分析和平台检查也随两个程序 ZIP 提供。

| 文件 | 内容 |
|---|---|
| `delivery_original.json` | 交付时的源码身份、测试状态和原始三个 ZIP 的 SHA-256；其中源码 ZIP 是上传前的本地快照 |
| `unit_tests.xml` | 60 项源码测试的原始 JUnit 收据 |
| `windows_wine_validation.json` | Windows 二进制在 Wine 11.18 的 20 个操作检查 |
| `github_windows_package.json`、`windows_native_validation.json`、`windows_native_gui_flow.json` | 同一 Windows ZIP 在原生 Windows Server 2025 runner 的身份、20 个操作检查与两维 GUI 收据 |
| `macos_validation.json`、`macos_gui_flow.json` | Mac arm64 成品的命令行和真实 Tk 主循环流程 |
| `windows_archive_relocation.json`、`macos_archive_relocation.json` | 最终 ZIP 在中文和空格新路径解压后的操作检查 |
| `validation_protocol_144.json` | 原 144 例合成验证的固定协议 |
| `readonly_analysis_protocol.json`、`readonly_analysis_summary.json`、`low_response_per_case.csv` | 旧 144 例只读复核与二维低响应区的测试后诊断 |

主验证逐例表和汇总为上一级的 [validation_per_case.csv](../validation_per_case.csv)、[validation_summary.json](../validation_summary.json)。两个程序 ZIP 的哈希保持原样；GitHub Release 的源码 ZIP 从标签提交导出，新增了发布信息与本目录，因此其哈希与原本地源码快照不同。Release 提供对应的 `SHA256SUMS.txt`。

文件完整性、软件操作、最终一阶收敛和科学适用性分别解释。原本地收据保留当时的 `native_windows: NOT_RUN`；后来增加的原生 Windows 云端收据记录 `NATIVE_WINDOWS` / `PASS`。二维浮动默认图像警告保持原样，检查者电脑的人工验收仍待完成。源码 CI 以仓库 Actions 的对应提交记录为准。
