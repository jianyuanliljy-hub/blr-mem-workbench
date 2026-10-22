# 正式程序和原始文献参考

核对日期：2026-10-20（America/Los_Angeles）。本包参考方法、接口和验证思路，没有复制以下外部项目代码。

## 科学方法与程序

1. Keith Horne (1994), **Echo Mapping Problems: Maximum Entropy Solutions**, ASP Conference Series 69, p.23。
   - 原始论文/ADS：https://ui.adsabs.harvard.edu/abs/1994ASPC...69...23H/abstract
   - 本地有 PDF：`../reference/101-Horne 1994-算法根基 — Echo Mapping Problems — Maximum Entropy Solutions.pdf`。
   - 参考正相对熵、默认图像、连续谱/背景/响应联合建模。当前程序的目标因子、默认图像更新与优化轨迹均明确标注，不能直接称为完整 MEMECHO 原版。

2. **MEMECHO** 相关正式使用与方法说明：
   - 可核对的盲测论文：Mangham et al. (2019), *Do Reverberation Mapping Analyses Provide an Accurate Picture of the Broad Line Region?*，https://arxiv.org/abs/1906.11272
   - 参考其联合拟合及速度–时延图工作流。公开论文不足以证明已取得可再分发的原版源代码授权。本版没有声称和 MEMECHO 做过数值逐例对照。

3. **PyROA**，作者维护的程序仓库：
   - https://github.com/FergusDonnan/PyROA
   - 可参考安装、API、示例和结果输出。其方法采用 running optimal average 等建模组件；它不构成当前二维非参数 MEM 的直接等价实现。后续对照必须先统一科学问题、输入与输出指标。

4. **BRAINS**，宽线区/回声映射分析程序：
   - https://github.com/LiyrAstroph/BRAINS
   - 文档：https://brains.readthedocs.io/
   - 可参考规范化输入、参数配置、模拟和结果后处理。其物理/贝叶斯建模范围与当前正 MEM 不同，不能只比较输出图是否相似。

5. **pyPETaL**，作者维护的时延测量流程：
   - https://github.com/Zstone19/pypetal
   - 文档：https://pypetal.readthedocs.io/
   - 可参考多入口流程、输入格式、运行示例与多方法结果组织。光变时延测量和完整速度–时延图反演的科学目标需区分。

6. Timmer & König (1995), **On generating power law noise**。
   - 本地参考 PDF 位于 `../reference/`。本包使用有限长傅里叶高斯幂律过程，同时随机化振幅与相位；未把该简单数值生成器宣称为完整真实 AGN 连续谱模型。

## 打包、分发与可复现性

- PyInstaller 官方说明：https://pyinstaller.org/en/stable/operating-mode.html
  - 按目标操作系统构建；本机 macOS 无法据此宣称 Windows EXE 已被验证。
- PyInstaller spec 与 hooks 文档：https://pyinstaller.org/en/stable/spec-files.html 、https://pyinstaller.org/en/stable/hooks.html
  - 设计使用 onedir，共享依赖，减少多入口重复携带科学计算库；实际构建和图形启动仍须在 Windows 运行。
- Python Packaging User Guide：https://packaging.python.org/en/latest/tutorials/packaging-projects/
  - 使用 `pyproject.toml`、`src/` 布局、可安装入口和独立测试。
- GitHub 官方文档：https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files
  - `CITATION.cff` 有助于引用，但作者与许可证必须由项目确认后填写正式信息。

后续若要引入正式程序作为对照，应记录其版本/提交、许可证、配置、同一对象的数据身份、输出单位及总计算时间；先做数学接口一致性，再进行盲数据比较。当前版本尚未执行这些第三方程序的基准比较。

## 用户提供的 Windows 程序样本

2026-10-21（Asia/Shanghai）另行静态审查了 `MEMECHO_Data_Generator.exe` 与 `MEMECHO(1).exe`，详见 [审查和设计对照](REFERENCE_EXE_REVIEW_ZH.md)。已读到生成器数值模块和两个 GUI/启动入口；优化器实际调用的外部 `023_0821.py` 未提供。两份文件的作者、正式身份、许可证和完整运行依赖尚未核实，不能将这次静态参考称为正式 MEMECHO 数值对照。当前未执行这两个 EXE，也未复制其代码到本包实现。
