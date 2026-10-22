"""复制程序已有的报告图用于 README；只读示例，不生成数据或重新求解。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def render(example: Path, output: Path):
    paths = {
        name: example / name
        for name in (
            "data/dataset.json",
            "data/observations.npz",
            "data/truth.npz",
            "result/result.json",
            "result/solution.npz",
            "report/check.json",
            "report/response.png",
        )
    }
    before = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    dataset = json.loads(paths["data/dataset.json"].read_text(encoding="utf-8"))
    result = json.loads(paths["result/result.json"].read_text(encoding="utf-8"))
    check = json.loads(paths["report/check.json"].read_text(encoding="utf-8"))
    assert dataset["dimension"] == 2
    assert dataset["observation_id"] == result["observation_id"] == check["observation_id"]
    for name in ("observations.npz", "truth.npz"):
        assert before[f"data/{name}"] == dataset["files"][name]
    assert before["result/solution.npz"] == result["files"]["solution.npz"]
    assert before["data/observations.npz"] == result["input_sha256"]

    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(paths["report/response.png"], output / "overview.png")
    image_hash = hashlib.sha256((output / "overview.png").read_bytes()).hexdigest()
    assert image_hash == before["report/response.png"]
    assert before == {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    receipt = {
        "kind": "readme_copy_of_existing_report_figure",
        "source": "Windows/macOS 0.1.0.dev1 bundle / examples/2D",
        "source_figure": "report/response.png",
        "observation_id": dataset["observation_id"],
        "source_sha256": before,
        "config": dataset["config"],
        "checks": check["checks"],
        "optimizer_history_warning": check.get("optimizer_history_warning"),
        "truth_metrics": check["truth_metrics"],
        "new_generation_or_optimization": False,
        "source_files_unchanged": True,
        "image_is_unmodified_report_output": True,
        "rendering": "Original Matplotlib four-panel report figure; shared map color scale, delay and velocity marginals.",
        "reproduce": "python tools/render_readme_preview.py --example <extracted-bundle>/examples/2D --out docs/assets",
        "image_sha256": image_hash,
    }
    (output / "preview.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "image": str(output / "overview.png"),
                "original_report_bytes": "EXACT_MATCH",
                "original_files": "UNCHANGED",
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--example", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    render(args.example, args.out)
