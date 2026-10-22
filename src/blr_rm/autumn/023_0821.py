"""
023: 二维 MEMECHO 加速版。

数学模型、Q=chi2-alpha*S、正值约束、floating default 外层更新和
Horne TEST 停止准则与 02/022 保持一致。数值求解改为：
1. 在 log(w/scale) 中做短程 Adam warm-up；
2. 每个冻结 default 下，用联合 L-BFGS-B 优化 Psi、C，并用
   变量投影在每次计算中精确求出条件最优 L_bg；
3. 外层再阻尼更新 default，直到 default 收敛。
"""

import os
import time
import re
import numpy as np
from scipy.optimize import minimize
import matplotlib.pyplot as plt

MATPLOTLIB_FONT_FAMILY = os.getenv('MEM_FONT_FAMILY', 'DejaVu Sans').strip()
if MATPLOTLIB_FONT_FAMILY:
    plt.rcParams['font.family'] = MATPLOTLIB_FONT_FAMILY
plt.rcParams['axes.unicode_minus'] = False

USE_NUMBA = os.getenv('MEM_USE_NUMBA', '0') == '1'
if USE_NUMBA:
    try:
        from numba import njit
        NUMBA_AVAILABLE = True
    except ImportError:
        njit = None
        NUMBA_AVAILABLE = False
        USE_NUMBA = False
else:
    njit = None
    NUMBA_AVAILABLE = False

MEM_INPUT = {
    "continuum_csv": os.getenv('MEM_CONTINUUM_CSV', os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "C_data.csv")),
    "continuum_err_csv": os.getenv('MEM_CONTINUUM_ERR_CSV', os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "C_err.csv")),
    "line_csv": os.getenv('MEM_LINE_CSV', os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "L_data.csv")),
    "line_err_csv": os.getenv('MEM_LINE_ERR_CSV', os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "L_err.csv")),
    "tau_pixels": int(os.getenv('MEM_TAU_PIXELS', '40')),
    "delay_min_days": 0.0,
    "delay_max_days": float(os.getenv('MEM_DELAY_MAX_DAYS', '40.0')),
}

try:
    import autograd.numpy as anp
    from autograd import value_and_grad as autograd_value_and_grad
    AUTOGRAD_AVAILABLE = True
except ImportError:
    anp = None
    autograd_value_and_grad = None
    AUTOGRAD_AVAILABLE = False

GRADIENT_BACKEND = os.getenv('MEM_GRADIENT_BACKEND', 'manual').strip().lower()
USE_JAX_JIT = os.getenv('MEM_USE_JAX_JIT', '0') == '1'
JAX_CACHE_DIR = os.getenv('MEM_JAX_CACHE_DIR', '').strip()
if GRADIENT_BACKEND not in ('manual', 'jax'):
    raise ValueError("MEM_GRADIENT_BACKEND must be 'manual' or 'jax'")
try:
    if GRADIENT_BACKEND != 'jax':
        raise ImportError('JAX is not needed for the selected manual backend')
    import jax
    import jax.numpy as jnp
    jax.config.update("jax_enable_x64", True)
    requested_device = os.getenv('MEM_JAX_DEVICE', 'cpu').strip().lower()
    if requested_device not in ('cpu', 'gpu', 'auto'):
        raise ValueError('MEM_JAX_DEVICE must be cpu, gpu or auto')
    try:
        selected_devices = jax.devices('gpu') if requested_device != 'cpu' else jax.devices('cpu')
    except RuntimeError:
        if requested_device == 'gpu':
            raise RuntimeError('GPU explicitly requested but unavailable. Native Windows JAX uses CPU; use a supported Linux/WSL2 CUDA environment.')
        selected_devices = jax.devices('cpu')
    if not selected_devices:
        raise RuntimeError('No device available for requested JAX backend')
    jax.config.update('jax_default_device', selected_devices[0])
    print(f'JAX selected device: {selected_devices[0]} (requested={requested_device})')
    if USE_JAX_JIT and JAX_CACHE_DIR:
        # JIT 仍由界面单独控制。磁盘缓存只减少相同程序/形状再次运行时
        # 的编译成本，不改变 Q、梯度或优化步骤。
        os.makedirs(JAX_CACHE_DIR, exist_ok=True)
        from jax.experimental.compilation_cache import compilation_cache as _jax_cc
        _jax_cc.set_cache_dir(JAX_CACHE_DIR)
        jax.config.update("jax_persistent_cache_min_compile_time_secs", 0)
    JAX_AVAILABLE = True
except ImportError:
    jax = None
    jnp = None
    JAX_AVAILABLE = False
if GRADIENT_BACKEND == 'jax' and not JAX_AVAILABLE:
    raise RuntimeError("JAX backend selected but jax is not installed")

np.random.seed(42)


# 1,读取数据

CONTINUUM_CSV_PATH = os.path.abspath(MEM_INPUT["continuum_csv"])
CONTINUUM_ERR_CSV_PATH = os.path.abspath(MEM_INPUT["continuum_err_csv"])
LINE_CSV_PATH = os.path.abspath(MEM_INPUT["line_csv"])
LINE_ERR_CSV_PATH = os.path.abspath(MEM_INPUT["line_err_csv"])
METADATA_CSV_PATH = os.path.join(
    os.path.dirname(CONTINUUM_CSV_PATH), "metadata.csv"
)

for required_path in (CONTINUUM_CSV_PATH, CONTINUUM_ERR_CSV_PATH,
                      LINE_CSV_PATH, LINE_ERR_CSV_PATH):
    if not os.path.exists(required_path):
        raise FileNotFoundError(f"Required observation file not found: {required_path}")

# 读取连续谱数据: time_days, continuum_flux
c_table = np.loadtxt(CONTINUUM_CSV_PATH, delimiter=",", skiprows=1, ndmin=2)
if c_table.shape[1] != 2:
    raise ValueError("C_data.csv needs: time_days,continuum_flux")
t_C = c_table[:, 0]
C_obs = c_table[:, 1]
if np.any(np.diff(t_C) <= 0):
    raise ValueError("C time must increase")

# 读取连续谱误差: time_days, continuum_error
c_err_table = np.loadtxt(CONTINUUM_ERR_CSV_PATH, delimiter=",", skiprows=1, ndmin=2)
if c_err_table.shape[1] != 2:
    raise ValueError("C_err.csv needs: time_days,continuum_error")
t_C_err = c_err_table[:, 0]
C_err = c_err_table[:, 1]
if not np.allclose(t_C, t_C_err):
    raise ValueError("C_data and C_err time axes do not match")
if np.any(C_err <= 0):
    raise ValueError("C errors must be positive")
t_C_obs = t_C.copy()

# 读取发射线数据: time_days, flux_v1, flux_v2, ...
with open(LINE_CSV_PATH, "r", encoding="utf-8-sig") as stream:
    l_headers = [x.strip() for x in stream.readline().strip().split(",")]
l_table = np.loadtxt(LINE_CSV_PATH, delimiter=",", skiprows=1, ndmin=2)
if l_headers[0] != "time_days":
    raise ValueError("L_data.csv first header must be time_days")

def header_velocity(text):
    match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
    if match is None:
        raise ValueError(f"No numeric velocity found in header {text!r}")
    return float(match.group())

velocities_list = []
flux_cols = []
for col, header in enumerate(l_headers[1:], start=1):
    if "flux" in header.lower():
        v = header_velocity(header)
        velocities_list.append(v)
        flux_cols.append(col)

velocities = np.asarray(velocities_list, dtype=float)
if np.all(np.diff(velocities) < 0):
    velocities = velocities[::-1]
    flux_cols = flux_cols[::-1]
elif not np.all(np.diff(velocities) > 0):
    raise ValueError("Velocity channels must be strictly monotonic")

t_L = l_table[:, 0]
if np.any(np.diff(t_L) <= 0):
    raise ValueError("L time must be strictly increasing")
L_obs = l_table[:, flux_cols].T
if not np.all(np.isfinite(L_obs)):
    raise ValueError("L flux must be finite")

# 读取发射线误差: time_days, error_v1, error_v2, ...
with open(LINE_ERR_CSV_PATH, "r", encoding="utf-8-sig") as stream:
    l_err_headers = [x.strip() for x in stream.readline().strip().split(",")]
l_err_table = np.loadtxt(LINE_ERR_CSV_PATH, delimiter=",", skiprows=1, ndmin=2)
if l_err_headers[0] != "time_days":
    raise ValueError("L_err.csv first header must be time_days")

error_cols = []
for col, header in enumerate(l_err_headers[1:], start=1):
    if "error" in header.lower():
        error_cols.append(col)

if len(error_cols) != len(flux_cols):
    raise ValueError("Number of error columns must match number of flux columns")

t_L_err = l_err_table[:, 0]
if not np.allclose(t_L, t_L_err):
    raise ValueError("L_data and L_err time axes do not match")
L_err = l_err_table[:, error_cols].T
if np.any(L_err <= 0):
    raise ValueError("L errors must be positive")

C_obs_physical = C_obs.copy()
C_err_physical = C_err.copy()
L_obs_physical = L_obs.copy()
L_err_physical = L_err.copy()
C_NORMALIZATION = float(np.mean(C_obs_physical))
L_NORMALIZATION = float(np.mean(L_obs_physical))
if (not np.isfinite(C_NORMALIZATION) or C_NORMALIZATION <= 0 or
        not np.isfinite(L_NORMALIZATION) or L_NORMALIZATION <= 0):
    raise ValueError("C and L normalization means must be finite and positive")
C_obs = C_obs_physical / C_NORMALIZATION
C_err = C_err_physical / C_NORMALIZATION
L_obs = L_obs_physical / L_NORMALIZATION
L_err = L_err_physical / L_NORMALIZATION
if not np.isclose(np.mean(C_obs), 1.0, rtol=1e-12, atol=1e-12):
    raise RuntimeError("C mean-normalization check failed")
if not np.isclose(np.mean(L_obs), 1.0, rtol=1e-12, atol=1e-12):
    raise RuntimeError("L mean-normalization check failed")
print("Input mean-normalization check")
print(f"C: physical mean={C_NORMALIZATION:.10g}, normalized mean={np.mean(C_obs):.10g}, "
      f"relative std={np.std(C_obs):.6g}")
print(f"L: physical mean={L_NORMALIZATION:.10g}, normalized mean={np.mean(L_obs):.10g}, "
      f"relative std={np.std(L_obs):.6g}")

# metadata 是可选的；旧数据会根据最小正时间差自动推断内部 cadence。
metadata = {}
if os.path.exists(METADATA_CSV_PATH):
    metadata_table = np.loadtxt(
        METADATA_CSV_PATH, delimiter=",", skiprows=1, dtype=str, ndmin=2
    )
    metadata = {row[0]: float(row[1]) for row in metadata_table}


def infer_base_cadence(times, metadata_key):
    if metadata_key in metadata:
        cadence = float(metadata[metadata_key])
    else:
        cadence = float(np.min(np.diff(times)))
    if cadence <= 0:
        raise ValueError("inferred full-grid cadence must be positive")
    return cadence


def regular_grid(start, stop, cadence):
    # 同时覆盖观测点 rint 索引，防止小数 cadence 的末端越界。
    count = max(int(np.floor((stop - start) / cadence + 1e-10)),
                int(np.rint((stop - start) / cadence))) + 1
    return start + np.arange(count, dtype=float) * cadence


def matern52_gp_initialization(model_times, observed_times, observed_values,
                               observed_errors, length_scale_days):
    """带观测误差的 Matérn-5/2 GP 条件均值/标准差，仅用作 gap 初值和可视化。"""
    if length_scale_days <= 0:
        raise ValueError("MEM_GAP_GP_TIMESCALE_DAYS must be positive")
    mean = float(np.mean(observed_values))
    amplitude = max(float(np.std(observed_values)), float(np.median(observed_errors)))

    def kernel(x, y):
        distance = np.abs(x[:, None] - y[None, :])
        scaled = np.sqrt(5.0) * distance / length_scale_days
        return amplitude ** 2 * (1.0 + scaled + scaled ** 2 / 3.0) * np.exp(-scaled)

    K_oo = kernel(observed_times, observed_times)
    K_oo.flat[::len(observed_times) + 1] += observed_errors ** 2 + 1e-10 * amplitude ** 2
    K_go = kernel(model_times, observed_times)
    chol = np.linalg.cholesky(K_oo)
    alpha = np.linalg.solve(chol.T, np.linalg.solve(chol, observed_values - mean))
    conditional_mean = mean + K_go @ alpha
    projected = np.linalg.solve(chol, K_go.T)
    conditional_variance = np.maximum(amplitude ** 2 - np.sum(projected ** 2, axis=0), 0.0)
    return conditional_mean, np.sqrt(conditional_variance)


def fit_matern52_timescale(observed_times, observed_values, observed_errors,
                           cadence_days):
    """用观测点的边际似然拟合 GP 时间尺度；绝不读取 gap 真值。"""
    centered = observed_values - np.mean(observed_values)
    amplitude = max(float(np.std(observed_values)), float(np.median(observed_errors)))
    distance = np.abs(observed_times[:, None] - observed_times[None, :])

    def negative_log_likelihood(log_length):
        length = float(np.exp(np.asarray(log_length).reshape(-1)[0]))
        scaled = np.sqrt(5.0) * distance / length
        covariance = amplitude ** 2 * (
            1.0 + scaled + scaled ** 2 / 3.0
        ) * np.exp(-scaled)
        covariance.flat[::len(observed_times) + 1] += (
            observed_errors ** 2 + 1e-10 * amplitude ** 2
        )
        try:
            chol = np.linalg.cholesky(covariance)
        except np.linalg.LinAlgError:
            return 1e100
        solved = np.linalg.solve(chol, centered)
        return float(
            0.5 * solved @ solved
            + np.sum(np.log(np.diag(chol)))
            + 0.5 * len(centered) * np.log(2.0 * np.pi)
        )

    span = max(float(observed_times[-1] - observed_times[0]), cadence_days)
    bounds = [(np.log(max(cadence_days, 1e-6)),
               np.log(max(2.0 * span, cadence_days)))]
    result = minimize(
        negative_log_likelihood,
        x0=np.array([np.log(min(max(30.0, cadence_days), span))]),
        method="L-BFGS-B", bounds=bounds,
        options={"maxiter": 60, "ftol": 1e-10},
    )
    return float(np.exp(result.x[0]))


# C 参数在跨越 seasonal gap 的完整内部网格上重建；观测 chi2 只用 t_C_obs。
C_GRID_CADENCE = infer_base_cadence(t_C_obs, "full_C_cadence_days")
t_C = regular_grid(t_C_obs[0], t_C_obs[-1], C_GRID_CADENCE)
gap_timescale_setting = os.getenv('MEM_GAP_GP_TIMESCALE_DAYS', 'auto').strip().lower()
if gap_timescale_setting == 'auto':
    GAP_GP_TIMESCALE_DAYS = fit_matern52_timescale(
        t_C_obs, C_obs, C_err, C_GRID_CADENCE
    )
else:
    GAP_GP_TIMESCALE_DAYS = float(gap_timescale_setting)
C_initial_grid, C_GP_STD = matern52_gp_initialization(
    t_C, t_C_obs, C_obs, C_err, GAP_GP_TIMESCALE_DAYS
)
C_initial_grid = np.clip(C_initial_grid, 1e-8, None)

# 标记哪些内部 C 像素有直接观测。
C_OBSERVED_GRID_MASK = np.zeros(len(t_C), dtype=bool)
observed_indices = np.rint((t_C_obs - t_C[0]) / C_GRID_CADENCE).astype(int)
C_OBSERVED_GRID_MASK[observed_indices] = True
C_GAP_MASK = ~C_OBSERVED_GRID_MASK
C_initial_grid[observed_indices] = C_obs

L_GRID_CADENCE = infer_base_cadence(t_L, "full_L_cadence_days")
t_L_model = regular_grid(t_L[0], t_L[-1], L_GRID_CADENCE)
L_OBSERVED_GRID_MASK = np.zeros(len(t_L_model), dtype=bool)
l_observed_indices = np.rint((t_L - t_L_model[0]) / L_GRID_CADENCE).astype(int)
L_OBSERVED_GRID_MASK[l_observed_indices] = True
L_GAP_MASK = ~L_OBSERVED_GRID_MASK

N_t_C, N_t_L, N_v = len(t_C), len(t_L), len(velocities)
N_tau = int(MEM_INPUT["tau_pixels"])
delays = np.linspace(MEM_INPUT["delay_min_days"], MEM_INPUT["delay_max_days"], N_tau)
d_tau = delays[1]-delays[0]
N_pixels = N_v*N_tau

C0_MODE = os.getenv('MEM_C0_MODE', 'real_data_mean').lower()
if C0_MODE == 'real_data_mean':
    C_bar_fixed = float(np.mean(C_obs))
elif C0_MODE == 'observed_median':
    C_bar_fixed = float(np.median(C_obs))
elif C0_MODE == 'simulation_truth':
    C_bar_fixed = float(os.getenv('MEM_C0_TRUTH', '2.0')) / C_NORMALIZATION
else:
    raise ValueError(
        "MEM_C0_MODE must be real_data_mean, observed_median, or simulation_truth"
    )

L_bg_initial = np.clip(np.percentile(L_obs, 10, axis=1), 1e-8, None)
L_variable_scale = np.nanmax(np.abs(L_obs - L_bg_initial[:, None]))

print(f"Fixed C_bar = {C_bar_fixed:.4f} normalized, "
      f"{C_bar_fixed * C_NORMALIZATION:.4f} physical (mode={C0_MODE})")
print(f"Median C_obs = {np.median(C_obs):.4f} normalized, "
      f"{np.median(C_obs_physical):.4f} physical")
print(f"C: {len(t_C_obs)} observed / {N_t_C} model epochs, "
      f"cadence={C_GRID_CADENCE:.6g} d")
print(f"L: {N_t_L} observed / {len(t_L_model)} model epochs x {N_v} velocities, "
      f"cadence={L_GRID_CADENCE:.6g} d")
print(f"Detected missing epochs: C={N_t_C-len(t_C_obs)}, "
      f"L={len(t_L_model)-N_t_L}")
print(f"Matérn-5/2 GP timescale = {GAP_GP_TIMESCALE_DAYS:.6g} d "
      f"(setting={gap_timescale_setting})")
print(f"Common temporal Gaussian sigma from metadata = "
      f"{metadata.get('time_broadening_sigma_days', 0.0):.6g} d")
print(f"Velocity: {velocities[0]:.6g}..{velocities[-1]:.6g} km/s")


def build_interpolation_matrix(t_target, t_grid):
    M = np.zeros((len(t_target), len(t_grid)))
    for i, t in enumerate(t_target):
        idx = np.clip(np.searchsorted(t_grid, t) - 1, 0, len(t_grid) - 2)
        if idx < len(t_grid) - 1:
            w1 = (t - t_grid[idx]) / (t_grid[idx+1] - t_grid[idx])
            M[i, idx] = 1.0 - w1
            M[i, idx+1] = w1
        else:
            M[i, -1] = 1.0
    return M


def build_interpolation_stencil(t_target, t_grid):
    """用每个目标时刻的左/右索引和右权重表示线性插值。"""
    right = np.searchsorted(t_grid, t_target, side="right")
    right = np.clip(right, 1, len(t_grid) - 1).astype(np.int64)
    left = (right - 1).astype(np.int64)
    weight_right = (
        (t_target - t_grid[left]) / (t_grid[right] - t_grid[left])
    ).astype(np.float64)
    return left, right, weight_right


if NUMBA_AVAILABLE:
    @njit(cache=False)
    def _interpolate_stencil_numba(values, left, right, weight_right):
        result = np.empty(left.size, dtype=np.float64)
        for i in range(left.size):
            wr = weight_right[i]
            result[i] = (1.0 - wr) * values[left[i]] + wr * values[right[i]]
        return result


    @njit(cache=False)
    def _scatter_stencil_numba(source, left, right, weight_right, output_size):
        result = np.zeros(output_size, dtype=np.float64)
        for i in range(left.size):
            wr = weight_right[i]
            result[left[i]] += (1.0 - wr) * source[i]
            result[right[i]] += wr * source[i]
        return result


def interpolate_stencil(values):
    if USE_NUMBA:
        return _interpolate_stencil_numba(
            values, REQ_LEFT, REQ_RIGHT, REQ_WEIGHT_RIGHT
        )
    return np.asarray(M_req @ values).reshape(-1)


def scatter_stencil(source):
    if USE_NUMBA:
        return _scatter_stencil_numba(
            source, REQ_LEFT, REQ_RIGHT, REQ_WEIGHT_RIGHT, N_t_C
        )
    return np.asarray(M_req.T @ source).reshape(-1)

M_obs = build_interpolation_matrix(t_C_obs, t_C)
t_req = (t_L[:, None] - delays[None, :]).flatten()
if t_req.min() < t_C.min() or t_req.max() > t_C.max():
    raise ValueError(
        "Continuum grid must cover every t_L - tau value; "
        "extend/reconstruct C before running MEM instead of relying on extrapolation."
    )
M_req = build_interpolation_matrix(t_req, t_C)
REQ_LEFT, REQ_RIGHT, REQ_WEIGHT_RIGHT = build_interpolation_stencil(t_req, t_C)

# 哪些 C 网格点至少进入一个实际观测到的 L(t,v) 预测。其余 gap 中央既无 C
# 数据，也不可能通过 L 的卷积得到约束；那里只能报告随机过程先验及其不确定度。
C_LINE_CONSTRAINED_MASK = np.zeros(N_t_C, dtype=bool)
C_LINE_CONSTRAINED_MASK[np.unique(REQ_LEFT)] = True
C_LINE_CONSTRAINED_MASK[np.unique(REQ_RIGHT)] = True
C_GAP_LINE_INFORMED_MASK = C_GAP_MASK & C_LINE_CONSTRAINED_MASK
C_GAP_UNIDENTIFIABLE_MASK = C_GAP_MASK & ~C_LINE_CONSTRAINED_MASK
print(f"Gap identifiability: {np.sum(C_GAP_LINE_INFORMED_MASK)} C epochs enter "
      f"observed L; {np.sum(C_GAP_UNIDENTIFIABLE_MASK)} epochs are prior-only")

print(f"M_req shape: {M_req.shape}")
print(
    "Sparse interpolation backend: "
    + ("Numba" if USE_NUMBA else "NumPy/BLAS")
    + ("" if NUMBA_AVAILABLE else " (Numba not installed)")
)


# 6,参数

POSITIVE_FLOOR = 1e-10
MAP_SLICE = slice(0, N_pixels)
C_SLICE = slice(N_pixels, N_pixels + N_t_C)
LBG_SLICE = slice(N_pixels + N_t_C, N_pixels + N_t_C + N_v)
N_total = N_pixels + N_t_C + N_v

# gap 曲率先验：只惩罚中心在 gap 内或三点 stencil 接触 gap 的二阶差分。
# 因此 gap 内平滑，两个边界的斜率/曲率也不会突然折断。
GAP_CURVATURE_WEIGHT = float(os.getenv('MEM_GAP_CURVATURE_WEIGHT', '10.0'))
if GAP_CURVATURE_WEIGHT < 0:
    raise ValueError("MEM_GAP_CURVATURE_WEIGHT must be non-negative")

# 目标函数尺度归一化测试：C、L 两个数据块分别使用各自的平均 chi2。
# 这使数据块权重不再由“L 有多少速度通道”暗中决定。
CHI2_C_SCALE = 1.0 / float(C_obs.size)
CHI2_L_SCALE = 1.0 / float(L_obs.size)
D2_C = np.zeros((max(N_t_C - 2, 0), N_t_C))
for row in range(N_t_C - 2):
    D2_C[row, row:row + 3] = (1.0, -2.0, 1.0)
GAP_CURVATURE_ROWS = np.array([
    np.any(C_GAP_MASK[row:row + 3]) for row in range(N_t_C - 2)
], dtype=float)
GAP_TERM_SCALE = 1.0 / float(max(1, np.count_nonzero(GAP_CURVATURE_ROWS)))
EFFECTIVE_GAP_CURVATURE_WEIGHT = GAP_CURVATURE_WEIGHT * GAP_TERM_SCALE
GAP_CURVATURE_SCALE = max(float(np.std(C_obs)), float(np.median(C_err)), 1e-8)
print(
    "Objective-scale normalization test: "
    f"chi2_C/{C_obs.size} + chi2_L/{L_obs.size}; "
    f"gap curvature/{max(1, np.count_nonzero(GAP_CURVATURE_ROWS))}"
)


def compute_gap_curvature(values):
    if GAP_CURVATURE_WEIGHT == 0 or not np.any(GAP_CURVATURE_ROWS):
        return 0.0, np.zeros_like(values)
    second_difference = D2_C @ values
    weighted = GAP_CURVATURE_ROWS * second_difference
    penalty = 0.5 * np.sum(weighted ** 2) / GAP_CURVATURE_SCALE ** 2
    gradient = D2_C.T @ (GAP_CURVATURE_ROWS * weighted) / GAP_CURVATURE_SCALE ** 2
    return float(penalty), gradient

# C0 固定
q_flat = np.full(N_pixels, 1.0 / N_pixels)
q_C = np.full(N_t_C, C_bar_fixed)
q_L_bg = L_bg_initial.copy()


def geometric_default_1d(values):
    """一维地图优化"""
    p = np.clip(values, POSITIVE_FLOOR, None)
    if p.size == 1:
        return p.copy()
    q = np.empty_like(p)
    q[1:-1] = np.sqrt(p[:-2] * p[2:])
    q[0] = np.sqrt(p[0] * p[1])
    q[-1] = np.sqrt(p[-2] * p[-1])
    return q


def geometric_default_2d(values_2d, smoothness_ratio=1.0):
    """二维地图在速度，时延方向优化"""
    if smoothness_ratio <= 0:
        raise ValueError("smoothness_ratio must be positive")
    p = np.clip(values_2d, POSITIVE_FLOOR, None)
    if p.shape[0] == 1:
        return geometric_default_1d(p[0])[None, :]

    q_v = np.empty_like(p)
    q_v[1:-1, :] = np.sqrt(p[:-2, :] * p[2:, :])
    q_v[0, :] = np.sqrt(p[0, :] * p[1, :])
    q_v[-1, :] = np.sqrt(p[-2, :] * p[-1, :])

    q_tau = np.empty_like(p)
    q_tau[:, 1:-1] = np.sqrt(p[:, :-2] * p[:, 2:])
    q_tau[:, 0] = np.sqrt(p[:, 0] * p[:, 1])
    q_tau[:, -1] = np.sqrt(p[:, -2] * p[:, -1])

    weight_v = smoothness_ratio / (1.0 + smoothness_ratio)
    weight_tau = 1.0 / (1.0 + smoothness_ratio)
    return (q_v ** weight_v) * (q_tau ** weight_tau)


# 7,熵与手写梯度

def unpack_parameters(w):
    """按 [Psi.flatten(), C(t), L0(v)] 拆分一维优化向量。"""
    return w[MAP_SLICE], w[C_SLICE], w[LBG_SLICE]


def compute_L_pred(p_flat, C_values, L_bg):
    """二维传递函数与 C-C0 卷积，再加上逐速度像素的 L0(v)。"""
    p_2d = p_flat.reshape(N_v, N_tau)
    delta_C_grid = interpolate_stencil(
        C_values - C_bar_fixed
    ).reshape(N_t_L, N_tau)
    L_variable = (p_2d @ delta_C_grid.T) * d_tau
    return L_variable + L_bg[:, None], delta_C_grid


def compute_entropy(image, default):
    """Skilling 相对熵 S=sum[p-q-p log(p/q)] 及其解析梯度。"""
    # 优化器的正值边界已保证 p,q>0，这里不再用 maximum/clip。
    # 否则在 p == POSITIVE_FLOOR 的不可导点，手写梯度与
    # autograd 选取的次梯度会不同。
    if np.any(image <= 0.0) or np.any(default <= 0.0):
        raise ValueError("MEM entropy requires strictly positive image and default")
    log_ratio = np.log(image / default)
    S = np.sum(image - default - image * log_ratio)
    grad_S = -log_ratio
    return S, grad_S


def entropy_scale(default):
    """把MEM熵除以default总量，降低参数个数/像素尺度依赖。"""
    return 1.0 / max(float(np.sum(default)), POSITIVE_FLOOR)


def compute_chi2_and_gradients(w):
    """返回两个 chi2、三个参数块的解析梯度和模型预测。"""
    p_flat, C_values, L_bg = unpack_parameters(w)

    C_pred = M_obs @ C_values
    raw_C = C_pred - C_obs
    weighted_C = raw_C / (C_err ** 2)
    chi2_C = np.sum((raw_C / C_err) ** 2)
    grad_C_from_C = 2.0 * (M_obs.T @ weighted_C)

    L_pred, delta_C_grid = compute_L_pred(p_flat, C_values, L_bg)
    raw_L = L_pred - L_obs
    weighted_L = raw_L / (L_err ** 2)
    chi2_L = np.sum((raw_L / L_err) ** 2)

    p_2d = p_flat.reshape(N_v, N_tau)
    grad_map = (
        CHI2_L_SCALE * 2.0 * weighted_L @ delta_C_grid * d_tau
    ).reshape(-1)
    grad_delta_C_grid = CHI2_L_SCALE * 2.0 * weighted_L.T @ p_2d * d_tau
    grad_C_from_L = scatter_stencil(grad_delta_C_grid.reshape(-1))
    grad_C = CHI2_C_SCALE * grad_C_from_C + grad_C_from_L
    grad_L_bg = CHI2_L_SCALE * 2.0 * np.sum(weighted_L, axis=1)

    return chi2_C, chi2_L, (grad_map, grad_C, grad_L_bg), C_pred, L_pred


# 8,三种优化参数块各自的TEST

def compute_component_test(grad_chi2, grad_S, values):
    """Horne (1994) 的欧氏梯度夹角 TEST=1-cos(theta)。"""
    active = values > 100.0 * POSITIVE_FLOOR
    if not np.any(active):
        return 0.0

    g_chi2 = grad_chi2[active]
    g_S = grad_S[active]
    norm_chi2 = np.linalg.norm(g_chi2)
    norm_S = np.linalg.norm(g_S)
    tiny = 1e-14
    if norm_chi2 < tiny and norm_S < tiny:
        return 0.0
    if norm_chi2 < tiny or norm_S < tiny:
        return 1.0

    cos_theta = np.dot(g_chi2, g_S) / (norm_chi2 * norm_S)
    return float(1.0 - np.clip(cos_theta, -1.0, 1.0))


def background_at_float_resolution(gradient, values, alpha):
    """The profiled convex background cannot move below float64 resolution.

    Relative angles become undefined when both data and entropy gradients vanish.
    Independently require the Newton correction to be <= 32 float64 eps in every
    background channel; this does not relax map/C tolerances or alter Q.
    """
    curvature = (2.0 * CHI2_L_SCALE * np.sum(1.0 / L_err**2, axis=1)
                 + alpha * entropy_scale(q_L_bg) / values)
    correction = np.abs(gradient) / (curvature * np.maximum(values, POSITIVE_FLOOR))
    return bool(np.all(np.isfinite(correction)) and
                np.all(correction <= 32.0 * np.finfo(float).eps))


def compute_all_tests(w):
    p_flat, C_values, L_bg = unpack_parameters(w)
    _, _, grad_chi2, _, _ = compute_chi2_and_gradients(w)
    _, grad_S_map = compute_entropy(p_flat, q_flat)
    _, grad_S_C = compute_entropy(C_values, q_C)
    _, grad_S_L = compute_entropy(L_bg, q_L_bg)
    _, grad_gap_C = compute_gap_curvature(C_values)
    effective_C_regularizer = (
        ALPHA_C * entropy_scale(q_C) * grad_S_C
        - EFFECTIVE_GAP_CURVATURE_WEIGHT * grad_gap_C
    )
    return {
        'TEST_map': compute_component_test(
            grad_chi2[0], entropy_scale(q_flat) * grad_S_map, p_flat
        ),
        'TEST_C': compute_component_test(
            grad_chi2[1], effective_C_regularizer, C_values
        ),
        'TEST_L_bg': 0.0 if background_at_float_resolution(
            grad_chi2[2] - ALPHA_L_BG * entropy_scale(q_L_bg) * grad_S_L,
            L_bg, ALPHA_L_BG
        ) else compute_component_test(
            grad_chi2[2], entropy_scale(q_L_bg) * grad_S_L, L_bg
        ),
    }


def compute_relative_Q_gradients(w, alpha_map, alpha_C, alpha_L_bg):
    """补充检查梯度幅值，防止 TEST 只因方向平行而过早停止。"""
    p_flat, C_values, L_bg = unpack_parameters(w)
    _, _, grad_chi2, _, _ = compute_chi2_and_gradients(w)
    _, grad_S_map = compute_entropy(p_flat, q_flat)
    _, grad_S_C = compute_entropy(C_values, q_C)
    _, grad_S_L = compute_entropy(L_bg, q_L_bg)
    _, grad_gap_C = compute_gap_curvature(C_values)

    diagnostics = {}
    blocks = (
        ('map', p_flat, grad_chi2[0],
         alpha_map * entropy_scale(q_flat) * grad_S_map),
        ('C', C_values, grad_chi2[1],
         alpha_C * entropy_scale(q_C) * grad_S_C
         - EFFECTIVE_GAP_CURVATURE_WEIGHT * grad_gap_C),
        ('L_bg', L_bg, grad_chi2[2],
         alpha_L_bg * entropy_scale(q_L_bg) * grad_S_L),
    )
    for name, values, grad_data, grad_entropy in blocks:
        if name == 'L_bg' and background_at_float_resolution(
                grad_data - grad_entropy, values, alpha_L_bg):
            diagnostics[name] = 0.0
            continue
        active = values > 100.0 * POSITIVE_FLOOR
        q_grad = grad_data[active] - grad_entropy[active]
        denominator = max(
            np.linalg.norm(grad_data[active]),
            np.linalg.norm(grad_entropy[active]),
            1e-14,
        )
        diagnostics[name] = float(np.linalg.norm(q_grad) / denominator)
    if np.any(C_GAP_MASK):
        gap_q_gradient = (
            grad_chi2[1] - alpha_C * entropy_scale(q_C) * grad_S_C
            + EFFECTIVE_GAP_CURVATURE_WEIGHT * grad_gap_C
        )[C_GAP_MASK]
        gap_denominator = max(
            np.linalg.norm(grad_chi2[1][C_GAP_MASK]),
            np.linalg.norm((alpha_C * entropy_scale(q_C) * grad_S_C
                            - EFFECTIVE_GAP_CURVATURE_WEIGHT * grad_gap_C)[C_GAP_MASK]),
            1e-14,
        )
        diagnostics['C_gap'] = float(np.linalg.norm(gap_q_gradient) / gap_denominator)
    return diagnostics


# 9，Q 目标函数及交给优化器的手写解析梯度

def objective_Q_with_manual_gradient(w, alpha_map, alpha_C, alpha_L_bg):
    # There is no independent chi2_map because the map is not directly observed.
    # Psi enters chi2_L through L_pred. 023 never reads or uses simulation truth.
    p_flat, C_values, L_bg = unpack_parameters(w)
    chi2_C, chi2_L, grad_chi2, _, _ = compute_chi2_and_gradients(w)
    S_map, grad_S_map = compute_entropy(p_flat, q_flat)
    S_C, grad_S_C = compute_entropy(C_values, q_C)
    S_L, grad_S_L = compute_entropy(L_bg, q_L_bg)
    gap_curvature, grad_gap_C = compute_gap_curvature(C_values)

    Q = (CHI2_C_SCALE * chi2_C + CHI2_L_SCALE * chi2_L
         - alpha_map * entropy_scale(q_flat) * S_map
         - alpha_C * entropy_scale(q_C) * S_C
         - alpha_L_bg * entropy_scale(q_L_bg) * S_L
         + EFFECTIVE_GAP_CURVATURE_WEIGHT * gap_curvature)
    grad_Q = np.concatenate([
        grad_chi2[0] - alpha_map * entropy_scale(q_flat) * grad_S_map,
        grad_chi2[1] - alpha_C * entropy_scale(q_C) * grad_S_C
        + EFFECTIVE_GAP_CURVATURE_WEIGHT * grad_gap_C,
        grad_chi2[2] - alpha_L_bg * entropy_scale(q_L_bg) * grad_S_L,
    ])
    return Q, grad_Q


def _objective_Q_autograd_value(w, alpha_map, alpha_C, alpha_L_bg):
    """与手写版本完全同构的纯标量 Q，专供 autograd 求导。"""
    p_flat = w[MAP_SLICE]
    C_values = w[C_SLICE]
    L_bg = w[LBG_SLICE]

    C_pred = anp.dot(M_obs, C_values)
    raw_C = C_pred - C_obs
    chi2_C = anp.sum((raw_C / C_err) ** 2)

    delta_C_grid = anp.reshape(
        anp.dot(M_req, C_values - C_bar_fixed), (N_t_L, N_tau)
    )
    p_2d = anp.reshape(p_flat, (N_v, N_tau))
    L_pred = anp.dot(p_2d, anp.transpose(delta_C_grid)) * d_tau + L_bg[:, None]
    chi2_L = anp.sum(((L_pred - L_obs) / L_err) ** 2)

    def entropy_autograd(image, default):
        # 与手写版使用同一个光滑表达式；正值由优化器边界保证。
        return anp.sum(image - default - image * anp.log(image / default))

    second_difference_C = anp.dot(D2_C, C_values)
    gap_curvature = (
        0.5 * anp.sum((GAP_CURVATURE_ROWS * second_difference_C) ** 2)
        / GAP_CURVATURE_SCALE ** 2
    )

    return (
        CHI2_C_SCALE * chi2_C + CHI2_L_SCALE * chi2_L
        - alpha_map * entropy_autograd(p_flat, q_flat) / anp.sum(q_flat)
        - alpha_C * entropy_autograd(C_values, q_C) / anp.sum(q_C)
        - alpha_L_bg * entropy_autograd(L_bg, q_L_bg) / anp.sum(q_L_bg)
        + EFFECTIVE_GAP_CURVATURE_WEIGHT * gap_curvature
    )


if AUTOGRAD_AVAILABLE:
    _autograd_Q_and_gradient = autograd_value_and_grad(_objective_Q_autograd_value)


def objective_Q_with_autodiff_gradient(w, alpha_map, alpha_C, alpha_L_bg):
    """自动微分版 Q/梯度；缺少可选依赖时给出明确错误。"""
    if not AUTOGRAD_AVAILABLE:
        raise RuntimeError("autograd is required: python -m pip install autograd")
    Q, grad_Q = _autograd_Q_and_gradient(
        w, alpha_map, alpha_C, alpha_L_bg
    )
    return float(Q), np.asarray(grad_Q, dtype=float)


if JAX_AVAILABLE:
    # 这些量在整个重构过程中不改变。只传入 JAX 一次，避免 SciPy 每次
    # 评价 Q 时反复执行 NumPy -> JAX 的复制/封装。
    _JAX_M_OBS = jax.device_put(M_obs)
    _JAX_C_OBS = jax.device_put(C_obs)
    _JAX_C_ERR = jax.device_put(C_err)
    _JAX_M_REQ = jax.device_put(M_req)
    _JAX_L_OBS = jax.device_put(L_obs)
    _JAX_L_ERR = jax.device_put(L_err)
    _JAX_D2_C = jax.device_put(D2_C)
    _JAX_GAP_CURVATURE_ROWS = jax.device_put(GAP_CURVATURE_ROWS)

    def _objective_Q_jax_value(w, q_map_value, q_C_value, q_L_value,
                               alpha_map, alpha_C, alpha_L_bg):
        p_flat = w[MAP_SLICE]
        C_values = w[C_SLICE]
        L_bg = w[LBG_SLICE]
        C_pred = _JAX_M_OBS @ C_values
        chi2_C = jnp.sum(((C_pred - _JAX_C_OBS) / _JAX_C_ERR) ** 2)
        delta_C_grid = (
            _JAX_M_REQ @ (C_values - C_bar_fixed)
        ).reshape(N_t_L, N_tau)
        p_2d = p_flat.reshape(N_v, N_tau)
        L_model = p_2d @ delta_C_grid.T * d_tau + L_bg[:, None]
        chi2_L = jnp.sum(((L_model - _JAX_L_OBS) / _JAX_L_ERR) ** 2)

        def entropy_jax(image, default):
            return jnp.sum(image - default - image * jnp.log(image / default))

        second_difference_C = _JAX_D2_C @ C_values
        gap_curvature = (
            0.5 * jnp.sum(
                (_JAX_GAP_CURVATURE_ROWS * second_difference_C) ** 2
            ) / GAP_CURVATURE_SCALE ** 2
        )
        return (
            CHI2_C_SCALE * chi2_C + CHI2_L_SCALE * chi2_L
            - alpha_map * entropy_jax(p_flat, q_map_value) / jnp.sum(q_map_value)
            - alpha_C * entropy_jax(C_values, q_C_value) / jnp.sum(q_C_value)
            - alpha_L_bg * entropy_jax(L_bg, q_L_value) / jnp.sum(q_L_value)
            + EFFECTIVE_GAP_CURVATURE_WEIGHT * gap_curvature
        )

    _jax_Q_and_gradient_plain = jax.value_and_grad(_objective_Q_jax_value)
    _jax_Q_and_gradient_jit = jax.jit(_jax_Q_and_gradient_plain)

_jax_default_source_ids = None
_jax_default_device_values = None
_jax_evaluation_count = 0
_jax_first_evaluation_seconds = None


def _jax_defaults_on_device():
    """每组冻结 default 只复制一次；外层更新后自动刷新。"""
    global _jax_default_source_ids, _jax_default_device_values
    source_ids = (id(q_flat), id(q_C), id(q_L_bg))
    if source_ids != _jax_default_source_ids:
        _jax_default_device_values = tuple(
            jax.device_put(value) for value in (q_flat, q_C, q_L_bg)
        )
        _jax_default_source_ids = source_ids
    return _jax_default_device_values


def objective_Q_with_jax_gradient(w, alpha_map, alpha_C, alpha_L_bg):
    global _jax_evaluation_count, _jax_first_evaluation_seconds
    if not JAX_AVAILABLE:
        raise RuntimeError("JAX backend selected but jax is not installed")
    evaluator = _jax_Q_and_gradient_jit if USE_JAX_JIT else _jax_Q_and_gradient_plain
    q_map_jax, q_C_jax, q_L_jax = _jax_defaults_on_device()
    started = time.perf_counter() if _jax_evaluation_count == 0 else None
    Q, grad_Q = evaluator(
        jax.device_put(w), q_map_jax, q_C_jax, q_L_jax,
        alpha_map, alpha_C, alpha_L_bg
    )
    # JAX 异步执行；第一次必须同步后计时，数字才包含真实编译时间。
    if started is not None:
        Q.block_until_ready()
        _jax_first_evaluation_seconds = time.perf_counter() - started
        print(
            f"JAX first Q/gradient evaluation: {_jax_first_evaluation_seconds:.3f} s "
            f"(includes JIT compilation={USE_JAX_JIT})"
        )
    _jax_evaluation_count += 1
    return float(Q), np.asarray(grad_Q, dtype=float)


def objective_Q_selected(w, alpha_map, alpha_C, alpha_L_bg):
    if GRADIENT_BACKEND == 'jax':
        return objective_Q_with_jax_gradient(w, alpha_map, alpha_C, alpha_L_bg)
    return objective_Q_with_manual_gradient(w, alpha_map, alpha_C, alpha_L_bg)


def run_one_block_cycle(w_start, objective_function,
                        alpha_map, alpha_C, alpha_L_bg,
                        block_maxiter=40):
    """按 Psi -> C -> L0 顺序跑一轮，用于手写/自动微分公平对比。"""
    w = w_start.copy()
    scales = np.concatenate([
        np.full(N_pixels, 1.0 / N_pixels),
        np.full(N_t_C, np.median(C_err)),
        np.full(N_v, np.median(w_start[LBG_SLICE])),
    ])
    for block in (MAP_SLICE, C_SLICE, LBG_SLICE):
        fixed_w = w.copy()
        block_scale = scales[block]

        def block_objective(z, block=block, fixed_w=fixed_w,
                            block_scale=block_scale):
            trial_w = fixed_w.copy()
            trial_w[block] = z * block_scale
            Q, grad_w = objective_function(
                trial_w, alpha_map, alpha_C, alpha_L_bg
            )
            return Q, grad_w[block] * block_scale

        result = minimize(
            block_objective,
            w[block] / block_scale,
            jac=True,
            method='L-BFGS-B',
            bounds=[(POSITIVE_FLOOR / scale, None) for scale in block_scale],
            options={'maxiter': block_maxiter, 'ftol': 1e-15, 'gtol': 1e-10},
        )
        w[block] = result.x * block_scale
    return w


def check_manual_Q_gradient(w, alpha_map, alpha_C, alpha_L_bg, seed=7):
    """用三个独立方向差分检查 Q 手写梯度，不参与优化。"""
    rng = np.random.default_rng(seed)
    Q, grad = objective_Q_with_manual_gradient(
        w, alpha_map, alpha_C, alpha_L_bg
    )
    del Q
    checks = {}
    for name, block in [('map', MAP_SLICE), ('C', C_SLICE), ('L_bg', LBG_SLICE)]:
        direction = np.zeros_like(w)
        direction[block] = rng.normal(size=w[block].size)
        direction /= np.linalg.norm(direction)
        max_step = np.min(w[block] / (np.abs(direction[block]) + 1e-30))
        step = min(1e-6, 0.1 * max_step)
        Q_plus = objective_Q_with_manual_gradient(
            w + step * direction, alpha_map, alpha_C, alpha_L_bg
        )[0]
        Q_minus = objective_Q_with_manual_gradient(
            w - step * direction, alpha_map, alpha_C, alpha_L_bg
        )[0]
        finite_difference = (Q_plus - Q_minus) / (2.0 * step)
        analytic = float(np.dot(grad, direction))
        relative_error = abs(finite_difference - analytic) / max(
            1.0, abs(finite_difference), abs(analytic)
        )
        checks[name] = relative_error
    return checks


def enforce_finite_difference_gradient_check(
        w, alpha_map, alpha_C, alpha_L_bg,
        tolerance=1e-4, context='initial'):
    """Stop before optimization if any block fails the directional check."""
    errors = check_manual_Q_gradient(
        w, alpha_map, alpha_C, alpha_L_bg
    )
    bad = {
        name: value for name, value in errors.items()
        if (not np.isfinite(value)) or value > tolerance
    }
    print(
        f"FINITE-DIFFERENCE GRADIENT CHECK ({context}): "
        + ", ".join(f"{k}={v:.3e}" for k, v in errors.items())
    )
    if bad:
        raise RuntimeError(
            f"Manual Q gradient finite-difference check failed at {context}: "
            f"{bad}; tolerance={tolerance:.3e}. Optimization stopped."
        )
    return errors


def enforce_autodiff_gradient_check(
        w, alpha_map, alpha_C, alpha_L_bg,
        gradient_tolerance=1e-7, q_tolerance=1e-10,
        context='initial'):
    """Compare the complete manual gradient with autograd and fail loudly."""
    if not AUTOGRAD_AVAILABLE:
        raise RuntimeError(
            "Automatic gradient checking is required but autograd is not "
            "installed. Run: python -m pip install autograd"
        )
    q_manual, grad_manual = objective_Q_with_manual_gradient(
        w, alpha_map, alpha_C, alpha_L_bg
    )
    q_auto, grad_auto = objective_Q_with_autodiff_gradient(
        w, alpha_map, alpha_C, alpha_L_bg
    )
    q_relative_error = abs(q_manual - q_auto) / max(
        1.0, abs(q_manual), abs(q_auto)
    )
    gradient_relative_error = np.linalg.norm(
        grad_manual - grad_auto
    ) / max(
        1.0, np.linalg.norm(grad_manual), np.linalg.norm(grad_auto)
    )
    print(
        f"AUTODIFF GRADIENT CHECK ({context}): "
        f"Q_rel={q_relative_error:.3e}, "
        f"grad_rel={gradient_relative_error:.3e}"
    )
    invalid = not all(np.isfinite(value) for value in (
        q_manual, q_auto, q_relative_error, gradient_relative_error
    ))
    if (invalid or q_relative_error > q_tolerance
            or gradient_relative_error > gradient_tolerance):
        raise RuntimeError(
            f"Manual/autodiff gradient check failed at {context}: "
            f"Q relative error={q_relative_error:.3e} "
            f"(limit {q_tolerance:.3e}), gradient relative error="
            f"{gradient_relative_error:.3e} "
            f"(limit {gradient_tolerance:.3e}). Optimization stopped."
        )
    return q_relative_error, gradient_relative_error


def enforce_jax_gradient_check(
        w, alpha_map, alpha_C, alpha_L_bg,
        gradient_tolerance=1e-7, q_tolerance=1e-10,
        context='initial'):
    q_manual, grad_manual = objective_Q_with_manual_gradient(
        w, alpha_map, alpha_C, alpha_L_bg
    )
    q_jax, grad_jax = objective_Q_with_jax_gradient(
        w, alpha_map, alpha_C, alpha_L_bg
    )
    q_relative_error = abs(q_manual - q_jax) / max(1.0, abs(q_manual), abs(q_jax))
    gradient_relative_error = np.linalg.norm(grad_manual - grad_jax) / max(
        1.0, np.linalg.norm(grad_manual), np.linalg.norm(grad_jax)
    )
    print(
        f"JAX GRADIENT CHECK ({context}): Q_rel={q_relative_error:.3e}, "
        f"grad_rel={gradient_relative_error:.3e}, JIT={USE_JAX_JIT}"
    )
    if (not np.isfinite(q_relative_error)
            or not np.isfinite(gradient_relative_error)
            or q_relative_error > q_tolerance
            or gradient_relative_error > gradient_tolerance):
        raise RuntimeError(
            f"Manual/JAX gradient check failed at {context}: "
            f"Q relative error={q_relative_error:.3e}, "
            f"gradient relative error={gradient_relative_error:.3e}"
        )
    return q_relative_error, gradient_relative_error


# 10,主重建函数 (修改版：支持 w_start 参数)

def mem_2d_reconstruction_corrected(alpha_map, alpha_C,
                                     alpha_L_bg,
                                     smoothness_ratio,
                                     max_iter,  # 内层三组向量
                                     max_default_iter,  # 外层
                                     default_tolerance,
                                     default_damping,
                                     test_threshold,
                                     q_gradient_threshold,
                                     fd_gradient_tolerance=1e-4,
                                     autodiff_gradient_tolerance=1e-7,
                                     autodiff_q_tolerance=1e-10,
                                     autodiff_check_every=10,
                                     w_start=None):  # <--- 新增：允许传入初始 w
    global q_flat, q_C, q_L_bg

    if w_start is None:
        # 原来的初始化逻辑
        p0 = np.full(N_pixels, 1.0 / N_pixels)
        C0 = np.clip(C_initial_grid, POSITIVE_FLOOR, None)
        L0 = L_bg_initial.copy()
        w0 = np.concatenate([p0, C0, L0])
    else:
        # 使用 Adams warm-up 后的结果
        w0 = w_start.copy()
        p0, C0, L0 = unpack_parameters(w0)
        # 确保正性
        p0 = np.clip(p0, POSITIVE_FLOOR, None)
        C0 = np.clip(C0, POSITIVE_FLOOR, None)
        L0 = np.clip(L0, POSITIVE_FLOOR, None)
        w0 = np.concatenate([p0, C0, L0])

    # 无 warm-up 时从初值建立默认图。有 warm-up 时必须保留 Adam
    # 使用的同一组冻结默认图，不能在 Adam 和 L-BFGS 之间暗中换 Q。
    if w_start is None:
        q_flat = geometric_default_2d(
            p0.reshape(N_v, N_tau), smoothness_ratio
        ).reshape(-1)
        q_C = geometric_default_1d(C0)
        q_L_bg = geometric_default_1d(L0)

    # 三个图像为正
    # 优化器内部使用 z=w/scale，解决地图(~1e-4)、C(~1)、L0(~1)的病态尺度；
    # 返回给 scipy 的手写梯度严格按链式法则 dQ/dz=(dQ/dw)*scale。
    def hessian_parameter_scale(w_reference):
        """用 Q 的正对角曲率构造联合 L-BFGS 预条件。

        map 和 L_bg 使用精确的对角曲率；C 使用连续谱观测项加熵项的
        对角曲率。scale=1/sqrt(H_diag) 使各块在新坐标中曲率接近 1。
        """
        p_ref, C_ref, L_ref = unpack_parameters(w_reference)
        _, delta_grid = compute_L_pred(p_ref, C_ref, L_ref)
        inv_var_L = 1.0 / (L_err ** 2)

        map_data_curvature = (
            CHI2_L_SCALE * 2.0 * d_tau ** 2
            * (inv_var_L @ (delta_grid ** 2))
        ).reshape(-1)
        map_curvature = (
            map_data_curvature + alpha_map * entropy_scale(q_flat) / p_ref
        )

        C_data_curvature = CHI2_C_SCALE * 2.0 * (
            (M_obs ** 2).T @ (1.0 / (C_err ** 2))
        )
        C_curvature = (
            C_data_curvature + alpha_C * entropy_scale(q_C) / C_ref
        )

        L_data_curvature = CHI2_L_SCALE * 2.0 * np.sum(inv_var_L, axis=1)
        L_curvature = (
            L_data_curvature + alpha_L_bg * entropy_scale(q_L_bg) / L_ref
        )

        curvature = np.concatenate([map_curvature, C_curvature, L_curvature])
        return 1.0 / np.sqrt(np.maximum(curvature, 1e-30))

    def solve_profiled_L_bg(p_values, C_values, initial_L):
        """在给定 Psi,C 时精确极小化每个速度通道的 L_bg。

        这是 100 个相互独立的一维严格凸问题，使用向量化 Newton。
        在外层联合目标中应用包络定理，因此对 Psi,C 的梯度无需加
        dL_bg/d(Psi,C) 项。
        """
        zero_bg = np.zeros(N_v)
        L_variable, _ = compute_L_pred(p_values, C_values, zero_bg)
        inv_var = 1.0 / (L_err ** 2)
        curvature_data = CHI2_L_SCALE * 2.0 * np.sum(inv_var, axis=1)
        linear_data = CHI2_L_SCALE * 2.0 * np.sum(
            (L_variable - L_obs) * inv_var, axis=1
        )
        L_values = np.clip(initial_L, POSITIVE_FLOOR, None).copy()
        for _ in range(12):
            gradient = (
                curvature_data * L_values + linear_data
                + alpha_L_bg * entropy_scale(q_L_bg)
                * np.log(L_values / q_L_bg)
            )
            hessian = (
                curvature_data
                + alpha_L_bg * entropy_scale(q_L_bg) / L_values
            )
            next_L = np.maximum(L_values - gradient / hessian, POSITIVE_FLOOR)
            if np.max(np.abs(next_L - L_values)) <= 1e-13 * max(1.0, np.max(L_values)):
                L_values = next_L
                break
            L_values = next_L
        return L_values
    history = {
        'TEST_map': [], 'TEST_C': [], 'TEST_L_bg': [],
        'relative_grad_Q_map': [], 'relative_grad_Q_C': [],
        'relative_grad_Q_L_bg': [],
        'relative_grad_Q_C_gap': [],
        'chi2_L': [], 'chi2_C': [], 'optimizer_nit': [],
        'default_change': [], 'optimizer_success': [], 'optimizer_message': [],
    }

    if autodiff_check_every <= 0:
        raise ValueError("autodiff_check_every must be a positive integer")
    
    # 梯度检查 (如果 w_start 不是 None，说明已经 warm-up 过，可以跳过或放松检查)
    if w_start is None:
        gradient_errors = enforce_finite_difference_gradient_check(
            w0, alpha_map, alpha_C, alpha_L_bg,
            tolerance=fd_gradient_tolerance, context='initial point'
        )
        if GRADIENT_BACKEND == 'jax':
            enforce_jax_gradient_check(
                w0, alpha_map, alpha_C, alpha_L_bg,
                gradient_tolerance=autodiff_gradient_tolerance,
                q_tolerance=autodiff_q_tolerance,
                context='initial point'
            )
        print("=== 2D MEMECHO reconstruction (from scratch) ===")
        print("Manual Q gradient relative errors: "
              f"map={gradient_errors['map']:.3e}, "
              f"C={gradient_errors['C']:.3e}, "
              f"L_bg={gradient_errors['L_bg']:.3e}")
    else:
        print("=== 2D MEMECHO reconstruction (continued from Adams warm-up) ===")
        # 放松检查，只做所选自动微分后端检查
        if GRADIENT_BACKEND == 'jax':
            enforce_jax_gradient_check(
                w0, alpha_map, alpha_C, alpha_L_bg,
                gradient_tolerance=autodiff_gradient_tolerance * 10,
                q_tolerance=autodiff_q_tolerance * 10,
                context='after Adams warm-up'
            )
    
    print(f"Fixed C_bar = {C_bar_fixed:.4f} (not optimized)")
    print(f"Variables: {N_pixels} map + {N_t_C} C + {N_v} L_bg = {N_total}")
    print(f"2D default-map smoothness ratio A = {smoothness_ratio:.3f}")
    print(
        f"Gradient backend = {GRADIENT_BACKEND}; JAX JIT = {USE_JAX_JIT}; "
        f"persistent cache = {bool(JAX_CACHE_DIR) if USE_JAX_JIT else False}"
    )
    print("-" * 100)

    default_converged = False
    for default_iteration in range(max_default_iter):
        print(f"\n=== Outer iteration {default_iteration + 1}/{max_default_iter} ===")
        w_opt = w0.copy()
        total_block_nit = 0
        inner_converged = False

        # 联合 L-BFGS-B：一次同时更新 Psi、C(t) 和 L_bg(v)。
        # 每个 outer iteration 用当前点的对角 Hessian 重新预条件。
        parameter_scale = hessian_parameter_scale(w_opt)
        joint_stop = C_SLICE.stop  # L_bg 在每次目标计算中被精确 profile 掉。
        joint_scale = parameter_scale[:joint_stop]
        bounds_scaled = [
            (POSITIVE_FLOOR / scale, None) for scale in joint_scale
        ]

        def joint_objective(z):
            map_and_C = z * joint_scale
            p_trial = map_and_C[MAP_SLICE]
            C_trial = map_and_C[C_SLICE]
            L_trial = solve_profiled_L_bg(
                p_trial, C_trial, w_opt[LBG_SLICE]
            )
            trial_w = np.concatenate([map_and_C, L_trial])
            Q, grad_w = objective_Q_selected(
                trial_w, alpha_map, alpha_C, alpha_L_bg
            )
            return Q, grad_w[:joint_stop] * joint_scale

        joint_result = minimize(
            fun=joint_objective,
            x0=w_opt[:joint_stop] / joint_scale,
            jac=True,
            method='L-BFGS-B',
            bounds=bounds_scaled,
            options={
                'maxiter': max_iter,
                'maxcor': 20,
                'maxls': 30,
                'ftol': 1e-15,
                'gtol': 1e-10,
            },
        )
        map_and_C_opt = joint_result.x * joint_scale
        L_bg_opt = solve_profiled_L_bg(
            map_and_C_opt[MAP_SLICE], map_and_C_opt[C_SLICE],
            w_opt[LBG_SLICE],
        )
        w_opt = np.concatenate([map_and_C_opt, L_bg_opt])
        total_block_nit = joint_result.nit

        print(
            f"Joint L-BFGS status={joint_result.status}, success={joint_result.success}, "
            f"nit={joint_result.nit}, nfev={joint_result.nfev}: {joint_result.message}"
        )

        tests_now = compute_all_tests(w_opt)
        q_gradients_now = compute_relative_Q_gradients(
            w_opt, alpha_map, alpha_C, alpha_L_bg
        )
        history['TEST_map'].append(tests_now['TEST_map'])
        history['TEST_C'].append(tests_now['TEST_C'])
        history['TEST_L_bg'].append(tests_now['TEST_L_bg'])
        history['relative_grad_Q_map'].append(q_gradients_now['map'])
        history['relative_grad_Q_C'].append(q_gradients_now['C'])
        history['relative_grad_Q_L_bg'].append(q_gradients_now['L_bg'])
        history['relative_grad_Q_C_gap'].append(
            q_gradients_now.get('C_gap', 0.0)
        )
        # SciPy 的 success 可能只表示 Q 的相对变化很小，不等于 MEM
        # 的 TEST/Q-gradient 条件已满足，所以严格按物理诊断判定。
        inner_converged = bool(
            all(value <= test_threshold for value in tests_now.values())
            and all(value <= q_gradient_threshold
                    for value in q_gradients_now.values())
        )

        tests = compute_all_tests(w_opt)
        q_gradients = compute_relative_Q_gradients(
            w_opt, alpha_map, alpha_C, alpha_L_bg
        )
        if not inner_converged and os.getenv('MEM_RESEARCH_ALLOW_INCOMPLETE', '0') != '1':
            raise RuntimeError(
                f"Fixed-default solve failed at outer iteration "
                f"{default_iteration + 1}: TEST={tests}, relative Q gradients="
                f"{q_gradients}"
            )

        p_opt, C_opt, L_bg_opt = unpack_parameters(w_opt)
        q_map_target = geometric_default_2d(
            p_opt.reshape(N_v, N_tau), smoothness_ratio
        ).reshape(-1)
        q_C_target = geometric_default_1d(C_opt)
        q_L_target = geometric_default_1d(L_bg_opt)

        default_changes = [
            np.sqrt(np.mean(np.log(np.clip(target, POSITIVE_FLOOR, None)
                                   / np.clip(current, POSITIVE_FLOOR, None)) ** 2))
            for current, target in (
                (q_flat, q_map_target),
                (q_C, q_C_target),
                (q_L_bg, q_L_target),
            )
        ]
        default_change = float(max(default_changes))
        history['default_change'].append(default_change)
        chi2_C, chi2_L, _, _, _ = compute_chi2_and_gradients(w_opt)
        history['chi2_L'].append(chi2_L / L_obs.size)
        history['chi2_C'].append(chi2_C / C_obs.size)
        history['optimizer_nit'].append(total_block_nit)
        history['optimizer_success'].append(bool(joint_result.success))
        history['optimizer_message'].append(str(joint_result.message))

        print(
            f"Default iter {default_iteration + 1:02d}, "
            f"joint L-BFGS nit={total_block_nit}: "
            f"TEST=[{tests['TEST_map']:.3e}, {tests['TEST_C']:.3e}, "
            f"{tests['TEST_L_bg']:.3e}], C_gap_Qgrad="
            f"{q_gradients.get('C_gap', 0.0):.3e}, "
            f"default_change={default_change:.3e}"
        )

        if inner_converged and default_change <= default_tolerance:
            default_converged = True
            break

        # 最后一轮后不再改变 q，确保返回参数、TEST 和后续梯度比较对应同一个 Q。
        if default_iteration == max_default_iter - 1:
            break

        # 以对数空间阻尼更新 floating/curvature defaults；下一次内层求解时冻结。
        def damp_default(current, target):
            return np.exp(
                (1.0 - default_damping) * np.log(np.clip(current, POSITIVE_FLOOR, None))
                + default_damping * np.log(np.clip(target, POSITIVE_FLOOR, None))
            )

        q_flat = damp_default(q_flat, q_map_target)
        q_C = damp_default(q_C, q_C_target)
        q_L_bg = damp_default(q_L_bg, q_L_target)
        w0 = w_opt

    history['research_default_converged'] = bool(default_converged)
    history['research_inner_converged'] = bool(inner_converged)
    if os.getenv('MEM_RESEARCH_ALLOW_INCOMPLETE', '0') == '1':
        p_final, C_final, L_bg_final = unpack_parameters(w_opt)
        L_pred, _ = compute_L_pred(p_final, C_final, L_bg_final)
        return p_final.reshape(N_v, N_tau), C_final, L_bg_final, L_pred, history
    if not default_converged:
        print(f"Floating defaults reached max_default_iter={max_default_iter}; "
              "final three-component TEST is still converged.")
    if not default_converged:
        raise RuntimeError('Floating default did not converge within the outer iteration budget; increase max_default_iter.')
    print(f"All three TEST values converged <= {test_threshold:.1e}; optimization stopped.")

    p_final, C_final, L_bg_final = unpack_parameters(w_opt)
    L_pred, _ = compute_L_pred(p_final, C_final, L_bg_final)
    reconstructed_map_2d = p_final.reshape(N_v, N_tau)
    return reconstructed_map_2d, C_final, L_bg_final, L_pred, history


# ============================================================
# 10.5 Adam 算法 warm-up（对数参数化）
# ============================================================

def adam_warmup(w0, alpha_map, alpha_C, alpha_L_bg,
                n_steps=150, step_size=0.03, beta1=0.9, beta2=0.999,
                eps=1e-8, report_every=25):
    """
    在对数参数 theta=log(w/scale) 上做 Adam warm-up。

    这使每次更新成为相对更新，同时适合 ~1e-4 的图像像素与 ~1 的
    C/L_bg，并天然保证正值。返回优化后的 w 和 history。
    """
    scale = np.concatenate([
        np.full(N_pixels, 1.0 / N_pixels),
        np.full(N_t_C, np.median(C_err)),
        np.full(N_v, np.median(np.clip(w0[LBG_SLICE], POSITIVE_FLOOR, None))),
    ])
    theta = np.log(np.clip(w0, POSITIVE_FLOOR, None) / scale)
    theta_min = np.log(POSITIVE_FLOOR / scale) + 2.0
    theta_max = np.log(1.0e6 / scale)
    m = np.zeros_like(theta)
    v = np.zeros_like(theta)
    best_Q = np.inf
    best_w = w0.copy()
    stale_steps = 0
    
    history_adams = {
        'Q': [],
        'TEST_map': [],
        'TEST_C': [],
        'TEST_L_bg': [],
        'chi2_L': [],
        'chi2_C': [],
    }
    
    print("\n" + "="*60)
    print(f"ADAM LOG-SPACE WARM-UP ({n_steps} steps maximum)")
    print("="*60)
    print(f"Step size: {step_size}, beta1={beta1}, beta2={beta2}")
    print("-" * 60)
    
    for step in range(n_steps):
        w = scale * np.exp(theta)
        Q, grad = objective_Q_selected(w, alpha_map, alpha_C, alpha_L_bg)

        # 链式法则：dQ/dtheta = dQ/dw * w。
        grad_theta = grad * w
        m = beta1 * m + (1 - beta1) * grad_theta
        v = beta2 * v + (1 - beta2) * (grad_theta ** 2)
        m_hat = m / (1 - beta1 ** (step + 1))
        v_hat = v / (1 - beta2 ** (step + 1))
        theta_new = np.clip(
            theta - step_size * m_hat / (np.sqrt(v_hat) + eps),
            theta_min, theta_max,
        )
        max_change = float(np.max(np.abs(theta_new - theta)))
        theta = theta_new

        if Q < best_Q * (1.0 - 1e-9):
            best_Q = float(Q)
            best_w = w.copy()
            stale_steps = 0
        else:
            stale_steps += 1

        if (step + 1) % report_every == 0 or step == 0:
            w_report = scale * np.exp(theta)
            Q_report, _ = objective_Q_selected(
                w_report, alpha_map, alpha_C, alpha_L_bg
            )
            tests = compute_all_tests(w_report)
            chi2_C, chi2_L, _, _, _ = compute_chi2_and_gradients(w_report)
            history_adams['Q'].append(Q_report)
            history_adams['TEST_map'].append(tests['TEST_map'])
            history_adams['TEST_C'].append(tests['TEST_C'])
            history_adams['TEST_L_bg'].append(tests['TEST_L_bg'])
            history_adams['chi2_L'].append(chi2_L / L_obs.size)
            history_adams['chi2_C'].append(chi2_C / C_obs.size)
            
            print(f"Adam step {step+1:4d}: Q={Q_report:.6e}, "
                  f"TEST_map={tests['TEST_map']:.3e}, "
                  f"TEST_C={tests['TEST_C']:.3e}, "
                  f"reduced_chi2_L={chi2_L / L_obs.size:.4f}")

        if max_change < 1e-8 or stale_steps >= 30:
            print(f"Adam stopped early at step {step + 1}")
            break
    
    # 最后再算一次
    w = scale * np.exp(theta)
    Q_final, _ = objective_Q_selected(
        w, alpha_map, alpha_C, alpha_L_bg
    )
    if best_Q < Q_final:
        w = best_w
    tests = compute_all_tests(w)
    chi2_C, chi2_L, _, _, _ = compute_chi2_and_gradients(w)
    print("-" * 60)
    print(f"Adam warm-up done: {step+1} steps")
    print(f"Final TEST: map={tests['TEST_map']:.3e}, "
          f"C={tests['TEST_C']:.3e}, L_bg={tests['TEST_L_bg']:.3e}")
    print(f"reduced_chi2_L={chi2_L / L_obs.size:.4f}")
    print("="*60)
    
    return w, history_adams


# 11,执行重建
# 默认值按 Horne 的 reduced chi2≈1 原则在当前模拟噪声下标定；

# 数据项分别约化、熵除以 default 总量后的新尺度。当前 data 实测：
# 本试用版采用2026秋季示例数据的局部标定：alpha_map=0.2，
# alpha_C=1200、alpha_Lbg=0.02；换输入数据后仍需检查拟合与收敛。
ALPHA_MAP = float(os.getenv('MEM_ALPHA_MAP', '0.2'))
ALPHA_C = float(os.getenv('MEM_ALPHA_C', '1200.0'))
ALPHA_L_BG = float(os.getenv('MEM_ALPHA_LBG', '0.02'))
SMOOTHNESS_RATIO = float(os.getenv('MEM_SMOOTHNESS_RATIO', '1'))
MAX_DEFAULT_ITER = int(os.getenv('MEM_MAX_DEFAULT_ITER', '1000'))
# 保留旧环境变量名以兼容原运行方式；现在表示每次外层的联合 L-BFGS 步数。
MAX_INNER_ITER = int(os.getenv('MEM_MAX_INNER_ITER', '800'))
DEFAULT_TOLERANCE = float(os.getenv('MEM_DEFAULT_TOLERANCE', '1e-2'))
DEFAULT_DAMPING = float(os.getenv('MEM_DEFAULT_DAMPING', '0.5'))
TEST_THRESHOLD = float(os.getenv('MEM_TEST_THRESHOLD', '1e-5'))
Q_GRADIENT_THRESHOLD = float(os.getenv('MEM_Q_GRADIENT_THRESHOLD', '3e-3'))
FD_GRADIENT_TOLERANCE = float(os.getenv('MEM_FD_GRADIENT_TOLERANCE', '1e-4'))
AUTODIFF_GRADIENT_TOLERANCE = float(
    os.getenv('MEM_AUTODIFF_GRADIENT_TOLERANCE', '1e-7')
)
AUTODIFF_Q_TOLERANCE = float(os.getenv('MEM_AUTODIFF_Q_TOLERANCE', '1e-10'))
AUTODIFF_CHECK_EVERY = int(os.getenv('MEM_AUTODIFF_CHECK_EVERY', '30'))

# ---- Adam warm-up 参数（保留 ADAMS 环境变量名以兼容 022） ----
ADAMS_STEPS = int(os.getenv('MEM_ADAMS_STEPS', '40'))
ADAMS_STEP_SIZE = float(os.getenv('MEM_ADAMS_STEP_SIZE', '0.03'))
DO_ADAMS_WARMUP = os.getenv('MEM_DO_ADAMS_WARMUP', '1') == '1'

# 构造初始 w
p0 = np.full(N_pixels, 1.0 / N_pixels)
C0 = np.clip(C_initial_grid, POSITIVE_FLOOR, None)
L0 = L_bg_initial.copy()
w0_init = np.concatenate([p0, C0, L0])

# Adam 与第一次联合 L-BFGS 必须使用完全相同的冻结 default（即同一个 Q）。
q_flat = geometric_default_2d(
    p0.reshape(N_v, N_tau), SMOOTHNESS_RATIO
).reshape(-1)
q_C = geometric_default_1d(C0)
q_L_bg = geometric_default_1d(L0)

# ---- 执行 Adams warm-up (如果启用) ----
if DO_ADAMS_WARMUP:
    w_adams, history_adams = adam_warmup(
        w0_init, 
        alpha_map=ALPHA_MAP,
        alpha_C=ALPHA_C,
        alpha_L_bg=ALPHA_L_BG,
        n_steps=ADAMS_STEPS,
        step_size=ADAMS_STEP_SIZE,
    )
    w_start_for_lbfgs = w_adams
else:
    w_start_for_lbfgs = None
    print("\nAdams warm-up skipped (MEM_DO_ADAMS_WARMUP=0)")

# ---- L-BFGS-B 精细优化 ----
reconstructed_map_2d, C_recon, L_bg_recon, L_pred, history = mem_2d_reconstruction_corrected(
    alpha_map=ALPHA_MAP,
    alpha_C=ALPHA_C,
    alpha_L_bg=ALPHA_L_BG,
    smoothness_ratio=SMOOTHNESS_RATIO,
    max_iter=MAX_INNER_ITER,
    max_default_iter=MAX_DEFAULT_ITER,
    default_tolerance=DEFAULT_TOLERANCE,
    default_damping=DEFAULT_DAMPING,
    test_threshold=TEST_THRESHOLD,
    q_gradient_threshold=Q_GRADIENT_THRESHOLD,
    fd_gradient_tolerance=FD_GRADIENT_TOLERANCE,
    autodiff_gradient_tolerance=AUTODIFF_GRADIENT_TOLERANCE,
    autodiff_q_tolerance=AUTODIFF_Q_TOLERANCE,
    autodiff_check_every=AUTODIFF_CHECK_EVERY,
    w_start=w_start_for_lbfgs,  # <--- 传入 Adams 结果
)


def predict_line_on_times(p_2d, C_values, L_bg, evaluation_times):
    required = (evaluation_times[:, None] - delays[None, :]).reshape(-1)
    if required.min() < t_C.min() or required.max() > t_C.max():
        raise ValueError("continuous L prediction requests times outside reconstructed C grid")
    interpolation = build_interpolation_matrix(required, t_C)
    delta_grid = (interpolation @ (C_values - C_bar_fixed)).reshape(
        len(evaluation_times), N_tau
    )
    return p_2d @ delta_grid.T * d_tau + L_bg[:, None]


# 用完整时间网格计算 gap 内的连续模型预测；这些点不参与 chi2。
L_pred_continuous = predict_line_on_times(
    reconstructed_map_2d, C_recon, L_bg_recon, t_L_model
)

# 11b. 手写梯度 vs 自动微分：同一起点、同一轮三块优化

autodiff_comparison = None
autodiff_cycle_map = None
if os.getenv('MEM_AUTODIFF_COMPARE', '1') == '1':
    if not AUTOGRAD_AVAILABLE:
        print("Autodiff comparison skipped: install optional package 'autograd'.")
    else:
        w_reference = np.concatenate([
            reconstructed_map_2d.reshape(-1), C_recon, L_bg_recon
        ])
        Q_manual, grad_manual = objective_Q_with_manual_gradient(
            w_reference, ALPHA_MAP, ALPHA_C, ALPHA_L_BG
        )
        Q_auto, grad_auto = objective_Q_with_autodiff_gradient(
            w_reference, ALPHA_MAP, ALPHA_C, ALPHA_L_BG
        )
        gradient_relative_error = np.linalg.norm(grad_manual - grad_auto) / max(
            1.0, np.linalg.norm(grad_manual), np.linalg.norm(grad_auto)
        )

        manual_cycle = run_one_block_cycle(
            w_reference, objective_Q_with_manual_gradient,
            ALPHA_MAP, ALPHA_C, ALPHA_L_BG
        )
        autodiff_cycle = run_one_block_cycle(
            w_reference, objective_Q_with_autodiff_gradient,
            ALPHA_MAP, ALPHA_C, ALPHA_L_BG
        )
        manual_map_cycle = manual_cycle[MAP_SLICE].reshape(N_v, N_tau)
        autodiff_cycle_map = autodiff_cycle[MAP_SLICE].reshape(N_v, N_tau)
        map_cycle_correlation = np.corrcoef(
            manual_map_cycle.reshape(-1), autodiff_cycle_map.reshape(-1)
        )[0, 1]
        autodiff_comparison = {
            'Q_abs_difference': abs(Q_manual - Q_auto),
            'gradient_relative_error': gradient_relative_error,
            'map_cycle_correlation': map_cycle_correlation,
            'map_cycle_max_abs_difference': np.max(
                np.abs(manual_map_cycle - autodiff_cycle_map)
            ),
            'C_cycle_max_abs_difference': np.max(np.abs(
                manual_cycle[C_SLICE] - autodiff_cycle[C_SLICE]
            )),
            'L_bg_cycle_max_abs_difference': np.max(np.abs(
                manual_cycle[LBG_SLICE] - autodiff_cycle[LBG_SLICE]
            )),
        }
        print("AUTODIFF CROSS-CHECK")
        for key, value in autodiff_comparison.items():
            print(f"{key} = {value:.6e}")


reconstructed_map_2d_physical = (
    reconstructed_map_2d * L_NORMALIZATION / C_NORMALIZATION
)
C_recon_physical = C_recon * C_NORMALIZATION
C_initial_grid_physical = C_initial_grid * C_NORMALIZATION
C_GP_STD_physical = C_GP_STD * C_NORMALIZATION
L_bg_initial_physical = L_bg_initial * L_NORMALIZATION
L_bg_recon_physical = L_bg_recon * L_NORMALIZATION
L_pred_physical = L_pred * L_NORMALIZATION
L_pred_continuous_physical = L_pred_continuous * L_NORMALIZATION


# 12. 画图

# ---- 1. 二维地图 ----
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

im1 = axes[0].pcolormesh(velocities, delays, reconstructed_map_2d_physical.T, shading='auto', cmap='hot')
axes[0].set_title('MEM Reconstructed Map')
axes[0].set_xlabel('Velocity (km/s)')
axes[0].set_ylabel('Delay (days)')
plt.colorbar(im1, ax=axes[0])

map_1d_recon = np.sum(reconstructed_map_2d_physical, axis=0)
axes[1].plot(delays, map_1d_recon / np.max(map_1d_recon+1e-10), 'r-o', 
             linewidth=2, markersize=3)
axes[1].set_xlabel('Delay (days)')
axes[1].set_ylabel('Normalized Integrated Response')
axes[1].set_title('Delay Projection')
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
output_dir = os.path.abspath(os.getenv(
    'MEM_OUTPUT_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
))
os.makedirs(output_dir, exist_ok=True)
np.savetxt(
    os.path.join(output_dir, "C_reconstructed_continuous.csv"),
    np.column_stack([t_C, C_recon_physical]), delimiter=",",
    header="time_days,C_reconstructed", comments="", fmt="%.10e"
)
np.savetxt(
    os.path.join(output_dir, "L_predicted_continuous.csv"),
    np.column_stack([t_L_model, L_pred_continuous_physical.T]), delimiter=",",
    header=",".join(["time_days"] + [f"L_pred_{v:.10g}_kms" for v in velocities]),
    comments="", fmt="%.10e"
)
np.savetxt(
    os.path.join(output_dir, "L_total_predicted.csv"),
    np.column_stack([t_L_model, np.sum(L_pred_continuous_physical, axis=0)]),
    delimiter=",", header="time_days,L_total_predicted", comments="", fmt="%.10e"
)
np.savetxt(
    os.path.join(output_dir, "Psi_velocity_delay_map.csv"),
    np.column_stack([velocities, reconstructed_map_2d_physical]),
    delimiter=",",
    header=",".join(["velocity_km_s"] + [f"delay_{tau:.10g}_days" for tau in delays]),
    comments="", fmt="%.10e"
)
map_figure_path = os.path.join(output_dir, 'MEM_velocity_delay_map.png')
fig.savefig(map_figure_path, dpi=300, bbox_inches='tight')
print(f"High-resolution map saved to: {map_figure_path}")
plt.show()

if autodiff_cycle_map is not None:
    fig_ad, axes_ad = plt.subplots(1, 3, figsize=(18, 5))
    auto_vmax = max(np.max(manual_map_cycle), np.max(autodiff_cycle_map))
    axes_ad[0].pcolormesh(
        velocities, delays, manual_map_cycle.T, shading='auto',
        cmap='hot', vmin=0.0, vmax=auto_vmax
    )
    axes_ad[0].set_title('One Block Cycle: Manual Gradient')
    axes_ad[1].pcolormesh(
        velocities, delays, autodiff_cycle_map.T, shading='auto',
        cmap='hot', vmin=0.0, vmax=auto_vmax
    )
    axes_ad[1].set_title('One Block Cycle: Autodiff Gradient')
    difference = manual_map_cycle - autodiff_cycle_map
    diff_limit = max(np.max(np.abs(difference)), 1e-16)
    axes_ad[2].pcolormesh(
        velocities, delays, difference.T, shading='auto', cmap='coolwarm',
        vmin=-diff_limit, vmax=diff_limit
    )
    axes_ad[2].set_title('Manual - Autodiff')
    for axis in axes_ad:
        axis.set_xlabel('Velocity (km/s)')
        axis.set_ylabel('Delay (days)')
    fig_ad.tight_layout()
    autodiff_figure_path = os.path.join(
        output_dir, 'MEM_manual_vs_autodiff.png'
    )
    fig_ad.savefig(autodiff_figure_path, dpi=300, bbox_inches='tight')
    print(f"Gradient-comparison map saved to: {autodiff_figure_path}")
    plt.show()

# ---- 2. C(t) 连续谱 ----
def shade_gap_regions(axis, grid, gap_mask, show_label=True):
    padded = np.r_[False, gap_mask, False].astype(int)
    starts = np.where(np.diff(padded) == 1)[0]
    stops = np.where(np.diff(padded) == -1)[0] - 1
    for number, (start, stop) in enumerate(zip(starts, stops)):
        axis.axvspan(
            grid[start], grid[stop], color='0.88', alpha=0.8,
            label=('season gap (model only)' if show_label and number == 0 else '_nolegend_')
        )


plt.figure(figsize=(14, 5))
axis_C = plt.gca()
shade_gap_regions(axis_C, t_C, C_GAP_MASK, show_label=False)
plt.fill_between(
    t_C, C_initial_grid_physical - 2.0 * C_GP_STD_physical,
    C_initial_grid_physical + 2.0 * C_GP_STD_physical,
    where=C_GAP_MASK, color='tab:green', alpha=0.18,
    label='_nolegend_'
)
plt.plot(t_C_obs, C_obs_physical, color='darkblue', marker='x', linestyle='none',
         alpha=1, markersize=4, label='Observed C(t)')
# C_recon 是在完整时间网格上联合优化得到的一条连续 MEM 曲线。
# GP 只通过上面的浅绿色 2-sigma 带表达 gap 不确定度，不再与 MEM 分段拼接。
plt.plot(t_C, C_recon_physical, 'r-', linewidth=1.5,
         label='MEM reconstructed C(t)')
plt.axhline(y=C_bar_fixed * C_NORMALIZATION, color='k', linestyle='--', alpha=0.5,
            label='_nolegend_')
plt.xlabel('Time (days)')
plt.ylabel('Continuum Flux')
plt.title('Continuum Light Curve')
plt.grid(True, alpha=0.3)
plt.legend()
continuum_figure_path = os.path.join(output_dir, 'MEM_continuum_gap_reconstruction.png')
plt.savefig(continuum_figure_path, dpi=220, bbox_inches='tight')
plt.show()

# ---- 3. 发射线光变 ----
plt.figure(figsize=(14, 4))
axis_L = plt.gca()
shade_gap_regions(axis_L, t_L_model, L_GAP_MASK)
plt.errorbar(t_L, np.sum(L_obs_physical, axis=0), fmt='x', linestyle='none',
             yerr=np.sqrt(np.sum(L_err_physical ** 2, axis=0)), color='darkblue',
             markersize=4, alpha=1, label='Observed L(t)')
plt.plot(t_L_model, np.sum(L_pred_continuous_physical, axis=0), 'r-', linewidth=2,
         label='MEM continuous predicted L(t)')
plt.xlabel('Time (days)')
plt.ylabel('Integrated Line Flux')
plt.title('Emission Line Light Curve Fit')
plt.grid(True, alpha=0.3)
plt.legend()
line_figure_path = os.path.join(output_dir, 'MEM_line_gap_prediction.png')
plt.savefig(line_figure_path, dpi=220, bbox_inches='tight')
plt.show()

fig_L_diag, axes_L_diag = plt.subplots(1, 2, figsize=(16, 5), constrained_layout=True)
im_L_fit = axes_L_diag[0].pcolormesh(
    t_L, velocities, L_pred_physical, shading='auto', cmap='viridis'
)
axes_L_diag[0].set_title('Optimized L(v,t)')
axes_L_diag[0].set_xlabel('Time (days)')
axes_L_diag[0].set_ylabel('Velocity (km/s)')
fig_L_diag.colorbar(im_L_fit, ax=axes_L_diag[0], label='Line flux')
L_normalized_residual = (L_pred - L_obs) / L_err
residual_limit = max(float(np.percentile(np.abs(L_normalized_residual), 99)), 1.0)
im_L_res = axes_L_diag[1].pcolormesh(
    t_L, velocities, L_normalized_residual, shading='auto', cmap='coolwarm',
    vmin=-residual_limit, vmax=residual_limit
)
axes_L_diag[1].set_title('L normalized residual: (model-data)/error')
axes_L_diag[1].set_xlabel('Time (days)')
axes_L_diag[1].set_ylabel('Velocity (km/s)')
fig_L_diag.colorbar(im_L_res, ax=axes_L_diag[1], label='Residual / sigma')
fig_L_diag.savefig(
    os.path.join(output_dir, 'L_fit_and_residual_heatmaps.png'),
    dpi=220, bbox_inches='tight'
)
plt.show()

psi_default = np.clip(q_flat.reshape(N_v, N_tau), POSITIVE_FLOOR, None)
psi_value = np.clip(reconstructed_map_2d, POSITIVE_FLOOR, None)
psi_entropy_penalty = psi_value * np.log(psi_value / psi_default) - psi_value + psi_default
fig_psi_diag, axes_psi_diag = plt.subplots(1, 2, figsize=(16, 5), constrained_layout=True)
im_psi = axes_psi_diag[0].pcolormesh(
    velocities, delays, reconstructed_map_2d_physical.T,
    shading='auto', cmap='hot'
)
axes_psi_diag[0].set_title('Optimized Psi(v,tau)')
axes_psi_diag[0].set_xlabel('Velocity (km/s)')
axes_psi_diag[0].set_ylabel('Delay (days)')
fig_psi_diag.colorbar(im_psi, ax=axes_psi_diag[0], label='Response')
im_entropy = axes_psi_diag[1].pcolormesh(
    velocities, delays, psi_entropy_penalty.T,
    shading='auto', cmap='magma'
)
axes_psi_diag[1].set_title('Psi local entropy penalty')
axes_psi_diag[1].set_xlabel('Velocity (km/s)')
axes_psi_diag[1].set_ylabel('Delay (days)')
fig_psi_diag.colorbar(im_entropy, ax=axes_psi_diag[1], label='p log(p/q) - p + q')
fig_psi_diag.savefig(
    os.path.join(output_dir, 'Psi_and_entropy_heatmaps.png'),
    dpi=220, bbox_inches='tight'
)
plt.show()

# ---- 速度-时延拟合及其局部 chi2/熵诊断合图 ----
# chi2_L 原本定义在 (velocity, observation time) 数据空间，不能唯一地
# 归属于某一个 delay 像素。这里按每个 delay 对模型线通量的绝对贡献
# 分配每个 (v,t) 的 chi2；分配后的像素总和仍等于 chi2_L。此图只用于
# 诊断哪些 Psi 像素承受数据拟合压力，不参与优化或收敛判据。
_, diagnostic_delta_grid = compute_L_pred(
    reconstructed_map_2d, C_recon, L_bg_recon
)
line_component_abs = np.abs(
    reconstructed_map_2d[:, None, :]
    * diagnostic_delta_grid[None, :, :]
    * d_tau
)
component_sum = np.sum(line_component_abs, axis=2, keepdims=True)
component_weights = np.divide(
    line_component_abs, component_sum,
    out=np.full_like(line_component_abs, 1.0 / N_tau),
    where=component_sum > 1e-30,
)
local_chi2_map = np.sum(
    (((L_pred - L_obs) / L_err) ** 2)[:, :, None] * component_weights,
    axis=1,
)

def normalize_diagnostic_map(values):
    values = np.asarray(values, dtype=float)
    maximum = float(np.max(values)) if values.size else 0.0
    return values / maximum if maximum > 0.0 else np.zeros_like(values)

relative_chi2_map = normalize_diagnostic_map(local_chi2_map)
relative_entropy_map = normalize_diagnostic_map(psi_entropy_penalty)

fig_psi_summary = plt.figure(figsize=(15, 11), constrained_layout=True)
summary_grid = fig_psi_summary.add_gridspec(2, 2, height_ratios=(1.15, 1.0))
axis_psi_fit = fig_psi_summary.add_subplot(summary_grid[0, :])
axis_chi2 = fig_psi_summary.add_subplot(summary_grid[1, 0])
axis_entropy = fig_psi_summary.add_subplot(summary_grid[1, 1])

image_psi_fit = axis_psi_fit.pcolormesh(
    velocities, delays, reconstructed_map_2d_physical.T,
    shading='auto', cmap='hot'
)
axis_psi_fit.set_title('Optimized velocity-delay map: Psi(v, tau)')
axis_psi_fit.set_xlabel('Velocity (km/s)')
axis_psi_fit.set_ylabel('Delay (days)')
fig_psi_summary.colorbar(image_psi_fit, ax=axis_psi_fit, label='Response')

# 两张诊断图都是无量纲相对贡献，严格共享 cmap、vmin、vmax 和色条。
diagnostic_cmap = 'magma'
image_chi2 = axis_chi2.pcolormesh(
    velocities, delays, relative_chi2_map.T,
    shading='auto', cmap=diagnostic_cmap, vmin=0.0, vmax=1.0
)
axis_chi2.set_title('Relative local chi-square contribution')
axis_chi2.set_xlabel('Velocity (km/s)')
axis_chi2.set_ylabel('Delay (days)')
axis_entropy.pcolormesh(
    velocities, delays, relative_entropy_map.T,
    shading='auto', cmap=diagnostic_cmap, vmin=0.0, vmax=1.0
)
axis_entropy.set_title('Relative local entropy penalty')
axis_entropy.set_xlabel('Velocity (km/s)')
axis_entropy.set_ylabel('Delay (days)')
fig_psi_summary.colorbar(
    image_chi2, ax=[axis_chi2, axis_entropy],
    label='Relative local contribution (0-1)'
)
psi_summary_path = os.path.join(
    output_dir, 'Psi_fit_chi2_entropy_summary.png'
)
fig_psi_summary.savefig(psi_summary_path, dpi=300, bbox_inches='tight')
print(f"Psi fit/chi-square/entropy summary saved to: {psi_summary_path}")
plt.show()

# 另存一张原始数值版本。chi2 与熵不分别归一化，而是直接共用两张图
# 的全局原始范围，便于调整 alpha 后比较二者的绝对量级。
raw_diagnostic_vmin = 0.0
raw_diagnostic_vmax = max(
    float(np.max(local_chi2_map)),
    float(np.max(psi_entropy_penalty)),
    np.finfo(float).tiny,
)
fig_psi_raw = plt.figure(figsize=(15, 11), constrained_layout=True)
raw_grid = fig_psi_raw.add_gridspec(2, 2, height_ratios=(1.15, 1.0))
axis_psi_raw = fig_psi_raw.add_subplot(raw_grid[0, :])
axis_chi2_raw = fig_psi_raw.add_subplot(raw_grid[1, 0])
axis_entropy_raw = fig_psi_raw.add_subplot(raw_grid[1, 1])

image_psi_raw = axis_psi_raw.pcolormesh(
    velocities, delays, reconstructed_map_2d_physical.T,
    shading='auto', cmap='hot'
)
axis_psi_raw.set_title('Optimized velocity-delay map: Psi(v, tau)')
axis_psi_raw.set_xlabel('Velocity (km/s)')
axis_psi_raw.set_ylabel('Delay (days)')
fig_psi_raw.colorbar(image_psi_raw, ax=axis_psi_raw, label='Response')

image_chi2_raw = axis_chi2_raw.pcolormesh(
    velocities, delays, local_chi2_map.T,
    shading='auto', cmap=diagnostic_cmap,
    vmin=raw_diagnostic_vmin, vmax=raw_diagnostic_vmax
)
axis_chi2_raw.set_title('Raw local chi-square contribution')
axis_chi2_raw.set_xlabel('Velocity (km/s)')
axis_chi2_raw.set_ylabel('Delay (days)')
axis_entropy_raw.pcolormesh(
    velocities, delays, psi_entropy_penalty.T,
    shading='auto', cmap=diagnostic_cmap,
    vmin=raw_diagnostic_vmin, vmax=raw_diagnostic_vmax
)
axis_entropy_raw.set_title('Raw local entropy penalty')
axis_entropy_raw.set_xlabel('Velocity (km/s)')
axis_entropy_raw.set_ylabel('Delay (days)')
fig_psi_raw.colorbar(
    image_chi2_raw, ax=[axis_chi2_raw, axis_entropy_raw],
    label='Raw local contribution (shared scale)'
)
psi_raw_summary_path = os.path.join(
    output_dir, 'Psi_fit_chi2_entropy_raw_shared_scale.png'
)
fig_psi_raw.savefig(psi_raw_summary_path, dpi=300, bbox_inches='tight')
print(
    f"Raw shared-scale Psi/chi-square/entropy summary saved to: "
    f"{psi_raw_summary_path}; vmin={raw_diagnostic_vmin:.6g}, "
    f"vmax={raw_diagnostic_vmax:.6g}"
)
plt.show()

# ---- 4. L0(v) 背景 ----
plt.figure(figsize=(10, 4))
plt.plot(velocities, L_bg_initial_physical, 'b--', linewidth=2, label='Initial L_bg(v) (10th percentile)')
plt.plot(velocities, L_bg_recon_physical, 'r-', linewidth=1.5, label='Optimized L_bg(v)')
plt.xlabel('Velocity (km/s)')
plt.ylabel('Line Background')
plt.title('Velocity-dependent Line Background')
plt.grid(True, alpha=0.3)
plt.legend()
plt.show()


# ---- 5. 统计 ----
chi2_L = np.sum(((L_pred - L_obs) / L_err)**2)
chi2_C = np.sum((((M_obs @ C_recon) - C_obs) / C_err)**2)
final_tests = {
    'map': history['TEST_map'][-1],
    'C': history['TEST_C'][-1],
    'L_bg': history['TEST_L_bg'][-1],
}

print("\n" + "="*60)
print("RECONSTRUCTION STATISTICS")
print("="*60)
print(f"chi2_L = {chi2_L:.4f}")
print(f"chi2_C = {chi2_C:.4f}")
print(f"reduced_chi2_L = {chi2_L / L_obs.size:.4f}")
print(f"reduced_chi2_C = {chi2_C / C_obs.size:.4f}")
print(f"Final TEST: map={final_tests['map']:.3e}, "
      f"C={final_tests['C']:.3e}, L_bg={final_tests['L_bg']:.3e}")
print("="*60)
print("Parameter vector: [map pixels, C(t), L_bg(v)]")
print(f"C_bar is fixed at {C_bar_fixed:.4f} and is not optimized.")
print("L_bg(v) is optimized jointly; it is not pre-subtracted.")
print("="*60)







