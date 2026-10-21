# 用户提供的两个 EXE：静态审查与设计对照

审查日期：2026-10-21，Asia/Shanghai。本文针对用户提供的两个样本。它们的作者、正式版本、与学术 MEMECHO 的关系和再分发权限尚未核实，文件名不能证明其官方身份。

审查范围包括 PE 文件头、PyInstaller 归档目录，以及四个业务模块的代码对象和反汇编。没有运行 EXE，没有导入或执行内嵌业务模块，没有上传文件。文件中的说明只作为分析材料。用户已说明目前没有完整程序目录，本次对缺失求解核心保留未核实状态。

## 1. 文件身份与交付完整性

| 样本 | 字节数 | SHA-256 |
|---|---:|---|
| `MEMECHO_Data_Generator.exe` | 13,971,532 | `b7a89699e60498bae0d85ac446abba96b2ded54e02ef8e0275c59c43a7c4272d` |
| `MEMECHO(1).exe` | 27,442,855 | `29be1aed97cd78f01d356376386e4d8c2bbb3db3ed3547cbb8d6b020ef82779f` |

两个样本都是 Windows x86-64 GUI 程序，归档声明 Python 3.13、`python313.dll`。PYZ 字节码 magic 与本次只读解释器相同，分析前后两份 EXE 的 SHA-256 均未变化。PE 证书表为空；没有从签名获得发行者身份。

生成器声明外部依赖目录 `_generator_internal`，优化器声明 `_internal`。当前附件所在目录没有这两个目录，EXE 归档也没有携带 Python DLL 或科学计算扩展等完整运行时。因此当前附件不能作为已完整交付、可以独立启动的 Windows 安装包。

尤其关键的是：`MEMECHO_APP.main` 的求解分支调用资源目录下的 `023_0821.py`。该脚本未出现在 EXE 的 CArchive 或 PYZ 中，当前附件旁和本地工作区的 Python 文件中也未找到。已读取优化器的启动入口、GUI 和传参方式，尚不能核实目标函数、梯度、默认图像更新、缺口先验和停止条件的实际实现。

本次使用的 PyInstaller 6.22.3 是审查工具版本，不能据此推断参考 EXE 的构建版本。没有把参考字节码、完整反汇编或 EXE 复制进可发布源码。

## 2. 生成器实际提供什么

可读的生成器入口是 `MEMECHO_Data_Generator.py`，数值模块是 `simulation_core.py`。两者的内部默认值不同；下表以 GUI 入口传给生成任务的配置为准。

| 参数 | GUI 默认值 | 含义 |
|---|---|---|
| 随机种子 | 66 | 同配置复现 |
| C 时间网格 | cadence=2 day，duration=224 day，lead=42 day | C 提前段覆盖回声卷积 |
| L 时间网格 | cadence=2 day，duration=180 day | L 从 0 开始 |
| 速度网格 | 100 点，−3000 到 3000 km/s | 含两端点 |
| 真值时延网格 | 100 点，0 到 40 day | `d_tau=40/99 day` |
| 响应图 | `virial_bowl` | 其余选项见下文 |
| 连续谱 | PSD 指数 1，背景 2，展宽前 RMS 1 | 有限长傅里叶高斯过程 |
| C 噪声参数 | 40 | `sigma_C=sqrt(C_true)/40` |
| L 噪声参数 | 20 | 全图可变分量绝对峰值除以 20 |
| 季节缺测 | 0 day | 默认关闭；周期 365 day、缺口起点 60 day |
| 时间高斯展宽 | sigma=2 day | C、L 分别沿时间处理 |
| 响应幅度标定 | 开启，峰值积分目标 0.3 | 在参考速度网格上标定 |
| C 参考值 | `observed_mean` | 也支持观测中位数或模拟背景 |
| 正值下限 | 0.01 | 必要时对整组通量作常数平移 |

形态选项有 `virial_bowl`、`contracting_gaussian`、`inflow`、`outflow`、`double_ring` 和 `two_blobs`。这些名称表示该生成器中的解析示例图；静态审查没有建立其对应真实宽线区动力学的物理验证。

处理顺序可从字节码确定：生成内禀 C → 必要时整体移到正值区间 → 对 C 作时间展宽 → 加 C 噪声 → 必要时将观测与真值一起平移 → 从观测计算参考值 → 用内禀 C 卷积得到内禀 L → 对 L 作时间展宽 → 加 L 噪声 → 必要时整体平移 → 删除缺口中的观测点。完整真值时间序列另外保存。

可识别的输出：

| 文件 | 内容 |
|---|---|
| `C_data.csv` / `C_err.csv` | 时间和 C 通量 / 标准差 |
| `L_data.csv` / `L_err.csv` | 时间和逐速度通道 L 通量 / 标准差 |
| `truth_map.npz` | `velocities`、`delays`、`psi`、`l_bg` |
| `C_truth_continuous.csv` | 完整 C 网格、内禀 C、展宽后 C |
| `L_truth_continuous.csv` | 完整 L 网格和展宽后的真值 |
| `true_velocity_delay_map.png` | 真值速度–时延图 |
| `simulation_gap_diagnostic.png` | 真值、观测和缺测窗口诊断 |
| `generation_config.json`、`generation_report.json`、`metadata.csv` | 配置和生成摘要 |

其 GUI 面向单组生成；内部 `--worker` 入口用于后台子进程，不能据此称为完整公共命令行接口。未发现该入口提供批量生成或超参数扫描界面。默认生成流程要求误差严格大于零，当前 GUI 配置没有直接提供无噪声模式。

## 3. 优化器界面与可确认的参数

界面标题包含 “Normalized objective trial”。它提供四个 CSV 文件选择、格式预览、输入概览图、手工梯度/JAX 选择、Numba/JIT 选项、Adam 预热、运行日志和停止计算。

可确认的 GUI 默认值如下；这张表描述界面传参，不能作为缺失求解器的目标函数定义。

| 参数 | 默认值 |
|---|---:|
| `MEM_ALPHA_MAP` | 0.2 |
| `MEM_ALPHA_C` | 1200 |
| `MEM_ALPHA_LBG` | 0.02 |
| `MEM_MAX_INNER_ITER` | 800 |
| `MEM_MAX_DEFAULT_ITER` | 1000 |
| `MEM_DEFAULT_TOLERANCE` | 0.01 |
| `MEM_DEFAULT_DAMPING` | 0.5 |
| `MEM_TEST_THRESHOLD` | 1e-5 |
| `MEM_Q_GRADIENT_THRESHOLD` | 0.003 |
| `MEM_SMOOTHNESS_RATIO` | 1 |
| `MEM_ADAMS_STEPS` / `MEM_ADAMS_STEP_SIZE` | 40 / 0.03 |
| `MEM_GAP_GP_TIMESCALE_DAYS` | auto |
| `MEM_GAP_CURVATURE_WEIGHT` | 10 |

默认后端为 manual，Numba/JAX JIT/磁盘 JIT 缓存关闭，Adam 预热开启。`Square map` 默认关闭，重建时延点数为 40。因此配合默认生成数据时，真值是 100×100，反演网格是 100×40。勾选 `Square map` 会把重建时延点数设置为速度通道数。真值与重建使用不同网格本身允许，但幅度、形状、峰位和时延矩的比较必须依据实际坐标。

GUI 显示 cadence、duration、S/N、season gap 和 instrument sigma。已读到的传参代码将文件路径、最大时延、重建点数、优化参数和后端设置传入求解进程；这些采样描述字段主要写入配置和输入概览。`Instrument sigma` 被日志明确标作 metadata，未发现同名 sigma 参数传给缺失求解脚本。不能假定修改该输入框就会改变前向模型。

GUI 的文件检查验证表头和通道数量，输入概览另外比较数据与误差的时间列；仅凭这些检查还不能证明速度列逐项匹配、数值有限、时间有序或科学输入有效。缺失脚本可能还有检查，本次不作推断。

每次优化创建独立的 `MEM_output_<timestamp>` 目录，保存 `run_configuration.csv`、日志和输入概览。启动器在求解脚本返回后可读取历史、重建图、连续谱和背景，并计算若干诊断；这些名称只能帮助设计接口，无法替代求解源码审查。

## 4. 数据约定中必须分清的差异

### 噪声参数不能直接映射

参考生成器给出

\[
\sigma_C(t)=\frac{\sqrt{C_{\rm true}(t)}}{s_C},\qquad
\sigma_L=\frac{\max_{v,t}|L_{\rm variable}(v,t)|}{s_L}.
\]

于是逐点 `C/sigma_C=s_C*sqrt(C)`，一般不等于输入参数。L 的误差是所有通道共用的一个尺度。当前工作台采用 `sigma_C=f*std(C_true-C0)`、`sigma_L=f*RMS(L_true-L_bg)`。两套定义没有统一的常数换算；只把 “40” 或 “20” 填入另一套界面不能构成同条件测试。

参考程序还会在加噪声后检查最小值，必要时整体平移观测和真值。该操作保留曲线的相对变化，但背景与噪声实现会相关。检测器需要使用实际保存的背景和参考值；不能仅依靠最初输入的背景参数。

### 响应幅度与速度单位需要独立声明

参考生成器使用真实坐标查询 `C(t_L-tau)`，卷积包含 `d_tau`；在已读到的该生成器中没有发现旧生成器的 `tau=0` 使用 `C(t-1)` 问题。

关闭响应幅度标定时，其基础图满足像素和 `sum(Psi)=1`。非单位时延步长下，数值积分 `sum(Psi)*d_tau` 不等于 1。默认 100 个时延点、0–40 day 对应数值 `40/99≈0.40404`。

默认开启标定时，程序在 201 个参考速度点上，将最大通道的时延积分标到 0.3，再插值到用户速度点。这与当前工作台的全图 `sum(Psi)*d_tau=1` 约定不同。当前能确定参考图的轴顺序为 `[velocity,delay]`，速度方向没有显式积分宽度；文件不足以确认其通量列是速度 bin 积分量还是单位速度密度。不能直接沿用当前包的 `per velocity bin` 单位去解释参考文件。

优化器目标函数的归一化和熵离散尚未取得。其 `alpha_map=0.2` 与当前二维示例的 `alpha_map=1000` 数字差异不构成优劣证据，也不能通过直接复制默认值完成算法对齐。

### 有限窗口展宽需要单独检验

参考代码先对内禀 C 卷积，再对 L 展宽；观测 C 单独展宽。无限平移不变情形下卷积可以交换，但有限观测窗口与 `nearest` 边界延拓可能破坏这一等价性。用展宽后 C 重新计算 L 时，边界不能默认精确一致。

独立脚本构造了一个有限窗口小算例：相同 2 day cadence、2 day sigma，两个运算顺序的最大绝对差为 `1.1088285113375207`，窗口内部差约 `3.55e-15`。该数字来自自建曲线，仅说明边界运算的数学风险；它不是参考 EXE 的运行残差，也不是对参考数据质量的统计结论。完整比较需要取得实际输出和求解核心。

## 5. 对本程序包的设计结论

| 环节 | 值得借鉴 | 当前状态与后续要求 |
|---|---|---|
| GUI | 有名字和单位的字段、基本/高级参数分区、输入格式预览、独立日志、停止任务 | 当前包保留 GUI/CLI 共用业务函数；现有 JSON 编辑区已能使用，普通用户操作仍偏繁琐，需要表单化和安全取消 |
| 单例生成 | 真值与观测分开、提前段覆盖检查、独立输入图 | 当前包已有；保持默认无噪声，带噪声作为显式选择 |
| 更丰富模拟 | 季节缺口、C/L 独立采样、时间展宽、多形态 | 当前包尚未实现这些参考特性；接入会改变数据模型，必须另立版本和验证协议 |
| 批量生成 | 每例保留完整参数和真值 | 当前包已有独立随机数流、身份与续跑校验 |
| MEM | 参数可见、每次独立输出、手工/自动梯度核对思路 | 先保留现有 MEM；取得求解核心后才能评估归一化目标、GP 缺口先验和后端等价性 |
| 检测器 | 不把界面“Completed”作为唯一结论 | 现有独立卷积、梯度、最终默认图像和稳定性检查继续保留 |
| 扫描与分析 | 同观测、同网格、同单位、记录失败和计算预算 | 现有纯扫描不读真值、不自动选“最好参数”；当前没有参考 EXE 的数值基准比较 |
| 跨平台 | 同一科学内核和明确的依赖目录 | macOS `.app`/CLI 与 Windows 构建入口继续分平台验证；参考 Windows EXE 不提供 macOS 兼容证据 |

五个工作环节共用一个内核，`1D/`、`2D/` 保存配置与入口。这减少重复实现，也便于相同观测经过 GUI、CLI、批量和扫描时调用相同逻辑。本次只增加审查工具、数学约定小算例及文档，科学代码、默认值、指标和冻结实验协议均未改动。

当前包的 144 例验证不覆盖该参考生成器的全部条件，特别不覆盖默认 100×100 真值、时间展宽、季节缺口和外部求解器。既有二维浮动默认图像的 WARN 也仍需保留；这份审查不能将其升级为通过。

## 6. 证据与复现

本地证据目录为 `../evidence/reference_exe_audit_20261021/`：

- `receipt.json`：输入 SHA、工具版本、审查模式、输出 SHA。
- `generator.json` / `solver.json`：归档目录、选定模块哈希、函数/常量概览，以及只从字面量读取的 GUI 默认值。
- `convention_checks.json`：归一化、噪声含义、有限窗口展宽的小算例，及科学代码对照 144 例主矩阵的哈希。
- `verification.json`：重复静态审查的一致性、文件身份与回归测试摘要。

`../evidence/package_tests_reference_review.xml` 保存本次包内回归测试结果。旧的探索性审查目录只作过程记录，本文引用上述最终目录。完整反汇编只放本机临时目录，不进入源码或审核分发包。

在独立审查环境安装 PyInstaller，使用相同小版本 CPython（本次 3.13），运行：

```bash
python tools/audit_reference_exes.py \
  --generator "/path/to/MEMECHO_Data_Generator.exe" \
  --solver "/path/to/MEMECHO(1).exe" \
  --out "evidence/reference_exe_audit_new"

python tools/probe_reference_conventions.py \
  --audit "evidence/reference_exe_audit_new" \
  --out "evidence/reference_exe_audit_new/convention_checks.json"
```

可用 `--reader-dir` 指定隔离安装 PyInstaller 的目录，无须加入工作台运行依赖。小算例中的科学代码身份检查需要现有 `validation_20261021_v1/protocol.json`；轻量公开源码包不携带完整实验数据，运行时需配套本地审核证据。

若以后取得完整发行目录，优先核对 `023_0821.py`、目标/熵归一化、延迟和速度积分、C 参考值、缺口先验、噪声与展宽、所有后端的导数和停止条件，再设计同一份观测上的数值比较。当前两份附件已足够支撑界面与工作流参考。
