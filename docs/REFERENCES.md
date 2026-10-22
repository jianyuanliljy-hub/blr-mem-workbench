# References · 参考文献

[BibTeX](references.bib) · [English homepage](https://github.com/jianyuanliljy-hub/blr-mem-workbench#english) · [中文首页](https://github.com/jianyuanliljy-hub/blr-mem-workbench#简体中文)

Bibliographic metadata checked on 2026-10-22 against DOI records, publisher records and author-maintained sources. The papers below explain the methods and numerical tools used or discussed in this project. Implementation details and local source provenance are recorded in [DESIGN_ZH.md](DESIGN_ZH.md) and [provenance.json](../provenance.json).

以下按本包中的用途列出文献。论文中的方法、其他软件的验证结果和本包的合成验证分别归属各自的来源；具体离散化、目标函数、默认值与收敛检查以本包的设计文档和代码为准。

## Reading map · 阅读与代码对应

| Topic / 内容 | Reference / 文献 | Implementation or scope / 对应位置或范围 |
|---|---|---|
| Linear response / 线性响应 | [Blandford & McKee (1982)](#reverberation-mapping) | `data.py::forward_matrix`, `simulate`; discretized response in [Design §3](DESIGN_ZH.md#3-数学约定和单位) |
| Joint MEM / 联合最大熵 | [Horne (1994)](#maximum-entropy-echo-mapping) | `_vendor/memecho.py`, `_vendor/mem2d.py`, `solver.py`; this package uses its own documented objective and optimizer conventions |
| Synthetic driver / 合成驱动光变 | [Timmer & König (1995)](#power-law-light-curves) | `data.py::_powerlaw_driver`; finite-length Gaussian Fourier process, rescaled to unit sample variance |
| Recovery and interpretation / 恢复检验与解读 | [Mangham et al. (2019)](#controlled-recovery-tests) | Context for known-truth tests and independent checks; the current 144-case suite is a separate protocol, not a reproduction of their blind test |
| Numerical minimization / 数值优化 | [Zhu et al. (1997)](#bound-constrained-optimization), [Virtanen et al. (2020)](#scientific-computing) | `scipy.optimize.minimize(method="L-BFGS-B")` in `scaled_1d.py` and `_vendor/mem2d.py` |
| Observational example / 观测研究 | [Horne et al. (2021)](#observational-context) | Published MEMEcho application to NGC 5548; background reading, separate from this package's synthetic validation |

## Method references · 方法文献

### Reverberation mapping

**[1]** Blandford, R. D. & McKee, C. F. (1982). **Reverberation mapping of the emission line regions of Seyfert galaxies and quasars.** *The Astrophysical Journal*, **255**, 419. [DOI: 10.1086/159843](https://doi.org/10.1086/159843) · [ADS](https://ui.adsabs.harvard.edu/abs/1982ApJ...255..419B/abstract).

Response functions connect continuum variability with delayed line emission. 本包将这一关系离散为按实际 `t_L - tau` 坐标查询的前向模型；二维响应按速度 bin 积分后的约定另见设计文档。

### Maximum-entropy echo mapping

**[2]** Horne, K. (1994). **Echo Mapping Problems: Maximum Entropy Solutions.** In P. M. Gondhalekar, K. Horne & B. M. Peterson (eds.), *Reverberation Mapping of the Broad-Line Region in Active Galactic Nuclei*, ASP Conference Series, **69**, 23. [Publisher volume](https://aspbooks.org/a/volumes/table_of_contents/?book_id=181) · [ADS](https://ui.adsabs.harvard.edu/abs/1994ASPC...69...23H/abstract).

Background for positive entropy, default images and joint continuum/background/response modeling. 本包一维使用固定默认图像，二维显式记录浮动默认图像及其稳定性；求解采用下述 L-BFGS-B，与原版 MEMEcho 的流程差异见设计文档。

### Power-law light curves

**[3]** Timmer, J. & König, M. (1995). **On generating power law noise.** *Astronomy and Astrophysics*, **300**, 707–710. [ADS](https://ui.adsabs.harvard.edu/abs/1995A%26A...300..707T/abstract) · [Author publication list](https://jeti.uni-freiburg.de/paper.html).

Background for Gaussian Fourier synthesis with randomized amplitudes and phases. 本包使用有限长度的幂律功率谱过程，并按样本方差归一化；尚未实现长序列裁剪和红噪声泄漏处理，不能把此生成器视为完整 AGN 连续谱物理模型。

### Controlled recovery tests

**[4]** Mangham, S. W., Knigge, C., Williams, P., Horne, K., Pancoast, A., Matthews, J. H., Long, K. S., Sim, S. A. & Higginbottom, N. (2019). **Do reverberation mapping analyses provide an accurate picture of the broad-line region?** *Monthly Notices of the Royal Astronomical Society*, **488**(2), 2780–2799. [DOI: 10.1093/mnras/stz1713](https://doi.org/10.1093/mnras/stz1713) · [arXiv:1906.11272](https://arxiv.org/abs/1906.11272).

A published blind test of MEMEcho and CARAMEL, including limits on physical interpretation. 本包保留已知真值与观测的区分，并分别检查前向一致性、数值条件和恢复误差；本包未运行原版 MEMEcho/CARAMEL 的逐例基准比较，也未复现该论文的数据协议。

### Bound-constrained optimization

**[5]** Zhu, C., Byrd, R. H., Lu, P. & Nocedal, J. (1997). **Algorithm 778: L-BFGS-B: Fortran subroutines for large-scale bound-constrained optimization.** *ACM Transactions on Mathematical Software*, **23**(4), 550–560. [DOI: 10.1145/279232.279236](https://doi.org/10.1145/279232.279236) · [Author description](https://users.iems.northwestern.edu/~nocedal/Abstracts/lbfgsb.html).

The numerical optimization algorithm used through SciPy. 本包的一维对角尺度预处理与二维分块安排属于本地实现约定；目标函数停止条件和最终独立梯度检查分别记录。所用 SciPy 1.15.3 的 [`ftol` / `gtol` 文档](https://docs.scipy.org/doc/scipy-1.15.3/reference/optimize.minimize-lbfgsb.html) 给出库函数的终止条件。

### Scientific computing

**[6]** Virtanen, P., Gommers, R., Oliphant, T. E. et al. (2020). **SciPy 1.0: fundamental algorithms for scientific computing in Python.** *Nature Methods*, **17**, 261–272. [DOI: 10.1038/s41592-019-0686-2](https://doi.org/10.1038/s41592-019-0686-2).

Citation for the SciPy library used by the numerical solvers. 运行依赖与构建版本记录在 `requirements-runtime.txt` 和分发包身份文件。

### Observational context

**[7]** Horne, K., De Rosa, G., Peterson, B. M. et al. (2021). **Space Telescope and Optical Reverberation Mapping Project. IX. Velocity–Delay Maps for Broad Emission Lines in NGC 5548.** *The Astrophysical Journal*, **907**(2), 76. [DOI: 10.3847/1538-4357/abce60](https://doi.org/10.3847/1538-4357/abce60) · [arXiv:2003.01448](https://arxiv.org/abs/2003.01448).

An observational application of MEMEcho with its linearized echo model and entropy regularization described in §3. 可用于理解真实观测下的速度–时延图；本包当前仅完成文档所列的合成验证，没有复算该观测研究。

## Related software · 相关软件

| Project | Maintained sources | Relevance / 参考范围 |
|---|---|---|
| PyROA | [Repository](https://github.com/FergusDonnan/PyROA) | Running optimal average and light-curve modeling; 可参考 API、安装与示例 |
| BRAINS | [Repository](https://github.com/LiyrAstroph/BRAINS) · [Documentation](https://brains.readthedocs.io/) | Bayesian BLR dynamics and reverberation/spectro-astrometric analysis; 可参考输入、配置和后处理 |
| pyPETaL | [Repository](https://github.com/Zstone19/pypetal) · [Documentation](https://pypetal.readthedocs.io/) | Multi-method AGN time-lag pipeline; 可参考流程与结果组织 |

These are related projects, not dependencies or benchmarked equivalents of this package. 本包未复制上述项目或外部 MEMEcho 的源代码。未来对照需记录版本、许可证、输入身份、单位、配置、指标和计算成本，再比较相同科学问题下的结果。

## Packaging and reproducibility · 构建与可复现性

- [PyInstaller operating mode](https://pyinstaller.org/en/stable/operating-mode.html), [spec files](https://pyinstaller.org/en/stable/spec-files.html) and [hooks](https://pyinstaller.org/en/stable/hooks.html): target-specific builds and shared runtimes. 实际构建与平台测试状态见 [RELEASE_ZH.md](RELEASE_ZH.md)。
- [Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/): installable projects, `pyproject.toml` and package metadata.
- [GitHub citation files](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files): software citation metadata in `CITATION.cff`. 正式作者与许可证仍以项目确认的信息为准。

## User-provided program samples · 用户提供的程序样本

On 2026-10-21, `MEMECHO_Data_Generator.exe` and `MEMECHO(1).exe` were inspected statically; see [REFERENCE_EXE_REVIEW_ZH.md](REFERENCE_EXE_REVIEW_ZH.md). 已读到生成器数值模块和 GUI/启动入口，优化器调用的外部 `023_0821.py` 未提供。其作者、正式身份、许可证和完整运行依赖尚未核实。本包未执行这两个 EXE、未复制其代码，也没有据此声称完成正式 MEMEcho 数值对照。

## Citing this workbench · 引用本软件

The method bibliography in [references.bib](references.bib) is separate from this software's metadata in [CITATION.cff](../CITATION.cff). Cite the methods actually used in your analysis and record the workbench version, Git commit and configurations. 本软件正式学术署名仍待确认；来源与授权状态见 [NOTICE.md](../NOTICE.md)。
