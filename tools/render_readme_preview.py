"""只读现有示例，绘制 README 科学预览；不生成数据或运行求解器。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch


def render(example: Path, output: Path):
    paths = {
        name: example / name
        for name in (
            "data/dataset.json",
            "data/observations.npz",
            "data/truth.npz",
            "result/solution.npz",
            "report/check.json",
        )
    }
    before = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    dataset = json.loads(paths["data/dataset.json"].read_text(encoding="utf-8"))
    check = json.loads(paths["report/check.json"].read_text(encoding="utf-8"))
    assert dataset["dimension"] == 2
    assert dataset["observation_id"] == check["observation_id"]
    for name in ("observations.npz", "truth.npz"):
        assert before[f"data/{name}"] == dataset["files"][name]
    with np.load(paths["data/observations.npz"], allow_pickle=False) as arrays:
        observed = dict(arrays)
    with np.load(paths["data/truth.npz"], allow_pickle=False) as arrays:
        truth = arrays["psi_true"]
    with np.load(paths["result/solution.npz"], allow_pickle=False) as arrays:
        recovered, continuum = arrays["psi"], arrays["continuum"]

    ink, muted, teal, blue, amber = "#172B43", "#60748A", "#0F766E", "#5577CD", "#A05A12"
    with matplotlib.rc_context({"font.family": "DejaVu Sans", "font.size": 10}):
        fig = Figure(figsize=(12.8, 7.15), dpi=160, facecolor="#F6F8FB")
        FigureCanvasAgg(fig)
        fig.add_artist(
            FancyBboxPatch(
                (0.015, 0.025),
                0.97,
                0.95,
                boxstyle="round,pad=0,rounding_size=0.022",
                transform=fig.transFigure,
                facecolor="white",
                edgecolor="#DEE5EE",
                linewidth=0.8,
                zorder=-1,
            )
        )
        fig.text(0.052, 0.922, "BLR / MEM", color=teal, size=11, weight="bold")
        fig.text(0.948, 0.922, "SYNTHETIC EXAMPLE  /  02", color=muted, size=9, ha="right")
        fig.text(0.052, 0.851, "Maximum-entropy response reconstruction.", color=ink, size=24, weight="bold")
        fig.text(0.052, 0.811, "Observed inputs. Joint MEM. Independent checks.", color=muted, size=11)

        def axes(rect, title):
            ax = fig.add_axes(rect)
            ax.set_title(title, loc="left", color=ink, size=11, pad=13, weight="bold")
            ax.tick_params(colors=muted, labelsize=8, length=3)
            ax.xaxis.label.set_color(muted)
            ax.yaxis.label.set_color(muted)
            for spine in ax.spines.values():
                spine.set_color("#DAE2EC")
                spine.set_linewidth(0.7)
            return ax

        light = axes([0.072, 0.425, 0.236, 0.287], "01  Continuum light curve")
        light.scatter(observed["t_c"], observed["c_obs"], s=8, color=blue, alpha=0.45, label="Observed")
        light.plot(observed["t_c"], continuum, color=teal, linewidth=1.5, label="Recovered")
        light.set(xlabel="Time [day]", ylabel="Flux [a.u.]")
        light.grid(axis="y", color="#EDF1F6", linewidth=0.7)
        light.legend(frameon=False, fontsize=7, loc="lower right", handlelength=1.5)

        extent = [
            observed["delays"][0],
            observed["delays"][-1],
            observed["velocities"][0],
            observed["velocities"][-1],
        ]
        v_max = float(max(truth.max(), recovered.max()))
        true_ax = axes([0.402, 0.425, 0.219, 0.287], "02  True response")
        fitted_ax = axes([0.683, 0.425, 0.219, 0.287], "03  Recovered response")
        for ax, values in ((true_ax, truth), (fitted_ax, recovered)):
            im = ax.imshow(
                values,
                origin="lower",
                aspect="auto",
                extent=extent,
                cmap="viridis",
                vmin=0,
                vmax=v_max,
                interpolation="nearest",
            )
            ax.set(xlabel="Delay [day]", xticks=[0, 5, 10, 15], yticks=[-3000, 0, 3000])
        true_ax.set_ylabel("Velocity [km/s]")
        color_ax = fig.add_axes([0.921, 0.425, 0.009, 0.287])
        colorbar = fig.colorbar(im, cax=color_ax)
        colorbar.outline.set_visible(False)
        colorbar.ax.tick_params(labelsize=7, colors=muted, length=2)
        fig.text(0.403, 0.355, "Shared color scale · response [1/day per velocity bin]", color=muted, size=8)

        marginal = axes([0.072, 0.139, 0.236, 0.173], "Delay marginal")
        marginal.plot(
            observed["delays"],
            truth.sum(axis=0),
            color=blue,
            linewidth=1.7,
            linestyle=(0, (3, 2)),
            label="True",
        )
        marginal.plot(observed["delays"], recovered.sum(axis=0), color=teal, linewidth=1.6, label="Recovered")
        marginal.set(xlabel="Delay [day]", ylabel="Response [1/day]")
        marginal.set_xticks([0, 5, 10, 15])
        marginal.grid(axis="y", color="#EDF1F6", linewidth=0.7)
        marginal.legend(frameon=False, fontsize=7, loc="upper left", handlelength=1.5)

        fig.text(0.403, 0.291, "INDEPENDENT CHECKS", color=muted, size=9, weight="bold")
        states = (
            (0.403, 0.251, "Forward consistency", check["checks"]["forward_consistency"]),
            (0.683, 0.251, "Final stationarity", check["checks"]["numerical_convergence"]),
            (0.403, 0.214, "Default stability", check["checks"]["floating_default_stability"]),
            (0.683, 0.214, "Optimizer history", "WARN" if check.get("optimizer_history_warning") else "PASS"),
        )
        for x, y, label, state in states:
            fig.text(x, y, label, color=ink, size=9)
            fig.text(x + 0.20, y, state, color=teal if state == "PASS" else amber, size=9, weight="bold")
        metrics = check["truth_metrics"]
        fig.text(
            0.403,
            0.155,
            f"Shape NMSE  {metrics['shape_nmse']:.4f}     |     Lag error  {metrics['lag_centroid_error_days']:+.3f} day",
            color=ink,
            size=10,
        )
        config = dataset["config"]
        fig.text(
            0.403,
            0.113,
            f"Bundled 2D example · {truth.shape[0]} × {truth.shape[1]} grid · {config['noise_fraction']:.0%} variability noise · seed {config['seed']}",
            color=muted,
            size=8,
        )
        fig.text(
            0.052,
            0.062,
            "Existing synthetic result. Warning states preserved. No real-AGN claim.",
            color=muted,
            size=8,
        )
        output.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            output / "overview.png",
            metadata={
                "Software": "BLR MEM Workbench / Matplotlib",
                "Description": "Read-only visualization of the bundled 2D synthetic example; no refitting.",
            },
        )

    assert before == {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    receipt = {
        "kind": "readme_illustration_of_existing_synthetic_result",
        "source": "Windows/macOS 0.1.0.dev1 bundle / examples/2D",
        "observation_id": dataset["observation_id"],
        "source_sha256": before,
        "config": dataset["config"],
        "checks": check["checks"],
        "optimizer_history_warning": check.get("optimizer_history_warning"),
        "truth_metrics": check["truth_metrics"],
        "new_generation_or_optimization": False,
        "source_files_unchanged": True,
        "rendering": "Matplotlib; nearest-neighbor cells; true/recovered maps share vmin=0 and vmax.",
        "reproduce": "python tools/render_readme_preview.py --example <extracted-bundle>/examples/2D --out docs/assets",
        "image_sha256": hashlib.sha256((output / "overview.png").read_bytes()).hexdigest(),
    }
    (output / "preview.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "image": str(output / "overview.png"),
                "original_files": "UNCHANGED",
                "checks": receipt["checks"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--example", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    render(args.example, args.out)
