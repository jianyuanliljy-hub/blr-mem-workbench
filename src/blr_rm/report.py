"""离线图像和 HTML 报告；指标与数值收敛分别呈现。"""

from __future__ import annotations

import html
from pathlib import Path

import numpy as np

from .status import has_failures, has_warnings, result_lines
from .storage import canonical, load_arrays, save_json


def _figure():
    from matplotlib.figure import Figure

    return Figure(figsize=(11, 8), constrained_layout=True)


def plot_dataset(obs, truth, destination):
    figure = _figure()
    axes = figure.subplots(2, 2)
    if len(obs["velocities"]) == 1:
        axes[0, 0].plot(obs["delays"], truth["psi_true"][0])
        axes[0, 0].set_ylabel("Response [1/day]")
    else:
        extent = [obs["delays"][0], obs["delays"][-1], obs["velocities"][0], obs["velocities"][-1]]
        image = axes[0, 0].imshow(truth["psi_true"], origin="lower", aspect="auto", extent=extent)
        figure.colorbar(image, ax=axes[0, 0], label="Response [1/day per velocity bin]")
        axes[0, 0].set_ylabel("Velocity [km/s]")
    axes[0, 0].set(xlabel="Delay [day]", title="True transfer function")
    axes[0, 1].plot(obs["t_c"], truth["c_true"], label="True")
    axes[0, 1].plot(obs["t_c"], obs["c_obs"], alpha=0.5, label="Observed")
    axes[0, 1].set(xlabel="Time [day]", ylabel="Continuum flux")
    axes[0, 1].legend()
    axes[1, 0].plot(obs["t_l"], truth["l_true"].sum(0), label="True")
    mask = obs["time_mask"]
    axes[1, 0].plot(obs["t_l"][mask], obs["l_obs"][:, mask].sum(0), ".", label="Observed")
    axes[1, 0].set(xlabel="Time [day]", ylabel="Velocity-summed line flux")
    axes[1, 0].legend()
    axes[1, 1].imshow(
        truth["l_true"],
        origin="lower",
        aspect="auto",
        extent=[obs["t_l"][0], obs["t_l"][-1], 0, len(obs["velocities"])],
    )
    axes[1, 1].set(xlabel="Time [day]", ylabel="Velocity bin", title="Noise-free line data")
    figure.savefig(destination, dpi=150)
    figure.clear()


def default_map_diagnostic(solution, config):
    """定位浮动默认图像的变化；1% 分区仅用于解释，不参与通过判定。"""
    from ._vendor.mem2d import geometric_default_2d

    response = solution["psi"]
    target = geometric_default_2d(response, config["smoothness_ratio"])
    squared = np.log(np.maximum(target, 1e-10) / np.maximum(solution["default_map"], 1e-10)) ** 2
    low = response < 0.01 * response.max()
    return {
        "purpose": "EXPLORATORY_ONLY_NO_CHANGE_TO_ACCEPTANCE",
        "low_response_definition": "Psi < 0.01 * max(Psi)",
        "low_response_pixel_fraction": float(low.mean()),
        "low_response_mass_fraction": float(response[low].sum() / response.sum()),
        "low_response_log_change_share": float(squared[low].sum() / squared.sum()) if squared.sum() else 0.0,
        "map_rms_log_change": float(np.sqrt(squared.mean())),
        "low_response_rms_log_change": float(np.sqrt(squared[low].mean())) if low.any() else None,
        "other_response_rms_log_change": float(np.sqrt(squared[~low].mean())),
    }


def _response_comparison(obs, solution, truth, destination):
    figure = _figure()
    axes = figure.subplots(2, 2)
    tau, velocity = obs["delays"], obs["velocities"]
    reference = truth["psi_true"] if truth else solution["default_map"]
    extent = [tau[0], tau[-1], velocity[0], velocity[-1]]
    maximum = max(reference.max(), solution["psi"].max())
    for axis, image, title in zip(
        axes[0],
        [reference, solution["psi"]],
        ["True response" if truth else "Final default map", "Recovered response"],
    ):
        plotted = axis.imshow(
            image, origin="lower", aspect="auto", extent=extent, vmin=0, vmax=maximum, cmap="viridis"
        )
        axis.set(xlabel="Delay [day]", ylabel="Velocity [km/s]", title=title)
    figure.colorbar(plotted, ax=list(axes[0]), label="Response [1/day per velocity bin]")
    for image, label, style in (
        (reference, "True" if truth else "Default", "--"),
        (solution["psi"], "Recovered", "-"),
    ):
        axes[1, 0].plot(tau, image.sum(0), style, label=label)
        axes[1, 1].plot(velocity, image.sum(1) * np.diff(tau)[0], style, label=label)
    axes[1, 0].set(xlabel="Delay [day]", ylabel="Velocity-summed response [1/day]", title="Delay marginal")
    axes[1, 1].set(
        xlabel="Velocity [km/s]", ylabel="Integrated response per velocity bin", title="Velocity marginal"
    )
    for axis in axes[1]:
        axis.legend()
    figure.savefig(destination, dpi=150)
    figure.clear()


def _diagnostic_plot(obs, solution, history, destination):
    figure = _figure()
    axes = figure.subplots(2, 2)
    mask = obs["time_mask"]
    residual = (solution["l_pred"] - obs["l_obs"]) / solution["l_error_used"]
    if len(obs["velocities"]) == 1:
        axes[0, 0].plot(obs["t_l"][mask], residual[0, mask], ".-")
        axes[0, 0].axhline(0, color="grey", linewidth=0.8)
        axes[0, 0].set(ylabel="Line residual / assumed sigma")
    else:
        shown = np.where(mask[None, :], residual, np.nan)
        maximum = max(float(np.nanmax(np.abs(shown))), 1e-12)
        image = axes[0, 0].imshow(
            shown,
            origin="lower",
            aspect="auto",
            cmap="RdBu_r",
            vmin=-maximum,
            vmax=maximum,
            extent=[obs["t_l"][0], obs["t_l"][-1], obs["velocities"][0], obs["velocities"][-1]],
        )
        axes[0, 0].set(ylabel="Velocity [km/s]")
        figure.colorbar(image, ax=axes[0, 0], label="Residual / assumed sigma")
    axes[0, 0].set(xlabel="Time [day]", title="Line residuals (gaps excluded)")
    axes[0, 1].plot(obs["t_c"], (solution["continuum"] - obs["c_obs"]) / solution["c_error_used"], ".-")
    axes[0, 1].axhline(0, color="grey", linewidth=0.8)
    axes[0, 1].set(xlabel="Time [day]", ylabel="Continuum residual / assumed sigma")
    if history and "outer" in history[0]:
        iterations = [row["outer"] for row in history]
        for key, label in (("reduced_chi2_C", "Continuum"), ("reduced_chi2_L", "Line")):
            axes[1, 0].plot(iterations, [row[key] for row in history], "o-", label=label)
        axes[1, 0].set(xlabel="Outer iteration", ylabel="Chi-square / number of data")
        axes[1, 0].legend()
        axes[1, 1].semilogy(iterations, np.maximum([row["default_change"] for row in history], 1e-16), "o-")
        axes[1, 1].set(xlabel="Outer iteration", ylabel="Default RMS log change", title="Prior updates")
    elif history:
        iterations = [row["iteration"] for row in history]
        axes[1, 0].plot(iterations, [row["objective_F"] for row in history])
        axes[1, 0].set(xlabel="Inner iteration", ylabel="MEM objective F")
        axes[1, 1].semilogy(
            iterations, np.maximum([row["original_log_gradient_inf"] for row in history], 1e-16)
        )
        axes[1, 1].set(xlabel="Inner iteration", ylabel="Original log-gradient infinity norm")
    figure.savefig(destination, dpi=150)
    figure.clear()


def write_result_report(dataset, result, output):
    from .detector import inspect_dataset, inspect_result
    from .solver import load_observations
    from .storage import read_json

    output = Path(output)
    if output.exists():
        raise FileExistsError(f"不覆盖已有报告: {output}")
    checked = inspect_result(dataset, result)
    dataset_check = inspect_dataset(dataset)
    _, obs = load_observations(dataset)
    solution = load_arrays(Path(result) / "solution.npz")
    run = read_json(Path(result) / "result.json")
    history = read_json(Path(result) / "history.json")
    truth = load_arrays(Path(dataset) / "truth.npz") if (Path(dataset) / "truth.npz").exists() else None
    output.mkdir(parents=True, exist_ok=False)
    figure = _figure()
    axes = figure.subplots(2, 2)
    if obs["velocities"].size == 1:
        axes[0, 0].plot(obs["delays"], solution["psi"][0], label="Recovered")
    else:
        image = axes[0, 0].imshow(
            solution["psi"],
            origin="lower",
            aspect="auto",
            extent=[obs["delays"][0], obs["delays"][-1], obs["velocities"][0], obs["velocities"][-1]],
        )
        figure.colorbar(image, ax=axes[0, 0], label="Response [1/day per velocity bin]")
        axes[0, 0].set_ylabel("Velocity [km/s]")
    if truth:
        if len(obs["velocities"]) == 1:
            axes[0, 0].plot(obs["delays"], truth["psi_true"][0], "--", label="True")
            axes[0, 0].legend()
        plot_dataset(obs, truth, output / "truth.png")
    axes[0, 0].set(xlabel="Delay [day]", title="Recovered response")
    axes[0, 1].plot(obs["t_c"], obs["c_obs"], ".", alpha=0.5, label="Observed")
    axes[0, 1].plot(obs["t_c"], solution["continuum"], label="Recovered")
    axes[0, 1].set(xlabel="Time [day]", ylabel="Continuum flux")
    axes[0, 1].legend()
    mask = obs["time_mask"]
    axes[1, 0].plot(obs["t_l"][mask], obs["l_obs"][:, mask].sum(0), ".", label="Observed")
    axes[1, 0].plot(obs["t_l"], solution["l_pred"].sum(0), label="Predicted")
    axes[1, 0].set(xlabel="Time [day]", ylabel="Velocity-summed line flux")
    axes[1, 0].legend()
    residual = (solution["l_pred"] - obs["l_obs"]) / solution["l_error_used"]
    axes[1, 1].hist(residual[:, mask].ravel(), bins=30)
    axes[1, 1].set(xlabel="Line residual / assumed sigma", ylabel="Count")
    figure.savefig(output / "reconstruction.png", dpi=150)
    figure.clear()
    _diagnostic_plot(obs, solution, history, output / "diagnostics.png")
    save_json(output / "check.json", checked)
    state = "有未通过项" if has_failures(checked) else "有数值警告" if has_warnings(checked) else "检测通过"
    body = '<section class="card"><h2>' + state + "</h2><ul>"
    body += "".join("<li>" + html.escape(line) + "</li>" for line in result_lines(checked)) + "</ul>"
    body += (
        f"<p>维度：{run['dimension']}D；响应网格：{solution['psi'].shape[0]} × {solution['psi'].shape[1]}；"
    )
    body += f"求解用时：{run['compute_seconds']:.3g} s。误差权重："
    body += (
        html.escape(str(run["error_floor"])) + "（C、L 绝对误差下限）" if run["error_floor"] else "观测标准差"
    )
    body += "。</p></section>"
    body += '<h2>恢复与残差</h2><img src="reconstruction.png" alt="恢复图和残差图">'
    if run["dimension"] == 2:
        _response_comparison(obs, solution, truth, output / "response.png")
        body += (
            "<h2>响应图对照</h2><p>上排共用色标；下排保留响应的绝对幅度。速度通道已积分，不再乘速度步长。</p>"
        )
        body += '<img src="response.png" alt="统一色标的响应对照与边缘响应">'
        diagnostic = default_map_diagnostic(solution, run["solver_config"])
        save_json(output / "default_map_diagnostic.json", diagnostic)
        body += "<details><summary>浮动默认图像变化来自哪里？</summary><p>"
        body += (
            f"低于响应峰值 1% 的像素占 {diagnostic['low_response_pixel_fraction']:.1%}，"
            f"贡献总响应的 {diagnostic['low_response_mass_fraction']:.2%}，"
            f"贡献均方对数变化的 {diagnostic['low_response_log_change_share']:.1%}。"
        )
        body += "这项分区用于解释变化，原稳定性阈值和 WARN 判定保持原样。强响应区域也需要结合残差检查。</p></details>"
    body += "<h2>残差与迭代过程</h2><p>残差使用实际拟合标准差归一化；缺测发射线不参与统计。</p>"
    body += '<img src="diagnostics.png" alt="残差分布与迭代历史">'
    if (output / "truth.png").exists():
        body += '<h2>模拟真值</h2><img src="truth.png" alt="无噪声真值">'
    for title, data in (
        ("独立检测完整记录", checked),
        ("生成数据检测", dataset_check),
        ("完整优化参数", run["solver_config"]),
    ):
        body += (
            "<details><summary>"
            + title
            + "</summary><pre>"
            + html.escape(canonical(data))
            + "</pre></details>"
        )
    write_html(output / "report.html", "BLR MEM 反演报告", body)
    return str(output / "report.html")


def write_html(path: Path, title: str, body: str):
    document = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    document += "<style>body{font:16px/1.65 system-ui,sans-serif;max-width:1080px;margin:40px auto;padding:0 22px;color:#17283e}h1,h2{line-height:1.3}img{width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f9;padding:20px;border-radius:10px}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #cbd5e1;text-align:left}.note{background:#fff5df;padding:16px}.card{border:1px solid #cbd5e1;border-radius:10px;padding:0 20px 12px}details{margin:18px 0}summary{cursor:pointer;font-weight:600}</style>"
    document += "<title>" + html.escape(title) + "</title><h1>" + html.escape(title) + "</h1>"
    document += (
        '<p class="note">数值收敛、模拟真值恢复和真实天体适用性分别评价。卡方除以数据点数（χ²/N）不代表已知有效自由度的约化卡方。首版尚无真实 AGN 验证。</p>'
        + body
        + "</html>"
    )
    with path.open("x", encoding="utf-8") as stream:
        stream.write(document)
