# 数据格式与单位

当前 schema 版本为 1。数据存为 NumPy NPZ，仅接受数值/布尔数组，读取时 `allow_pickle=False`。目录是不可覆盖的运行单元；最终 JSON 清单记录逐文件 SHA-256。清单用于一致性核对，不提供数字签名或数据来源认证。

## 数据目录

```text
dataset/
  observations.npz
  truth.npz          # 真实观测可没有此文件
  truth.png          # 生成时可选
  dataset.json       # 最后写入的完成清单
```

### observations.npz

| 字段 | 形状 | 定义 |
|---|---|---|
| `t_c` | `[N_C]` | 连续谱时刻/day；首版要求等间隔 |
| `t_l` | `[N_L]` | 发射线时刻/day；严格递增 |
| `delays` | `[N_tau]` | 非负、等间隔时延/day |
| `velocities` | `[N_v]` | 速度/km s^-1；二维严格递增，一维用单通道 0 |
| `c_obs` | `[N_C]` | 连续谱观测通量 |
| `c_sigma` | `[N_C]` | 连续谱测量标准差 |
| `l_obs` | `[N_v,N_L]` | 每个速度通道的发射线观测通量 |
| `l_sigma` | `[N_v,N_L]` | 发射线测量标准差；不用隐含广播规则 |
| `time_mask` | `[N_L]`，bool | True 为真实观测时刻；False 不进入发射线似然 |

当前首版支持整期谱线缺失，不支持每个速度像素独立缺失。模拟文件在缺失位置仍可保存生成的值，但所有求解和残差评价严格应用 mask；真实观测应显式填入有限占位值，不能把占位值当作测量。

现有二维实验 HDF5 中，`C_obs` 可能是全文件共享的 `[200]` 连续谱，`L_sigma` 则可能每个对象只有一个标量。接入旧格式时必须先逐文件核对 schema，不能把所有字段都按对象索引。首版没有自动 HDF5 迁移器，避免在不确认 C0、mask 和归一化的情况下批量转换旧数据。

连续谱必须覆盖所有 `t_l-delays`，包括最大延迟所需的监测前历史。范围外不外推。首版没有针对连续谱内部长缺口的观测网格/潜在网格分离接口，不能把插值后的连续谱当作无相关误差的密集真实观测；需要这类输入时应扩展接口后另做验证。

正联合模型要求观测通量为正。程序不会自动裁剪、平移、重归一化或改动网格。零误差只作为无噪声模拟的真实描述；反演须显式指定误差下限。

### truth.npz

| 字段 | 形状 | 定义 |
|---|---|---|
| `c_true` | `[N_C]` | 无噪声连续谱 |
| `l_true` | `[N_v,N_L]` | 无噪声发射线 |
| `psi_true` | `[N_v,N_tau]` | 真响应函数或速度–时延图 |
| `l_bg_true` | `[N_v]` | 真发射线背景 |

一维也保留速度维度 1，避免多套数组规则。优化入口通过文件白名单仅校验并读取 `observations.npz`；不读取或校验 `truth.npz`。独立检测与报告阶段才打开真值。

### dataset.json

必须包含 `schema_version`、`dimension`、`c0`、`observation_id` 和 `files`。生成数据另含完整生成配置、单位、轴语义、噪声定义、真值身份和运行环境。`observation_id` 由数组字段名、dtype、shape 和内容联合计算，而不依赖压缩文件的字节排列。

`C0` 是明确给定的参考连续谱水平，前向模型统一使用 `C-C0`。模拟使用配置的背景值；真实观测必须声明采用的参考水平，不能用隐藏真值替代观测标定。

模拟二维响应为**每个速度 bin 内已积分的响应密度**，单位 `day^-1 per velocity bin`。每条速度通道的模型积分只乘 `d_tau`。真值按 `sum(Psi)*d_tau=1` 归一化；优化结果不强行改成单位和。若需要每单位速度的连续密度，需要另行按 bin 宽度转换并记录。

## 反演结果目录

```text
result/
  solution.npz
  history.json
  diagnostics.json
  result.json
```

`solution.npz` 保存 `psi`、`continuum`、`l_bg`、`l_pred`、最后实际使用的 `default_map/default_continuum/default_background`，以及 `c_error_used/l_error_used`。检测器可以在不依赖优化器预测函数的情况下重算目标与所有参数块的梯度。

`result.json` 保存输入身份及输入文件 SHA、完整优化配置、显式误差下限、计算时间、版本、平台、依赖和代码 SHA。Windows 构建计划同时记录构建源代码清单和当前启动 EXE 的 SHA。`compute_seconds` 只统计求解阶段，排除数据读取、绘图与报告；不得称为完整端到端速度。

`history.json` 保留接受的迭代状态。浮动默认图像更新会改变目标函数，不能把跨外层的目标变化直接当成同一固定目标的单调下降证据。

## 指标

\[
\mathrm{NMSE}_{raw}=\frac{\sum(P-T)^2}{\sum T^2},\qquad
\mathrm{NMSE}_{shape}=\frac{\sum(\bar P-\bar T)^2}{\sum\bar T^2},
\quad \bar P=P/\sum P.
\]

同时报告时延重心误差/day、速度重心误差/km s^-1、恢复面积、真面积及 `chi2_C/N_C`、`chi2_L/N_observed_pixels`。没有可靠的有效自由度估计，不把后两项称为正式约化卡方。

经验重复模拟的波动、bootstrap 区间与后验可信区间有不同含义。首版的区间仅用于这批合成对象的均值差统计；没有实现贝叶斯后验和真实目标的误差覆盖率检验。
