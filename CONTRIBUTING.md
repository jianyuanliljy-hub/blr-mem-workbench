# 参与贡献 · Contributing

感谢你帮助改进 BLR MEM Workbench。当前版本重点是可复现的数据生成、可靠的 MEM 流程和清楚的界面；优先解决具体使用问题，保持实现轻量。

## 报告问题

请通过 [Issue](https://github.com/jianyuanliljy-hub/blr-mem-workbench/issues/new/choose) 提供程序版本、操作系统、1D/2D 维度、最小参数配置、复现步骤和完整错误信息。优先使用小型合成数据，不上传私人数据或凭据。`WARN` 也有诊断价值，请保留完整检测结果。

## 本地开发

使用 Python 3.11+ 的独立虚拟环境，图形界面需要 Tcl/Tk。环境创建方式见 [使用指南](docs/USAGE_ZH.md#安装与启动)。在项目根目录运行：

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m blr_rm benchmark --profile smoke --out "run_contribution_smoke"
```

`run_contribution_smoke` 必须是新目录；完成后检查其中的汇总，保留二维默认图像警告。测试工作流覆盖 Windows、macOS、Linux，成品检查与源码测试分别记录。

## 提交什么样的修改

一次修改解决一个明确问题，并说明复现方式、修改原因及实际验证范围。文档和样式修改不应顺带改变数值行为；软件错误的修复应提供能暴露原问题的回归测试（regression test）。界面改动请附真实截图，并确认中文、空格路径和错误恢复。

涉及目标函数、默认超参数、误差权重、生成分布、阈值或评价指标时，请先在 Issue 说明提议及其对结果的影响。对照应使用固定输入和明确的实验协议，另建结果目录，保留原始指标与失败状态。不要用一次运行成功代替方法学验证。

`src/blr_rm/_vendor/` 的来源记录在 [provenance.json](provenance.json)。修改来源实现时，应同时记录差异及身份变化。当前历史代码的作者和正式许可证仍待确认；请仅提交你有权提供的内容，并阅读 [NOTICE.md](NOTICE.md)。

## English

Please keep changes focused. Report a reproducible issue with the app version, operating system, dimension, minimal configuration, steps and complete error output. Prefer small synthetic inputs and preserve warning states.

Use an isolated Python 3.11+ environment, run the commands above, and describe what you actually checked. Discuss changes to objectives, scientific defaults, error weights, thresholds or evaluation metrics before implementation. Preserve the original protocol and outputs, and provide independent comparisons. Documentation changes should preserve numerical behavior. Historical authorship and the release license remain pending; see [NOTICE.md](NOTICE.md).
